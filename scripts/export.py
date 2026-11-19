"""Export the call log to CSV.

    python -m scripts.export                  # today's enquiries
    python -m scripts.export --date 2026-11-19
    python -m scripts.export --all
"""

import argparse
import csv
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.models import Intake
from app.db.session import make_session_factory
from app.routing.projects import RoutingTable
from app.settings import get_settings

COLUMNS = [
    "Date",
    "Time",
    "Caller number",
    "Caller type",
    "Caller name",
    "Firm / bank",
    "Project",
    "Unit no.",
    "Location",
    "Reason",
    "Summary",
    "Transferred to",
    "Status",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the call log to CSV")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--all", action="store_true", help="export every enquiry")
    parser.add_argument("--tz", default="Asia/Kuala_Lumpur")
    parser.add_argument("--out", help="output file (default: exports/call-log-<date>.csv)")
    args = parser.parse_args()

    settings = get_settings()
    tz = ZoneInfo(args.tz)
    table = RoutingTable.load(settings.projects_file)
    labels = {
        r["key"]: r["label"] for r in json.loads(settings.reasons_file.read_text(encoding="utf-8"))
    }

    query = select(Intake).where(Intake.status != "ignored").order_by(Intake.id)
    name = "all"
    if not args.all:
        day = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
        start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
        query = query.where(Intake.created_at >= start, Intake.created_at < start + timedelta(days=1))
        name = day.isoformat()

    out = Path(args.out) if args.out else Path("exports") / f"call-log-{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    with make_session_factory(settings.database_url)() as db:
        intakes = db.scalars(query).all()

    # utf-8-sig so Excel opens non-English text correctly
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for i in intakes:
            created = i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)
            local = created.astimezone(tz)
            project = table.get(i.project_key)
            writer.writerow(
                [
                    local.strftime("%Y-%m-%d"),
                    local.strftime("%H:%M"),
                    i.phone,
                    i.caller_type or "",
                    i.caller_name or "",
                    i.organisation or "",
                    project.name if project else (i.project_text or ""),
                    i.unit_no or "",
                    i.location or (project.location if project else ""),
                    labels.get(i.reason_category or "", ""),
                    i.summary or "",
                    i.routed_to_name or "",
                    i.status,
                ]
            )
    print(f"Wrote {len(intakes)} enquiries to {out}")


if __name__ == "__main__":
    main()
