import os
import tempfile
import unittest
from pathlib import Path

from core.office_store import OfficeStore
from core.workstations import DesktopOperations, DesktopError, DesktopAuthError


class WorkstationDesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = OfficeStore(root / "company.db")
        self.desktop = DesktopOperations(
            self.store,
            workspace_root=root / "workspace",
            owner_password="test-pass",
        )
        self.desktop.clear_login_throttle()

    def tearDown(self):
        self.tmp.cleanup()

    def _login(self, workstation="OWNER-PC-001", account="owner", password="test-pass"):
        return self.desktop.login(workstation, account, password)

    def test_catalog_seeds_owner_and_employee_workstations(self):
        workstations = {item["id"]: item for item in self.desktop.list_workstations()}
        self.assertEqual(len(workstations), 8)
        owner = workstations["OWNER-PC-001"]
        self.assertEqual(owner["account_id"], "owner")
        self.assertEqual(owner["room_id"], "owner")
        self.assertIn("PC-BE-001", workstations)

    def test_owner_login_returns_session_and_audits(self):
        session = self._login()
        self.assertIn("token", session)
        self.assertGreater(len(session["token"]), 20)
        self.assertEqual(session["workstation"]["id"], "OWNER-PC-001")
        self.assertEqual(session["account"]["role"], "owner")
        self.assertEqual(session["apps"], ["files", "terminal", "infrastructure", "company"])
        self.assertEqual(self.desktop.workstation("OWNER-PC-001")["status"], "online")
        events = self.desktop.audit(session["token"])
        self.assertTrue(any(e["event_type"] == "desktop_login" for e in events))

    def test_wrong_password_is_rejected_and_throttled(self):
        with self.assertRaisesRegex(DesktopError, "salah"):
            self._login(password="wrong")
        for _ in range(4):
            with self.assertRaises(DesktopError):
                self._login(password="wrong")
        with self.assertRaisesRegex(DesktopError, "Terlalu banyak"):
            self._login()
        self.desktop.clear_login_throttle()
        self.assertIn("token", self._login())

    def test_employee_account_is_assignable_and_active_by_default(self):
        session = self.desktop.login("PC-BE-001", "backend", self.desktop.employee_password("backend"))
        self.assertEqual(session["account"]["role"], "employee")
        self.assertEqual(session["apps"], ["files", "terminal", "company"])
        events = self.desktop.audit(session["token"])
        self.assertTrue(any(e["event_type"] == "desktop_login" for e in events))

    def test_employee_accounts_can_be_frozen_by_env(self):
        os.environ["BANGKAH_EMPLOYEE_ACCOUNTS"] = "0"
        try:
            frozen = DesktopOperations(self.store,
                                       workspace_root=Path(self.tmp.name) / "workspace-frozen",
                                       owner_password="test-pass")
            frozen.clear_login_throttle()
            with self.assertRaisesRegex(DesktopError, "tidak aktif"):
                frozen.login("PC-BE-001", "backend", "x")
        finally:
            # The frozen flags were persisted to the shared store; restore them so
            # later tests keep the default active state.
            os.environ.pop("BANGKAH_EMPLOYEE_ACCOUNTS", None)
            with self.desktop._db() as db:
                self.desktop._apply_employee_account_flags(db)

    def test_employee_credentials_file_is_written_and_chmodged(self):
        path = Path(self.tmp.name) / "employee_credentials.local"
        self.assertTrue(path.is_file())
        content = path.read_text(encoding="utf-8")
        self.assertIn("backend=", content)
        password = self.desktop.employee_password("backend")
        self.assertIn(f"backend={password}", content)
        if os.name == "nt":
            # Windows has no POSIX mode bits; presence of the file is the contract.
            self.assertTrue(path.is_file())
        else:
            self.assertEqual(oct(path.stat().st_mode)[-3:], "600")

    def test_account_must_match_workstation(self):
        with self.assertRaisesRegex(DesktopError, "tidak ditugaskan"):
            self.desktop.login("PC-BE-001", "owner", "test-pass")

    def test_session_state_and_close(self):
        token = self._login()["token"]
        state = self.desktop.session_state(token)
        self.assertEqual(state["session_id"], state["session_id"].upper())
        self.assertEqual(state["account"]["id"], "owner")
        self.desktop.close_session(token)
        with self.assertRaisesRegex(DesktopAuthError, "ditutup"):
            self.desktop.session_state(token)
        self.assertEqual(self.desktop.workstation("OWNER-PC-001")["status"], "offline")

    def test_expired_session_is_rejected(self):
        token = self._login()["token"]
        with self.desktop._db() as db:
            db.execute("UPDATE workstation_sessions SET expires_at='2000-01-01T00:00:00+00:00'")
        with self.assertRaisesRegex(DesktopAuthError, "berakhir"):
            self.desktop.session_state(token)

    def test_terminal_builtins_read_sandbox_files(self):
        token = self._login()["token"]
        pwd = self.desktop.run_command(token, "pwd")
        self.assertEqual(pwd["exit_code"], 0)
        self.assertTrue(pwd["stdout"].endswith("OWNER-PC-001"))
        self.assertEqual(self.desktop.run_command(token, "whoami")["stdout"].strip(), "owner")
        listing = self.desktop.run_command(token, "ls")
        self.assertIn("README.md", listing["stdout"])
        self.assertIn("docs/", listing["stdout"])
        cat = self.desktop.run_command(token, "cat README.md")
        self.assertIn("OWNER-PC-001", cat["stdout"])
        grep = self.desktop.run_command(token, "grep -i sandbox README.md")
        self.assertEqual(grep["exit_code"], 0)
        self.assertIn("sandbox", grep["stdout"].lower())

    def test_terminal_rejects_shell_metacharacters(self):
        token = self._login()["token"]
        with self.assertRaisesRegex(DesktopError, "Karakter shell"):
            self.desktop.run_command(token, "ls; rm -rf /")
        with self.assertRaisesRegex(DesktopError, "Karakter shell"):
            self.desktop.run_command(token, "cat README.md | whoami")

    def test_terminal_rejects_unknown_and_outside_commands(self):
        token = self._login()["token"]
        with self.assertRaisesRegex(DesktopError, "tidak tersedia"):
            self.desktop.run_command(token, "python --version")
        with self.assertRaisesRegex(DesktopError, "Path absolut"):
            self.desktop.run_command(token, "cat C:/Windows/win.ini")
        with self.assertRaisesRegex(DesktopError, "keluar dari folder"):
            self.desktop.run_command(token, "cat ../company.db")

    def test_terminal_rejects_when_no_token(self):
        with self.assertRaises(DesktopAuthError):
            self.desktop.run_command("", "ls")

    def test_files_are_scoped_to_the_workstation(self):
        token = self._login()["token"]
        listing = self.desktop.list_files(token, ".")
        names = {item["name"] for item in listing["entries"]}
        self.assertIn("README.md", names)
        self.assertIn("docs", names)
        self.desktop.write_file(token, "docs/plan.md", "# Plan\nShip the slice.\n")
        read = self.desktop.read_file(token, "docs/plan.md")
        self.assertIn("Ship the slice", read["content"])
        with self.assertRaisesRegex(DesktopError, "keluar dari folder"):
            self.desktop.read_file(token, "../company.db")
        with self.assertRaisesRegex(DesktopError, "Path absolut"):
            self.desktop.read_file(token, "C:/Windows/win.ini")
        with self.assertRaisesRegex(DesktopError, "Tipe file"):
            self.desktop.write_file(token, "payload.exe", "binary")
        with self.assertRaisesRegex(DesktopError, "64 KB"):
            self.desktop.write_file(token, "big.txt", "x" * (64 * 1024 + 1))

    def test_file_write_is_audited(self):
        token = self._login()["token"]
        self.desktop.write_file(token, "notes.txt", "updated\n")
        events = self.desktop.audit(token)
        self.assertTrue(any(e["event_type"] == "desktop_file_write" for e in events))

    def test_system_info_reports_domain_honestly(self):
        token = self._login()["token"]
        info = self.desktop.system_info(token)
        self.assertEqual(info["workstation"]["id"], "OWNER-PC-001")
        self.assertEqual(info["terminal"]["mode"], "sandboxed-argv")
        self.assertIn("terminal", info["apps"])
        self.assertFalse(info["integrations"]["domain"]["dns_managed"])
        self.assertFalse(info["integrations"]["domain"]["email_provisioned"])

    def test_routes_exist_in_server(self):
        source = Path(__file__).resolve().parents[1] / "office_server.py"
        text = source.read_text(encoding="utf-8")
        for route in ("/api/workstations", "/api/desktop/session", "/api/terminal/exec",
                      "/api/desktop/files", "/api/desktop/system"):
            self.assertIn(route, text)


if __name__ == "__main__":
    unittest.main()
