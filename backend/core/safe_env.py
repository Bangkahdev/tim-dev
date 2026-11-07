"""Lingkungan (environment) aman untuk subprocess yang dijalankan agen AI.

Subprocess agen tidak boleh mewarisi rahasia backend (kunci API, password SMTP,
token deploy, token API). Hanya variabel dalam allowlist yang diteruskan.
"""
from __future__ import annotations

import os
from typing import Mapping

ALLOWED_KEYS = frozenset(
    {
        "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
        "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
        "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL",
        "LC_CTYPE", "TERM", "TZ", "NODE_PATH", "NPM_CONFIG_CACHE",
        "PYTHONIOENCODING", "VIRTUAL_ENV",
    }
)


def safe_subprocess_env(
    extra: Mapping[str, str] | None = None,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Kembalikan env minimal untuk subprocess agen (allowlist, bukan blocklist)."""
    src = os.environ if source is None else source
    env = {key: value for key, value in src.items() if key.upper() in ALLOWED_KEYS}
    env.update(extra or {})
    return env
