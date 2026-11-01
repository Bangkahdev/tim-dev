"""Konfigurasi backend yang dibaca dari .env.

Nilai dibaca saat modul diimpor. Tes dapat menimpa lewat variabel lingkungan
sebelum mengimpor modul ini.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, str(default)))
    except ValueError:
        return default


def env_bool(key: str, default: bool = False) -> bool:
    value = env(key, "1" if default else "0").lower()
    return value in {"1", "true", "yes", "on"}


def _path(key: str, default: Path) -> Path:
    raw = env(key)
    return Path(raw).resolve() if raw else default


DATA_DIR = _path("BANGKAH_DATA_DIR", BASE_DIR / "data")
DB_PATH = _path("BANGKAH_DB_PATH", DATA_DIR / "bangkah.db")
PRINT_DIR = _path("BANGKAH_PRINT_DIR", DATA_DIR / "prints")
REPORT_DIR = _path("BANGKAH_REPORT_DIR", BASE_DIR / "reports")
WORKSPACE_DIR = _path("BANGKAH_WORKSPACE_DIR", BASE_DIR / "workspace" / "projects")
DOCS_DIR = _path("BANGKAH_DOCS_DIR", BASE_DIR / "docs")

HOST = env("BANGKAH_HOST", "127.0.0.1")
PORT = env_int("BANGKAH_PORT", 8765)

API_AUTH_TOKEN = env("API_AUTH_TOKEN")
OWNER_SESSION_HOURS = max(1, env_int("OWNER_SESSION_HOURS", 8))
APPROVAL_TTL_HOURS = max(1, env_int("APPROVAL_TTL_HOURS", 24))
MAX_REPAIR_ROUNDS = max(0, env_int("MAX_REPAIR_ROUNDS", 3))
MAX_CONCURRENT_PROJECTS = max(1, env_int("MAX_CONCURRENT_PROJECTS", 2))
DAILY_TOKEN_BUDGET = max(0, env_int("DAILY_TOKEN_BUDGET", 0))

EVENT_RETENTION_HOURS = max(1, env_int("EVENT_RETENTION_HOURS", 24))
EVENT_RETENTION_COUNT = max(100, env_int("EVENT_RETENTION_COUNT", 10_000))
PAPER_TRAY_LIMIT = max(1, env_int("PAPER_TRAY_LIMIT", 15))
MAX_REQUEST_BYTES = max(1_000, env_int("MAX_REQUEST_BYTES", 64_000))

# Email / website: hanya dibaca backend, tidak pernah diteruskan ke subprocess.
EMAIL_ADDRESS = env("EMAIL_ADDRESS")
EMAIL_PASSWORD = env("EMAIL_PASSWORD")
EMAIL_IMAP_HOST = env("EMAIL_IMAP_HOST")
EMAIL_SMTP_HOST = env("EMAIL_SMTP_HOST")
EMAIL_SEND_LIMIT_PER_DAY = max(0, env_int("EMAIL_SEND_LIMIT_PER_DAY", 50))
WEBSITE_URL = env("WEBSITE_URL")
WEBSITE_DEPLOY_TOKEN = env("WEBSITE_DEPLOY_TOKEN")

# Model per peran. Nilai ini hanya nama model, bukan kunci API.
MODEL_GROUPS = {
    "MANAGER": env("MODEL_MANAGER", "ollama/qwen2.5-coder:1.5b"),
    "CODER": env("MODEL_CODER", "ollama/qwen2.5-coder:1.5b"),
    "SPECIALIST": env("MODEL_SPECIALIST", "ollama/llama3.2:3b"),
}
MODEL_SECRETARY = env("MODEL_SECRETARY", MODEL_GROUPS["MANAGER"])


def model_for_role(role: str) -> str:
    group = {
        "lead": "MANAGER",
        "coo": "MANAGER",
        "secretary": "MANAGER",
        "promo_manager": "MANAGER",
        "architect": "CODER",
        "backend": "CODER",
        "frontend": "CODER",
        "promo_writer": "CODER",
        "promo_social": "CODER",
        "api": "SPECIALIST",
        "qa": "SPECIALIST",
        "receptionist": "SPECIALIST",
    }.get(role, "SPECIALIST")
    override = env(f"MODEL_{role.upper()}")
    if role == "secretary":
        return override or MODEL_SECRETARY
    return override or MODEL_GROUPS.get(group, MODEL_GROUPS["SPECIALIST"])


def ensure_directories() -> None:
    for directory in (DATA_DIR, PRINT_DIR, REPORT_DIR, WORKSPACE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def secret_values() -> set[str]:
    """Nilai rahasia yang tidak boleh bocor ke log, prompt, atau subprocess."""
    names = (
        "API_AUTH_TOKEN",
        "EMAIL_PASSWORD",
        "WEBSITE_DEPLOY_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
    )
    return {env(name) for name in names if env(name)}
