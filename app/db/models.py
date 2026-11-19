from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Caller(Base):
    """One row per WhatsApp number. What we remember between enquiries."""

    __tablename__ = "callers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    caller_type: Mapped[str | None] = mapped_column(String(32))
    organisation: Mapped[str | None] = mapped_column(String(200))
    last_project_key: Mapped[str | None] = mapped_column(String(100))
    last_project_text: Mapped[str | None] = mapped_column(String(200))
    last_unit_no: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Intake(Base):
    """One enquiry: the call-log row plus the conversation state."""

    __tablename__ = "intakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    caller_id: Mapped[int] = mapped_column(ForeignKey("callers.id"), index=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)

    caller_type: Mapped[str | None] = mapped_column(String(32))
    caller_name: Mapped[str | None] = mapped_column(String(200))
    organisation: Mapped[str | None] = mapped_column(String(200))
    project_key: Mapped[str | None] = mapped_column(String(100))
    project_text: Mapped[str | None] = mapped_column(String(200))
    unit_no: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(200))
    reason_category: Mapped[str | None] = mapped_column(String(40))
    summary: Mapped[str | None] = mapped_column(Text)

    # Conversation state
    same_as_previous: Mapped[bool | None] = mapped_column(Boolean)
    last_asked: Mapped[str | None] = mapped_column(String(40))
    ask_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    language: Mapped[str] = mapped_column(String(40), default="English")
    has_media: Mapped[bool] = mapped_column(Boolean, default=False)
    wants_human: Mapped[bool] = mapped_column(Boolean, default=False)

    routed_to_name: Mapped[str | None] = mapped_column(String(200))
    routed_to_number: Mapped[str | None] = mapped_column(String(32))
    routed_role: Mapped[str | None] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intake_id: Mapped[int | None] = mapped_column(ForeignKey("intakes.id"), index=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(3))  # "in" | "out"
    wa_message_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="text")
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
