import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from schedule_gate import should_run

class ScheduleGate(unittest.TestCase):
    def test_daily_completion_and_manual_override(self):
        now = datetime(2026,11,22,10,43,tzinfo=timezone.utc)
        done = {"last_scheduled_completed_at":"2026-11-22T06:20:00+00:00"}
        self.assertFalse(should_run("schedule", done, now))
        self.assertTrue(should_run("workflow_dispatch", done, now))
        self.assertTrue(should_run("push", done, now))
    def test_missing_failed_yesterday_and_before_morning(self):
        now = datetime(2026,11,22,10,43,tzinfo=timezone.utc)
        for value in [None, "invalid", "2026-11-21T10:00:00+00:00", "2026-11-22T05:00:00+00:00"]:
            self.assertTrue(should_run("schedule", {"last_scheduled_completed_at":value}, now))
    def test_tbilisi_date_boundary(self):
        self.assertTrue(should_run("schedule", {"last_scheduled_completed_at":"2026-11-21T19:43:00+00:00"}, datetime(2026,11,22,6,13,tzinfo=timezone.utc)))
