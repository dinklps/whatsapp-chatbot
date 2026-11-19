"""Builds the two handoff messages: contact details for the caller, and the alert for staff."""

import re

from app.db.models import Intake
from app.routing.projects import Route, RoutingTable, wa_link
from app.types import Outbound

# Order of the {{1}}..{{7}} variables in the approved `intake_alert` template (see README).
ALERT_FIELDS = ["Caller type", "Caller", "Project", "Unit", "Reason", "Summary", "Reply to caller"]


def _clean(value: str | None, limit: int = 200) -> str:
    """Template variables may not contain newlines, tabs or runs of spaces, and may not be empty."""
    text = re.sub(r"\s+", " ", value or "").strip()
    return (text[: limit - 1] + "…") if len(text) > limit else (text or "-")


def contact_block(route: Route, intake: Intake, table: RoutingTable) -> str:
    """Contact details appended to the caller's closing message. Written by code, never the model."""
    staff = route.staff
    lines = [staff.name, f"WhatsApp: {staff.wa_link}"]
    if intake.reason_category == "pic_contact":
        if staff.email:
            lines.append(f"Email: {staff.email}")
        if staff.office:
            lines.append(f"Office: {staff.office}")
        hod = table.route(intake.project_key, "complaint").staff
        if hod.name != staff.name:
            lines.append("")
            lines.append(f"Head of department: {hod.name}")
            if hod.email:
                lines.append(f"Email: {hod.email}")
            if hod.office:
                lines.append(f"Office: {hod.office}")
    return "\n".join(lines)


def alert_params(intake: Intake, table: RoutingTable, reason_labels: dict[str, str]) -> list[str]:
    project = table.get(intake.project_key)
    if project:
        project_text = project.name
    elif intake.project_text:
        project_text = f"{intake.project_text} (not in project list"
        project_text += f"; location: {intake.location})" if intake.location else ")"
    else:
        project_text = f"Not given; location: {intake.location}" if intake.location else "-"

    caller = intake.caller_name or "-"
    if intake.organisation:
        caller += f", {intake.organisation}"

    summary = intake.summary or "No details given"
    notes = []
    if intake.wants_human:
        notes.append("asked to speak to staff")
    if intake.has_media:
        notes.append("sent a voice note or file, see the chat")
    if notes:
        summary += f" [{'; '.join(notes)}]"

    return [
        _clean(intake.caller_type),
        _clean(caller),
        _clean(project_text),
        _clean(intake.unit_no),
        _clean(reason_labels.get(intake.reason_category or "", intake.reason_category)),
        _clean(summary, limit=450),
        wa_link(intake.phone),
    ]


def alert_message(
    route: Route,
    intake: Intake,
    table: RoutingTable,
    reason_labels: dict[str, str],
    template: str,
    template_lang: str,
) -> Outbound:
    params = alert_params(intake, table, reason_labels)
    body = "New conveyancing enquiry\n" + "\n".join(
        f"{label}: {value}" for label, value in zip(ALERT_FIELDS, params)
    )
    return Outbound(
        to=route.staff.whatsapp,
        kind="template",
        body=body,  # plain-text version: used for logs, dry runs and as a fallback
        template=template,
        template_lang=template_lang,
        params=params,
        purpose="alert",
    )
