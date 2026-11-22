"""Avoid repeated source downloads after today's scheduled check completed."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Asia/Tbilisi")

def should_run(event, status, now):
    if event != "schedule":
        return True
    value = status.get("last_scheduled_completed_at")
    try:
        previous = datetime.fromisoformat(value).astimezone(ZONE)
    except (TypeError, ValueError):
        return True
    local = now.astimezone(ZONE)
    return not (previous.date() == local.date() and previous.hour >= 10)

if __name__ == "__main__":
    status = json.loads(Path("dist/data/update-status.json").read_text())
    due = should_run(os.getenv("GITHUB_EVENT_NAME"), status, datetime.now(ZONE))
    message = "Run source checks" if due else "Today's scheduled check already completed; no source requests"
    print(message)
    with open(os.environ["GITHUB_OUTPUT"], "a") as out:
        out.write("due=" + str(due).lower() + "\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
        out.write(message + "\n")
