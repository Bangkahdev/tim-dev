import os
import tempfile
import unittest
from pathlib import Path

from core.office_store import OfficeStore
from core.domain_service import DomainService


def _isolated_domain():
    root = Path(tempfile.mkdtemp())
    store = OfficeStore(root / "office.db")
    return root, DomainService(store)


class DomainServiceTests(unittest.TestCase):
    def setUp(self):
        self.root, self.domain = _isolated_domain()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _audit_events(self):
        with self.domain.store._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id").fetchall()]

    def test_initial_state_is_internal_dns_not_managed(self):
        state = self.domain.state()
        self.assertEqual(state["domain_name"], "bangkah.my.id")
        self.assertEqual(state["ou_path"], "OU=Workstations,DC=bangkah,DC=my,DC=id")
        self.assertFalse(state["internal_dns_managed"])
        self.assertEqual(state["joined_count"], 0)
        self.assertEqual(state["dns_record_count"], 10)

    def test_join_domain_activates_internal_dns_and_audits(self):
        result = self.domain.join_domain("PC-BE-001", "owner")
        self.assertEqual(result["workstation_id"], "PC-BE-001")
        self.assertEqual(result["domain"], "bangkah.my.id")
        state = self.domain.state()
        self.assertTrue(state["internal_dns_managed"])
        self.assertEqual(state["joined_count"], 1)
        events = self._audit_events()
        self.assertIsNotNone(events)
        join_events = [e for e in events if e["event_type"] == "domain_join"]
        self.assertEqual(len(join_events), 1)
        self.assertEqual(join_events[0]["actor"], "owner")
        self.assertEqual(join_events[0]["entity_id"], "PC-BE-001")

    def test_join_domain_is_idempotent(self):
        self.domain.join_domain("PC-BE-001", "owner")
        self.domain.join_domain("PC-BE-001", "owner")
        state = self.domain.state()
        self.assertEqual(state["joined_count"], 1)
        join_events = [e for e in self._audit_events() if e["event_type"] == "domain_join"]
        self.assertEqual(len(join_events), 2)

    def test_join_domain_requires_id(self):
        with self.assertRaises(ValueError):
            self.domain.join_domain("")

    def test_dns_lookup_seeded_records(self):
        record = self.domain.dns_lookup("OWNER-PC-001.bangkah.my.id")
        self.assertIsNotNone(record)
        self.assertEqual(record["type"], "A")
        self.assertEqual(record["value"], "127.0.0.1")
        self.assertEqual(record["source"], "internal")

    def test_dns_lookup_case_insensitive(self):
        upper = self.domain.dns_lookup("OWNER-PC-001.BANGKAH.MY.ID")
        lower = self.domain.dns_lookup("owner-pc-001.bangkah.my.id")
        self.assertEqual(upper, lower)

    def test_dns_lookup_unknown_returns_none(self):
        self.assertIsNone(self.domain.dns_lookup("tidakada.bangkah.my.id"))

    def test_dns_records_list(self):
        records = self.domain.dns_records()
        self.assertEqual(len(records), 10)
        names = {r["name"] for r in records}
        self.assertIn("dc", names)
        self.assertIn("bangkah.my.id", names)

    def test_add_dns_record(self):
        record = self.domain.add_dns_record("apps.bangkah.my.id", "CNAME", "dc.bangkah.my.id", "owner")
        self.assertEqual(record["type"], "CNAME")
        self.assertEqual(record["value"], "dc.bangkah.my.id")
        self.assertEqual(record["source"], "admin")
        lookup = self.domain.dns_lookup("apps.bangkah.my.id")
        self.assertIsNotNone(lookup)
        events = [e for e in self._audit_events() if e["event_type"] == "dns_record_added"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["actor"], "owner")

    def test_add_dns_record_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            self.domain.add_dns_record("", "A", "1.2.3.4")
        with self.assertRaises(ValueError):
            self.domain.add_dns_record("x.b", "AAAA", "1.2.3.4")


if __name__ == "__main__":
    unittest.main()
