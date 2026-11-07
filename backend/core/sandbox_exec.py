"""Subprocess sandbox wrapper configuration (operator-configured).

Set BANGKAH_SANDBOX_CMD to an argv prefix that provides OS/container isolation,
e.g. (conceptually) a container runtime with --network none and only the
project directory mounted. The token {project_dir} is replaced with the
resolved project directory. Example shape (operator must supply a real image
and correct mounts): docker run --rm --network none -v {project_dir}:/work
-w /work <image>

This module does NOT claim NFR-SEC-09/10 met. Isolation is only real if the
configured wrapper actually confines filesystem and network access.

BANGKAH_SANDBOX_REQUIRED=1 makes missing/misconfigured sandbox fail-closed:
command execution is rejected and an audit/warning is emitted by callers.
"""
from __future__ import annotations

import logging
import os
import shlex
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

SANDBOX_CMD_ENV = "BANGKAH_SANDBOX_CMD"
SANDBOX_REQUIRED_ENV = "BANGKAH_SANDBOX_REQUIRED"
PROJECT_DIR_TOKEN = "{project_dir}"


class SandboxConfigurationError(RuntimeError):
    """Raised when sandbox execution cannot satisfy configured requirements."""


def sandbox_required(source: dict | None = None) -> bool:
    src = os.environ if source is None else source
    raw = str(src.get(SANDBOX_REQUIRED_ENV, "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def sandbox_wrapper(source: dict | None = None) -> list[str]:
    src = os.environ if source is None else source
    raw = str(src.get(SANDBOX_CMD_ENV, "") or "").strip()
    if not raw:
        return []
    return shlex.split(raw)


def sandbox_status(source: dict | None = None) -> dict:
    required = sandbox_required(source)
    raw = str((os.environ if source is None else source).get(SANDBOX_CMD_ENV, "") or "")
    configured = bool(raw.strip())
    error = None
    wrapper = []
    if configured:
        try:
            wrapper = sandbox_wrapper(source)
        except Exception as exc:  # shlex/config parse errors
            error = f"invalid {SANDBOX_CMD_ENV}: {exc}"
            wrapper = []
    if required and not wrapper:
        error = error or f"{SANDBOX_REQUIRED_ENV}=1 but {SANDBOX_CMD_ENV} is empty or misconfigured"
    return {
        "required": required,
        "configured": configured,
        "active": bool(wrapper),
        "wrapper_argv": wrapper,
        "error": error,
    }


def wrap_argv(argv: Sequence[str], project_dir: str | Path, source: dict | None = None) -> list[str]:
    argv = list(argv)
    prefix = sandbox_wrapper(source)
    if not prefix:
        return argv
    project_dir = str(Path(project_dir).resolve())
    prefix = [p.replace(PROJECT_DIR_TOKEN, project_dir) for p in prefix]
    return prefix + argv


def enforce_sandbox(argv: Sequence[str], project_dir: str | Path, source: dict | None = None) -> list[str]:
    """Return argv wrapped by configured sandbox, or raise when required+missing.

    Callers MUST use this (not best-effort wrap_argv) for execution paths that
    must honor BANGKAH_SANDBOX_REQUIRED.
    """
    argv = list(argv)
    status = sandbox_status(source)
    if status["error"]:
        logger.warning("sandbox enforcement: %s", status["error"])
        if status["required"]:
            raise SandboxConfigurationError(status["error"])
        return argv
    if not status["active"]:
        return argv
    project_dir = str(Path(project_dir).resolve())
    prefix = [p.replace(PROJECT_DIR_TOKEN, project_dir) for p in status["wrapper_argv"]]
    return prefix + argv
