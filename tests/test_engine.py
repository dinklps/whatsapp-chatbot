from datetime import timedelta

from sqlalchemy import select

from app.db.models import Caller, Intake, utcnow
from app.engine.llm import LLMError, is_single_question
from app.types import Inbound
from tests.conftest import turn

PHONE = "60123456789"


def msg(text, **kw):
    return Inbound(phone=PHONE, text=text, **kw)


async def run_full_intake(engine, llm):
    """A first-time purchaser answering one question at a time."""
    llm.script(
        turn("caller_type", "Hello! Are you the purchaser, a lawyer, from a bank, or someone else?"),
        turn("caller_name", "Thanks. May I have your name?", caller_type="purchaser"),
        turn("project", "Which project is the property in?", caller_name="Aminah"),
        turn(
            "unit_no",
            "What is the unit number?",
            project_key="sample-residence",
            project_text="sample residence",
        ),
        turn("summary", "How can we help you with this unit?", unit_no="A-12-3"),
        turn(
            "none",
            "Thank you.",
            summary="Asks when the strata title will be transferred.",
            reason_category="status_enquiry",
        ),
    )
    outs = []
    for text in ["hi", "purchaser", "Aminah", "sample residence", "A-12-3", "when is my title coming"]:
        outs.append(await engine.handle(msg(text)))
    return outs


async def test_full_intake_asks_one_question_per_turn_then_hands_off(engine, llm, table):
    outs = await run_full_intake(engine, llm)

    for step in outs[:-1]:
        assert len(step) == 1
        assert is_single_question(step[0].body)
    assert outs[0][0].kind == "list"  # caller type is offered as tappable options

    reply, alert = outs[-1]
    pic = table.data.staff["pic_a"]
    assert pic.name in reply.body and pic.wa_link in reply.body
    assert alert.to == pic.whatsapp and alert.kind == "template"
    assert alert.params[0] == "purchaser"
    assert alert.params[2] == "Sample Residence"
    assert alert.params[3] == "A-12-3"
    assert alert.params[4] == "Status enquiry"
    assert alert.params[6] == f"https://wa.me/{PHONE}"

    with engine.sessions() as db:
        intake = db.scalar(select(Intake))
        assert intake.status == "handed_off" and intake.routed_role == "pic"


async def test_everything_in_first_message_skips_to_what_is_missing(engine, llm):
    llm.script(
        turn(
            "caller_name",
            "Thanks, may I have your name?",
            caller_type="purchaser",
            project_key="example-heights",
            project_text="Example Heights",
            unit_no="B-3-1",
            summary="Wants to know which documents are still pending.",
            reason_category="document_request",
        ),
        turn("none", "Thank you.", caller_name="Tan"),
    )
    first = await engine.handle(msg("I'm the purchaser of B-3-1 Example Heights, what documents are pending?"))
    assert [o.body for o in first] == ["Thanks, may I have your name?"]
    second = await engine.handle(msg("Tan"))
    assert second[1].purpose == "alert" and second[1].params[4] == "Document request"


async def test_model_asking_the_wrong_slot_is_overridden(engine, llm):
    # The model tries to jump to the project; the engine insists on caller type first.
    llm.script(turn("project", "Which project is this about?"))
    out = await engine.handle(msg("hello"))
    assert out[0].kind == "list"
    assert out[0].body.startswith("PHRASED Ask whether they are the purchaser")


async def test_reply_with_two_questions_is_replaced(engine, llm):
    llm.script(turn("caller_type", "Who are you? And which project is this?"))
    out = await engine.handle(msg("hello"))
    assert is_single_question(out[0].body)
    assert out[0].body.startswith("PHRASED")


async def test_model_down_falls_back_to_fixed_questions(engine, llm):
    llm.phrase_fails = True
    llm.script(LLMError("down"))
    out = await engine.handle(msg("hello"))
    assert out[0].body == "Are you the purchaser, a lawyer, from a bank, or someone else?"


async def test_list_reply_sets_caller_type_without_the_model(engine, llm):
    llm.phrase_fails = True
    llm.script(LLMError("down"), LLMError("down"))
    await engine.handle(msg("hello"))
    out = await engine.handle(msg("Lawyer / Peguam", kind="list_reply", reply_id="caller_type:lawyer"))
    assert out[0].body == "May I have your name, please?"


async def test_lawyer_is_asked_for_their_firm(engine, llm):
    llm.script(
        turn("caller_name", "May I have your name?", caller_type="lawyer"),
        turn("organisation", "Which firm are you from?", caller_name="Siva"),
    )
    await engine.handle(msg("I'm a lawyer"))
    out = await engine.handle(msg("Siva"))
    assert out[0].body == "Which firm are you from?"


async def test_complaint_goes_to_head_of_department(engine, llm, table):
    llm.script(
        turn(
            "none",
            "Thank you.",
            caller_type="purchaser",
            caller_name="Lim",
            project_key="sample-residence",
            unit_no="C-1-1",
            summary="Has been unable to reach the PIC for two weeks.",
            reason_category="complaint",
        )
    )
    reply, alert = await engine.handle(msg("I can't reach your staff for 2 weeks! Lim, C-1-1 Sample Residence"))
    hod = table.data.staff["hod"]
    assert alert.to == hod.whatsapp
    assert hod.name in reply.body


