"""The conversation engine.

One call to `Engine.handle` per inbound message. The engine owns the state: it decides which
slot is asked next and when the intake is complete. The model extracts what the caller said and
words the question; if its wording doesn't match the slot the engine chose, or isn't exactly one
question, the engine re-words it or falls back to a fixed template.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Caller, Intake, Message, utcnow
from app.engine import templates
from app.engine.llm import (
    LLM,
    Extracted,
    LLMError,
    TurnContext,
    TurnOutput,
    has_no_question,
    is_single_question,
)
from app.engine.slots import has_previous_file, known_slots, missing_slots
from app.handoff.handoff import alert_message, contact_block
from app.routing.projects import RoutingTable
from app.types import Inbound, Outbound

log = logging.getLogger(__name__)

MEDIA_NOTES = {
    "audio": "The caller sent a voice note. You cannot listen to it.",
    "image": "The caller sent an image. You cannot view it.",
    "document": "The caller sent a document. You cannot open it.",
    "video": "The caller sent a video. You cannot view it.",
    "other": "The caller sent something that is not text. You cannot read it.",
}
HISTORY_LIMIT = 30


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Engine:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        llm: LLM,
        table: RoutingTable,
        reasons: list[dict],
        session_timeout_hours: int = 24,
        alert_template: str = "intake_alert",
        alert_template_lang: str = "en",
    ):
        self.sessions = sessions
        self.llm = llm
        self.table = table
        self.reason_labels = {r["key"]: r["label"] for r in reasons}
        self.timeout = timedelta(hours=session_timeout_hours)
        self.alert_template = alert_template
        self.alert_template_lang = alert_template_lang

    # ------------------------------------------------------------------ public

    async def handle(self, inbound: Inbound) -> list[Outbound]:
        with self.sessions() as db:
            if inbound.wa_id and db.scalar(
                select(Message.id).where(Message.wa_message_id == inbound.wa_id)
            ):
                return []  # Meta redelivered a message we already handled

            caller = self._caller(db, inbound.phone)
            intake, fresh = self._open_intake(db, caller)
            history = self._history(db, intake)

            body = inbound.text or f"[{inbound.kind}]"
            db.add(
                Message(
                    intake_id=intake.id,
                    phone=inbound.phone,
                    direction="in",
                    wa_message_id=inbound.wa_id,
                    kind=inbound.kind,
                    body=body,
                )
            )
            if inbound.kind in MEDIA_NOTES:
                intake.has_media = True
            if inbound.reply_id and inbound.reply_id.startswith("caller_type:"):
                intake.caller_type = inbound.reply_id.split(":", 1)[1]
            db.commit()  # release the database before waiting on the model

            turn = await self._turn(intake, caller, history, inbound, body)

            if turn is not None:
                if turn.start_over and not fresh:
                    intake.status = "abandoned"
                    intake = self._new_intake(db, caller)
                    fresh = True
                if turn.language:
                    intake.language = turn.language
                if (
                    fresh
                    and turn.closing_remark
                    and turn.extracted.is_empty()
                    and self._last_status(db, caller, before=intake.id) == "handed_off"
                ):
                    # "Thanks" after a handoff: reply politely, don't start a new enquiry.
                    intake.status = "ignored"
                    text = await self._phrase(
                        "The caller just thanked us or said goodbye after their enquiry was "
                        "passed to staff. Acknowledge briefly. Do not ask any question.",
                        intake.language,
                        ok=has_no_question,
                        fallback=templates.closing(intake.language),
                    )
                    return self._finish(db, intake, [Outbound(to=inbound.phone, body=text)])
                self._apply(intake, caller, turn.extracted)
                if turn.wants_human:
                    intake.wants_human = True

            missing = missing_slots(intake, caller)
            if intake.wants_human or not missing:
                out = await self._handoff(intake, caller)
            else:
                out = [await self._ask(missing[0], intake, caller, turn)]
            return self._finish(db, intake, out)

    # ------------------------------------------------------------ state loading

    def _caller(self, db: Session, phone: str) -> Caller:
        caller = db.scalar(select(Caller).where(Caller.phone == phone))
        if caller is None:
            caller = Caller(phone=phone)
            db.add(caller)
            db.flush()
        return caller

    def _open_intake(self, db: Session, caller: Caller) -> tuple[Intake, bool]:
        intake = db.scalar(
            select(Intake)
            .where(Intake.caller_id == caller.id, Intake.status == "open")
            .order_by(Intake.id.desc())
        )
        if intake is not None:
            if utcnow() - _aware(intake.updated_at) <= self.timeout:
                return intake, False
            intake.status = "abandoned"
        return self._new_intake(db, caller), True

    def _new_intake(self, db: Session, caller: Caller) -> Intake:
        # A returning caller is not asked again for who they are.
        intake = Intake(
            caller_id=caller.id,
            phone=caller.phone,
            status="open",
            caller_type=caller.caller_type,
            caller_name=caller.name,
            organisation=caller.organisation,
            ask_counts={},
        )
        db.add(intake)
        db.flush()
        return intake

    def _history(self, db: Session, intake: Intake) -> list[tuple[str, str]]:
        rows = db.scalars(
            select(Message)
            .where(Message.intake_id == intake.id, Message.phone == intake.phone)
            .order_by(Message.id.desc())
            .limit(HISTORY_LIMIT)
        ).all()
        return [("user" if m.direction == "in" else "assistant", m.body) for m in reversed(rows)]

    def _last_status(self, db: Session, caller: Caller, before: int) -> str | None:
        return db.scalar(
            select(Intake.status)
            .where(Intake.caller_id == caller.id, Intake.id < before, Intake.status != "ignored")
            .order_by(Intake.id.desc())
        )

    # ------------------------------------------------------------------- model

    async def _turn(
        self,
        intake: Intake,
        caller: Caller,
        history: list[tuple[str, str]],
        inbound: Inbound,
        body: str,
    ) -> TurnOutput | None:
        missing = missing_slots(intake, caller)
        previous = None
        if "same_as_previous" in missing:
            previous = {"project": self._previous_project(caller), "unit_no": caller.last_unit_no}
        ctx = TurnContext(
            history=history,
            message=body,
            known=known_slots(intake),
            missing=missing,
            previous_file=previous,
            returning_caller=bool(caller.caller_type),
            notes=[MEDIA_NOTES[inbound.kind]] if inbound.kind in MEDIA_NOTES else [],
        )
        try:
            return await self.llm.turn(ctx)
        except (LLMError, ValueError) as e:  # ValueError: output failed schema validation
            log.warning("model turn failed, using fixed wording: %s", e)
            return None

    async def _phrase(self, instruction: str, language: str, ok, fallback: str) -> str:
        try:
            text = await self.llm.phrase(instruction, language)
        except LLMError as e:
            log.warning("model phrasing failed, using fixed wording: %s", e)
            return fallback
        return text if ok(text) else fallback

    # ------------------------------------------------------------ state changes

    def _previous_project(self, caller: Caller) -> str:
        project = self.table.get(caller.last_project_key)
        return project.name if project else (caller.last_project_text or "")

    def _apply(self, intake: Intake, caller: Caller, x: Extracted) -> None:
        for name in ["caller_type", "caller_name", "organisation", "unit_no", "location", "summary"]:
            value = getattr(x, name)
            if isinstance(value, str) and value.strip():
                setattr(intake, name, value.strip())
        if x.reason_category:
            intake.reason_category = x.reason_category

        project = self.table.get(x.project_key) or self.table.match(x.project_text)
        if project:
            intake.project_key, intake.project_text = project.key, project.name
        elif x.project_text and x.project_text.strip():
            intake.project_key, intake.project_text = None, x.project_text.strip()

        if x.same_as_previous is not None and has_previous_file(caller):
            intake.same_as_previous = x.same_as_previous
            if x.same_as_previous and not (intake.project_text or intake.unit_no):
                intake.project_key = caller.last_project_key
                intake.project_text = self._previous_project(caller)
                intake.unit_no = caller.last_unit_no

    async def _ask(
        self, slot: str, intake: Intake, caller: Caller, turn: TurnOutput | None
    ) -> Outbound:
        fmt = {"project": self._previous_project(caller), "unit": caller.last_unit_no or ""}
        if turn is not None and turn.asked_slot == slot and is_single_question(turn.reply):
            text = turn.reply.strip()
        else:
            text = await self._phrase(
                templates.QUESTION_INSTRUCTIONS[slot].format(**fmt),
                intake.language,
                ok=is_single_question,
                fallback=templates.question(slot, intake.language, **fmt),
            )
        counts = dict(intake.ask_counts or {})
        counts[slot] = counts.get(slot, 0) + 1
        intake.ask_counts = counts
        intake.last_asked = slot
        if slot == "caller_type":
            return Outbound(
                to=intake.phone,
                kind="list",
                body=text,
                button="Select / Pilih",
                rows=list(templates.CALLER_TYPE_ROWS),
            )
        return Outbound(to=intake.phone, body=text)

    async def _handoff(self, intake: Intake, caller: Caller) -> list[Outbound]:
        intake.reason_category = intake.reason_category or "others"
        route = self.table.route(intake.project_key, intake.reason_category)
        intake.status = "handed_off"
        intake.completed_at = utcnow()
        intake.routed_to_name = route.staff.name
        intake.routed_to_number = route.staff.whatsapp
        intake.routed_role = route.role

        # Remember the caller for next time.
        caller.caller_type = intake.caller_type or caller.caller_type
        caller.name = intake.caller_name or caller.name
        caller.organisation = intake.organisation or caller.organisation
        if intake.unit_no and intake.project_text:
            caller.last_project_key = intake.project_key
            caller.last_project_text = intake.project_text
            caller.last_unit_no = intake.unit_no

        text = await self._phrase(
            f"Thank the caller and tell them their enquiry has been recorded and passed to "
            f"{route.staff.name}, who will follow up with them, and that the contact details "
            f"are below this message. Do not ask any question.",
            intake.language,
            ok=has_no_question,
            fallback=templates.handoff(intake.language, route.staff.name),
        )
        reply = Outbound(
            to=intake.phone, body=f"{text}\n\n{contact_block(route, intake, self.table)}"
        )
        alert = alert_message(
            route,
            intake,
            self.table,
            self.reason_labels,
            self.alert_template,
            self.alert_template_lang,
        )
        return [reply, alert]

    def _finish(self, db: Session, intake: Intake, out: list[Outbound]) -> list[Outbound]:
        for o in out:
            db.add(
                Message(
                    intake_id=intake.id,
                    phone=o.to,
                    direction="out",
                    kind="alert" if o.purpose == "alert" else o.kind,
                    body=o.body,
                )
            )
        intake.updated_at = utcnow()
        db.commit()
        return out
