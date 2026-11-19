from dataclasses import dataclass, field


@dataclass
class Inbound:
    """A message from a caller, already normalised from the WhatsApp payload."""

    phone: str
    text: str
    kind: str = "text"  # text | list_reply | audio | image | document | video | other
    wa_id: str | None = None
    reply_id: str | None = None  # id of the list/button option chosen, if any
    profile_name: str | None = None


@dataclass
class Outbound:
    """A message the bot wants sent. `kind` is text, list or template."""

    to: str
    kind: str = "text"
    body: str = ""
    button: str = ""
    rows: list[tuple[str, str]] = field(default_factory=list)  # (id, title) for list messages
    template: str = ""
    template_lang: str = ""
    params: list[str] = field(default_factory=list)
    purpose: str = "reply"  # reply | alert
