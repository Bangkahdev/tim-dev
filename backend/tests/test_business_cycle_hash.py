import hashlib, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.business_cycle import BusinessCycle, run_sandboxed
from core.company_operations import CompanyOperations
from core.office_store import OfficeStore

class EvidenceHashTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.ops = CompanyOperations(OfficeStore(self.root / "office.db"))
        self.ws = self.root / "projects"

    def test_run_tests_records_output_sha256(self):
        bc = BusinessCycle(self.ops, workspace_root=self.ws)
        (self.ws / "p" / "tests").mkdir(parents=True)
        (self.ws / "p" / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (self.ws / "p" / "tests" / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n",
            encoding="utf-8")
        # use real runner on this tiny project
        res = bc._run_tests(self.ws / "p")
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["output_sha256"], hashlib.sha256(res["output"].encode("utf-8","replace")).hexdigest())
        art = (self.ws / "p" / res["artifact"]).read_text(encoding="utf-8")
        self.assertIn("exit_code: 0", art)
        self.assertIn("sha256:", art)
        self.assertIn(res["output_sha256"], art)

if __name__ == "__main__":
    unittest.main()
