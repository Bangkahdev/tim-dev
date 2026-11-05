"""Konfigurasi terpusat. Semua pengaturan model dibaca dari file .env."""

import os
from pathlib import Path

from dotenv import load_dotenv
from crewai import LLM

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _env(key, default=""):
    return os.getenv(key, default).strip()


# ------------------------------------------------------------
# Pengaturan umum
# ------------------------------------------------------------

OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")

try:
    MAX_REPAIR_ROUNDS = max(0, int(_env("MAX_REPAIR_ROUNDS", "3")))
except ValueError:
    MAX_REPAIR_ROUNDS = 3

try:
    COMMAND_TIMEOUT = max(5, int(_env("COMMAND_TIMEOUT", "120")))
except ValueError:
    COMMAND_TIMEOUT = 120


# ------------------------------------------------------------
# Model per kelompok dan per karyawan
# ------------------------------------------------------------

GROUP_MODELS = {
    "MANAGER": _env("MODEL_MANAGER", "ollama/qwen2.5-coder:1.5b"),
    "CODER": _env("MODEL_CODER", "ollama/qwen2.5-coder:1.5b"),
    "SPECIALIST": _env("MODEL_SPECIALIST", "ollama/llama3.2:3b"),
}

ROLE_GROUP = {
    "lead": "MANAGER",
    "coo": "MANAGER",
    "architect": "CODER",
    "backend": "CODER",
    "frontend": "CODER",
    "api": "SPECIALIST",
    "qa": "SPECIALIST",
}


def model_for(role):
    """Model untuk satu karyawan.

    Urutan prioritas: MODEL_<ROLE> (contoh MODEL_BACKEND)
    lalu model kelompoknya (MANAGER / CODER / SPECIALIST).
    """
    override = _env(f"MODEL_{role.upper()}")
    return override or GROUP_MODELS[ROLE_GROUP[role]]


def is_local(model):
    return model.startswith("ollama/")


def make_llm(model, temperature=0.2):
    """Buat objek LLM CrewAI untuk model lokal (Ollama) maupun cloud."""
    if is_local(model):
        return LLM(
            model=model,
            base_url=OLLAMA_URL,
            temperature=temperature
        )

    # Model cloud: API key dibaca litellm dari environment (.env).
    return LLM(
        model=model,
        temperature=temperature
    )


def required_local_models():
    """Nama model Ollama (tanpa prefix) yang dipakai oleh semua karyawan."""
    models = {model_for(role) for role in ROLE_GROUP}

    return sorted(
        model.removeprefix("ollama/")
        for model in models
        if is_local(model)
    )


# ------------------------------------------------------------
# Pemeriksaan API key untuk model cloud
# ------------------------------------------------------------

PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
}


def missing_api_keys():
    """Daftar nama variabel API key yang dibutuhkan tetapi belum diisi."""
    missing = set()

    for role in ROLE_GROUP:
        model = model_for(role)

        if is_local(model):
            continue

        provider = model.split("/", 1)[0].lower()
        key_name = PROVIDER_KEYS.get(provider)

        if key_name and not os.getenv(key_name, "").strip():
            missing.add(key_name)

    return sorted(missing)
