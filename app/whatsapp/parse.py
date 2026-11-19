"""Turn a WhatsApp Cloud API webhook payload into normalised inbound messages."""

from app.types import Inbound

MEDIA_KINDS = {"audio": "audio", "image": "image", "document": "document", "video": "video"}
IGNORED = {"reaction", "system", "ephemeral"}


def parse_webhook(payload: dict) -> list[Inbound]:
    out: list[Inbound] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts") or []
            }
            for msg in value.get("messages") or []:
                inbound = _parse_message(msg, names)
                if inbound:
                    out.append(inbound)
    return out


def _parse_message(msg: dict, names: dict) -> Inbound | None:
    phone, mtype = msg.get("from"), msg.get("type")
    if not phone or mtype in IGNORED:
        return None
    base = {"phone": phone, "wa_id": msg.get("id"), "profile_name": names.get(phone)}

    if mtype == "text":
        return Inbound(text=(msg.get("text") or {}).get("body", ""), **base)
    if mtype == "interactive":
        interactive = msg.get("interactive") or {}
        reply = interactive.get("list_reply") or interactive.get("button_reply") or {}
        return Inbound(
            text=reply.get("title", ""), kind="list_reply", reply_id=reply.get("id"), **base
        )
    if mtype == "button":
        return Inbound(text=(msg.get("button") or {}).get("text", ""), **base)
    if mtype in MEDIA_KINDS:
        caption = (msg.get(mtype) or {}).get("caption", "")
        return Inbound(text=caption, kind=MEDIA_KINDS[mtype], **base)
    return Inbound(text="", kind="other", **base)
