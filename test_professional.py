import sqlite3, tempfile, unittest
from pathlib import Path
from professional import OperationLock, ensure_failure_schema, estimate_work, record_failure, export_failures

class ProfessionalTests(unittest.TestCase):
    def test_second_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            first=OperationLock(Path(d)); second=OperationLock(Path(d))
            self.assertTrue(first.acquire()); self.assertFalse(second.acquire()); first.release()
    def test_estimate_and_failure_export(self):
        self.assertEqual(estimate_work(10,6,0.5)["requests"],2)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); db=sqlite3.connect(root/"p.db"); ensure_failure_schema(db)
            record_failure(db,"k",'["a.jpg"]',"offline"); export_failures(db,root)
            self.assertIn("offline",(root/"error_report.csv").read_text(encoding="utf-8-sig"))

if __name__ == "__main__": unittest.main()