async def test_unknown_project_asks_location_then_routes_to_duty_desk(engine, llm, table):
    llm.script(
        turn("unit_no", "What is the unit number?", caller_type="other", caller_name="Raj", project_text="Mystery Park"),
        turn("location", "Where is the property located?", unit_no="12"),
        turn("summary", "How can we help?", location="Ipoh"),
        turn("none", "Thanks.", summary="Wants to change correspondence address.", reason_category="others"),
    )
    first = await engine.handle(msg("Raj here, other party, about Mystery Park"))
    # Project was volunteered but isn't in our list: confirm it once before moving on.
    assert first[0].body.startswith("PHRASED Ask which project")
    second = await engine.handle(msg("Mystery Park, unit 12"))
    assert second[0].body == "Where is the property located?"
    await engine.handle(msg("Ipoh"))
    out = await engine.handle(msg("change my address"))
    alert = out[-1]
    assert alert.purpose == "alert"
    assert alert.to == table.data.staff["duty"].whatsapp
    assert "not in project list" in alert.params[2]


async def test_caller_who_wants_a_human_is_handed_off_immediately(engine, llm, table):
    llm.script(turn("caller_type", "Are you the purchaser?", wants_human=True))
    reply, alert = await engine.handle(msg("just let me talk to someone"))
    assert alert.to == table.data.staff["duty"].whatsapp
    assert "asked to speak to staff" in alert.params[5]
    assert table.data.staff["duty"].wa_link in reply.body


async def test_slot_is_given_up_after_two_asks(engine, llm):
    llm.script(
        turn("caller_type", "Are you the purchaser, a lawyer, from a bank, or someone else?"),
        turn("caller_type", "Sorry, are you the purchaser, a lawyer, from a bank, or someone else?"),
        turn("caller_name", "May I have your name?"),
    )
    await engine.handle(msg("hmm"))
    await engine.handle(msg("why"))
    out = await engine.handle(msg("not telling"))
    assert out[0].body == "May I have your name?"


async def test_returning_caller_is_asked_only_whether_it_is_the_same_unit(engine, llm):
    await run_full_intake(engine, llm)

    llm.script(
        turn("same_as_previous", "Welcome back Aminah, is this about A-12-3 at Sample Residence again?"),
        turn("summary", "How can we help you this time?", same_as_previous=True),
        turn("none", "Thanks.", summary="Wants to collect the MOT.", reason_category="collection"),
    )
    first = await engine.handle(msg("hi again"))
    assert "A-12-3" in first[0].body
    ctx = llm.contexts[-1]
    assert ctx.returning_caller and ctx.previous_file == {"project": "Sample Residence", "unit_no": "A-12-3"}
    assert ctx.known["caller_type"] == "purchaser" and ctx.known["caller_name"] == "Aminah"

    await engine.handle(msg("yes"))
    out = await engine.handle(msg("want to collect my MOT"))
    alert = out[-1]
    assert alert.params[2:5] == ["Sample Residence", "A-12-3", "Collection"]


async def test_thanks_after_handoff_does_not_start_a_new_enquiry(engine, llm):
    await run_full_intake(engine, llm)
    llm.script(turn("same_as_previous", "Is this about the same unit?", closing_remark=True))
    out = await engine.handle(msg("ok thanks"))
    assert len(out) == 1 and "?" not in out[0].body
    with engine.sessions() as db:
        assert db.scalars(select(Intake.status).order_by(Intake.id)).all() == ["handed_off", "ignored"]


async def test_duplicate_delivery_is_ignored(engine, llm):
    llm.script(turn("caller_type", "Are you the purchaser, a lawyer, from a bank, or someone else?"))
    first = await engine.handle(msg("hi", wa_id="wamid.1"))
    again = await engine.handle(msg("hi", wa_id="wamid.1"))
    assert first and again == []


async def test_voice_note_is_flagged_for_staff(engine, llm):
    llm.script(turn("caller_type", "I can only read text. Are you the purchaser, a lawyer, from a bank, or someone else?", wants_human=True))
    out = await engine.handle(Inbound(phone=PHONE, text="", kind="audio"))
    assert "voice note" in llm.contexts[0].notes[0]
    assert "sent a voice note or file" in out[-1].params[5]


async def test_stale_conversation_starts_a_new_enquiry(engine, llm):
    llm.script(
        turn("caller_name", "May I have your name?", caller_type="bank"),
        turn("caller_type", "Are you the purchaser, a lawyer, from a bank, or someone else?"),
    )
    await engine.handle(msg("bank here"))
    with engine.sessions() as db:
        intake = db.scalar(select(Intake))
        intake.updated_at = utcnow() - timedelta(hours=25)
        db.commit()
    await engine.handle(msg("hello"))
    with engine.sessions() as db:
        assert db.scalars(select(Intake.status).order_by(Intake.id)).all() == ["abandoned", "open"]
        assert db.scalar(select(Caller)).caller_type is None  # nothing remembered from an unfinished intake
