"""What the bot collects, in what order, and when a slot applies.

The engine (code) decides which slot to ask next; the model only words the question.
"""

from app.db.models import Caller, Intake

CALLER_TYPES = ["purchaser", "lawyer", "bank", "other"]

# Order in which slots are asked.
SLOT_ORDER = [
    "same_as_previous",
    "caller_type",
    "caller_name",
    "organisation",
    "project",
    "unit_no",
    "location",
    "summary",
]

# After this many asks without an answer, a slot is skipped and left blank for staff.
MAX_ASKS = 2


def has_previous_file(caller: Caller) -> bool:
    return bool(caller.last_unit_no and (caller.last_project_key or caller.last_project_text))


def _applies(slot: str, intake: Intake, caller: Caller) -> bool:
    if slot == "same_as_previous":
        # Only offered to a returning caller who hasn't already named a project or unit.
        return has_previous_file(caller) and not (intake.project_text or intake.unit_no)
    if slot == "organisation":
        return intake.caller_type in ("lawyer", "bank")
    if slot == "location":
        # Only useful when we could not match the project to our list.
        return intake.project_key is None
    return True


def _filled(slot: str, intake: Intake) -> bool:
    asks = (intake.ask_counts or {}).get(slot, 0)
    if slot == "same_as_previous":
        return intake.same_as_previous is not None
    if slot == "project":
        if intake.project_key:
            return True
        # An unrecognised project name is accepted once we have asked about it.
        return bool(intake.project_text) and asks >= 1
    return bool(getattr(intake, slot))


def missing_slots(intake: Intake, caller: Caller) -> list[str]:
    """Slots still to ask, in order. Slots asked MAX_ASKS times are given up on."""
    asks = intake.ask_counts or {}
    return [
        slot
        for slot in SLOT_ORDER
        if _applies(slot, intake, caller)
        and not _filled(slot, intake)
        and asks.get(slot, 0) < MAX_ASKS
    ]


def known_slots(intake: Intake) -> dict:
    fields = [
        "caller_type",
        "caller_name",
        "organisation",
        "project_key",
        "project_text",
        "unit_no",
        "location",
        "reason_category",
        "summary",
    ]
    return {f: getattr(intake, f) for f in fields if getattr(intake, f)}
