"""Optional subprocess sandbox wrapper (operator-configured, best-effort).

Set BANGKAH_SANDBOX_CMD to an argv prefix that provides OS/container isolation,
e.g. (conceptually) a container runtime with --network none and only the
project directory mounted. The token {project_dir} is replaced with the
resolved project directory. Example shape (operator must supply a real image
and correct mounts): docker run --rm --network none -v {project_dir}:/work
-w /work <image>

This module does NOT claim NFR-SEC-09/10 met. Isolation is only real if the
configured wrapper actually confines filesystem and network access.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Sequence

SANDBOX_CMD_ENV = "BANGKAH_SANDBOX_CMD"
PROJECT_DIR_TOKEN = "{project_dir}"


def sandbox_wrapper(source: dict | None = None) -> list[str]:
    src = os.environ if source is None else source
    raw = str(src.get(SANDBOX_CMD_ENV, "") or "").strip()
    if not raw:
        return []
    return shlex.split(raw)


def wrap_argv(argv: Sequence[str], project_dir: str | Path, source: dict | None = None) -> list[str]:
    argv = list(argv)
    prefix = sandbox_wrapper(source)
    if not prefix:
        return argv
    project_dir = str(Path(project_dir).resolve())
    prefix = [p.replace(PROJECT_DIR_TOKEN, project_dir) for p in prefix]
    return prefix + argv
