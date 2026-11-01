"""Lingkungan subprocess agen yang disaring (NFR-SEC-02, NFR-SEC-09/10).

Allowlist executable tetap berlaku, tetapi bukan satu-satunya pertahanan.
Fungsi di sini menyaring env dan, di POSIX, memasang batas resource. Untuk
isolasi jaringan penuh, jalankan backend di container dengan kebijakan proxy
allowlist per proyek; dokumentasi ada di README.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Iterable

from . import settings

ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
    "PYTHONUNBUFFERED", "PYTHONIOENCODING", "PYTHONDONTWRITEBYTECODE",
}

ALLOWED_EXECUTABLES = {
    "python", "python3", "py", "pytest", "node", "npm", "npx", "git", "uv",
    "pip", "pip3", "ruff", "mypy",
}

FORBIDDEN_ARGUMENTS = {
    "rm", "rmdir", "del", "format", "shutdown", "reboot", "sudo", "su",
    "chmod", "chown", "mkfs", "curl", "wget", "ssh", "scp", "nc",
}


def safe_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in ENV_ALLOWLIST
    }
    env.setdefault("PYTHONUNBUFFERED", "1")
    if extra:
        for key, value in extra.items():
            if key.upper() not in ENV_ALLOWLIST:
                continue
            env[key] = value
    return env


def validate_command(command: str) -> list[str]:
    try:
        args = shlex.split(command)
    except ValueError as error:
        raise ValueError(f"Perintah tidak dapat diurai: {error}") from error
    if not args:
        raise ValueError("Perintah kosong.")
    executable = Path(args[0]).name.lower()
    if executable not in ALLOWED_EXECUTABLES:
        raise ValueError(f"Executable tidak diizinkan: {executable}")
    for argument in args:
        name = Path(argument).name.lower()
        if name in FORBIDDEN_ARGUMENTS:
            raise ValueError("Perintah berbahaya ditolak.")
        if re.search(r"[;&|`$><\r\n]", argument):
            raise ValueError("Metakarakter shell ditolak.")
        if ".." in Path(argument).parts:
            raise ValueError("Path traversal ditolak.")
    return args


def _limits() -> None:  # pragma: no cover - POSIX only
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, 1_500_000_000))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except (ImportError, ValueError, OSError):
        pass


def run_command(
    command: str,
    *,
    cwd: str | Path,
    timeout: int = 120,
    extra_env: dict[str, str] | None = None,
) -> dict:
    args = validate_command(command)
    kwargs = {
        "args": args,
        "cwd": str(cwd),
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "shell": False,
        "env": safe_env(extra_env),
    }
    if os.name == "posix":
        kwargs["preexec_fn"] = _limits
    result = subprocess.run(**kwargs)
    output = (result.stdout or "") + (result.stderr or "")
    return {
        "exit_code": result.returncode,
        "output": redact(output[-12000:]),
        "command": command,
    }


def redact(text: str, extra_secrets: Iterable[str] | None = None) -> str:
    value = str(text or "")
    secrets = set(settings.secret_values())
    if extra_secrets:
        secrets.update(secret for secret in extra_secrets if secret)
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(api[_-]?key|password|token)\s*[=:]\s*\S+", r"\1=[REDACTED]", value)
