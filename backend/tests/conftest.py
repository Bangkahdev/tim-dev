import os
import tempfile
from pathlib import Path

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="bangkah-tests-"))
os.environ["BANGKAH_DB_PATH"] = str(_TEST_ROOT / "office.db")
os.environ.setdefault("BANGKAH_SESSION_HOURS", "8")
os.environ.pop("BANGKAH_API_TOKEN", None)
os.environ.pop("BANGKAH_LEGACY_TOKEN_ROLE", None)
