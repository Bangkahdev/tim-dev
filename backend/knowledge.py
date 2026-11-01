"""Penyaringan dokumen knowledge (KNW-04).

Dokumen yang mengandung pola rahasia tidak boleh masuk indeks. Fungsi di sini
hanya melaporkan nama pola, tidak pernah mengembalikan nilai rahasia itu
sendiri, agar pesan error dan log tetap aman (P5, NFR-SEC-01).
"""

from __future__ import annotations

import re
from pathlib import Path

from .sandbox import redact

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key)\b\s*[=:]\s*['\"]?[A-Za-z0-9_\-./+]{12,}")),
    ("password", re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[=:]\s*['\"]?\S{6,}")),
    ("token", re.compile(r"(?i)\b(token|bearer)\b\s*[=:]\s*['\"]?[A-Za-z0-9_\-.]{12,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
)


class KnowledgeError(Exception):
    status_code = 422


def secret_kinds(text: str) -> list[str]:
    """Nama pola rahasia yang ditemukan; tidak pernah berisi nilainya."""
    value = str(text or "")
    return [name for name, pattern in SECRET_PATTERNS if pattern.search(value)]


def contains_secrets(text: str) -> bool:
    return bool(secret_kinds(text))


def assert_safe(text: str) -> None:
    kinds = secret_kinds(text)
    if kinds:
        raise KnowledgeError(
            "Dokumen mengandung pola rahasia dan ditolak (KNW-04): "
            + ", ".join(kinds)
        )


def file_has_secrets(path: Path) -> bool:
    try:
        return contains_secrets(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False


def safe_snippet(text: str, *, start: int, end: int) -> str:
    return redact(text[start:end])
