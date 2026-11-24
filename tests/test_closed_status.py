import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from radar import apply_result
class ClosedStatusRegression(unittest.TestCase):
    def test_missing_preserves_closed_and_archived(self):
        for status in ("closed", "archived"):
            record = {"id": "reviewed", "status": status}
            history = []
            apply_result(record, "missing", "2026-11-24T08:00:00Z", "HTTP 404", "https://example.com/job", history)
            self.assertEqual(record["status"], status)
            self.assertEqual(history[-1]["outcome"], "missing")
            self.assertNotIn("last_verified_at", record)
