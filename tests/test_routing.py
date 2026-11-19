import hashlib
import hmac

from app.types import Outbound
from app.whatsapp.client import to_payload
from app.whatsapp.parse import parse_webhook
from app.whatsapp.verify import signature_valid


def test_normal_enquiry_goes_to_the_project_pic(table):
    route = table.route("sample-residence", "status_enquiry")
    assert route.role == "pic" and route.staff == table.data.staff["pic_a"]


def test_complaint_goes_to_hod(table):
    route = table.route("example-heights", "complaint")
    assert route.role == "hod" and route.staff == table.data.staff["hod"]
    assert route.pic == table.data.staff["pic_b"]


def test_unknown_project_goes_to_duty_desk(table):
    assert table.route(None, "payment").role == "duty"
    assert table.route("no-such-key", "payment").staff == table.data.staff["duty"]


def test_match_by_name_and_alias_ignores_case_and_punctuation(table):
    assert table.match("SAMPLE  residence").key == "sample-residence"
    assert table.match("residensi sample").key == "sample-residence"
    assert table.match("somewhere else") is None


def test_signature_check():
    body = b'{"a":1}'
    good = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert signature_valid("secret", body, good)
    assert not signature_valid("secret", body + b" ", good)
    assert not signature_valid("secret", body, None)
    assert not signature_valid("", body, good)


def _payload(message: dict) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "60123456789", "profile": {"name": "Aminah"}}],
                            "messages": [{"from": "60123456789", "id": "wamid.X", **message}],
                        }
                    }
                ]
            }
        ]
    }


def test_parse_text_list_reply_and_voice_note():
    [text] = parse_webhook(_payload({"type": "text", "text": {"body": "hello"}}))
    assert (text.phone, text.text, text.kind, text.wa_id) == ("60123456789", "hello", "text", "wamid.X")
    assert text.profile_name == "Aminah"

    [choice] = parse_webhook(
        _payload(
            {
                "type": "interactive",
                "interactive": {"type": "list_reply", "list_reply": {"id": "caller_type:bank", "title": "Bank"}},
            }
        )
    )
    assert choice.reply_id == "caller_type:bank" and choice.text == "Bank"

    [voice] = parse_webhook(_payload({"type": "audio", "audio": {"id": "1"}}))
    assert voice.kind == "audio" and voice.text == ""


def test_parse_ignores_status_updates_and_reactions():
    assert parse_webhook({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}) == []
    assert parse_webhook(_payload({"type": "reaction", "reaction": {"emoji": "x"}})) == []


def test_outbound_payload_shapes():
    text = to_payload(Outbound(to="601", body="hi"))
    assert text["type"] == "text" and text["text"]["body"] == "hi"

    listing = to_payload(Outbound(to="601", kind="list", body="Pick", button="Select", rows=[("a", "A")]))
    assert listing["interactive"]["action"]["sections"][0]["rows"] == [{"id": "a", "title": "A"}]

    template = to_payload(
        Outbound(to="601", kind="template", template="intake_alert", template_lang="en", params=["x", "y"])
    )
    assert template["template"]["name"] == "intake_alert"
    assert [p["text"] for p in template["template"]["components"][0]["parameters"]] == ["x", "y"]
