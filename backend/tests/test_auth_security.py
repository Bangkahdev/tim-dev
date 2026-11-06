import os, tempfile, unittest
from pathlib import Path
from core.office_store import OfficeStore
from core.auth.sessions import create_user
import core.auth.authentication as A

class AuthSecurityTests(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        os.environ["BANGKAH_DB_PATH"] = str(root / "office.db")
        from core.office_store import STORE
        with STORE._db() as db:
            db.execute("DELETE FROM auth_users WHERE username='owner'")
        create_user("owner","pass","owner")
    def test_login_wrong(self):
        self.assertIsNone(A.login("owner","bad"))
    def test_login_ok(self):
        r = A.login("owner","pass")
        self.assertIsNotNone(r)
        self.assertTrue(A.current_user(r["token"]) is not None)
    def test_revoked(self):
        r = A.login("owner","pass")
        A.logout(r["token"])
        self.assertIsNone(A.current_user(r["token"]))

if __name__ == "__main__":
    unittest.main()
