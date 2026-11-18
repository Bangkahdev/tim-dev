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

import json
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Sequence

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


def _wrapper_binary_error(wrapper: list[str]) -> str | None:
    if not wrapper:
        return None
    binary = wrapper[0]
    # Absolute/relative paths must exist; bare command names must resolve on PATH.
    if os.path.sep in binary or (os.path.altsep and os.path.altsep in binary):
        if not Path(binary).exists():
            return f"sandbox wrapper binary not found: {binary}"
        return None
    if shutil.which(binary) is None:
        return f"sandbox wrapper binary not found on PATH: {binary}"
    return None


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
    if wrapper and PROJECT_DIR_TOKEN not in raw:
        error = error or f"{SANDBOX_CMD_ENV} must include {PROJECT_DIR_TOKEN} so the project directory is mounted/confined"
    if not error:
        error = _wrapper_binary_error(wrapper)
    if required and not wrapper:
        error = error or f"{SANDBOX_REQUIRED_ENV}=1 but {SANDBOX_CMD_ENV} is empty or misconfigured"
    return {
        "required": required,
        "configured": configured,
        "active": bool(wrapper) and not bool(error and required),
        "has_project_dir_token": PROJECT_DIR_TOKEN in raw,
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
    must honor BANGKAH_SANDBOX_REQUIRED. When required mode is active this also
    runs the cached isolation canaries, so a caller cannot bypass the canary
    check by using this function alone.
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
    if status["required"]:
        # Fail closed: required mode must not execute anything without
        # independent evidence that the wrapper isolates filesystem and network.
        ensure_sandbox_canaries(project_dir, source=source)
    project_dir = str(Path(project_dir).resolve())
    prefix = [p.replace(PROJECT_DIR_TOKEN, project_dir) for p in status["wrapper_argv"]]
    return prefix + argv


FS_CANARY_SCRIPT = r'''
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    data = p.read_text(encoding="utf-8", errors="replace")
    print(json.dumps({"ok": True, "leaked": True, "bytes": len(data)}))
except Exception as exc:
    print(json.dumps({"ok": True, "leaked": False, "error": type(exc).__name__}))
'''

NET_CANARY_SCRIPT = r'''
import json, socket
s = socket.socket()
s.settimeout(2)
try:
    s.connect(("1.1.1.1", 53))
    print(json.dumps({"ok": True, "leaked": True}))
except Exception as exc:
    print(json.dumps({"ok": True, "leaked": False, "error": type(exc).__name__}))
finally:
    try: s.close()
    except Exception: pass
'''


def _default_canary_runner(argv: list[str], project_dir: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=project_dir, capture_output=True, text=True, timeout=timeout, shell=False)


def _canary_payload(completed: subprocess.CompletedProcess) -> dict:
    """Parse the last canary JSON line without failing on short non-JSON output."""
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if not stdout.strip():
        return {"raw": "", "stderr": stderr[-500:]}
    try:
        value = json.loads(stdout.strip().splitlines()[-1])
    except Exception:
        return {"raw": stdout[-500:], "stderr": stderr[-500:]}
    if isinstance(value, dict):
        return value
    return {"raw": stdout[-500:], "stderr": stderr[-500:]}


def _canary_ran(payload: dict) -> bool:
    return isinstance(payload, dict) and payload.get("ok") is True and "leaked" in payload


def run_sandbox_canaries(
    project_dir: str | Path,
    source: dict | None = None,
    runner: Callable[[list[str], Path, int], subprocess.CompletedProcess] | None = None,
    sentinel_path: str | Path | None = None,
) -> dict:
    """Run isolation canaries through the configured sandbox wrapper.

    A required/validated sandbox must BLOCK both canaries:
    - filesystem: reading a sentinel file outside project_dir must fail
    - network: outbound TCP connect must fail inside the sandbox while the same
      probe succeeds outside the sandbox. If the control probe cannot reach the
      network, the result is inconclusive and treated as not isolated.
    If either canary leaks, required mode must be rejected.

    The wrapper is operator-controlled, so a wrapper that fabricates canary JSON
    can defeat these checks. Canaries are supporting evidence, not standalone
    proof of NFR-SEC-09/10.
    """
    project_dir = Path(project_dir).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    status = sandbox_status(source)
    result = {
        "required": status["required"],
        "configured": status["configured"],
        "wrapper": status.get("wrapper_argv", []),
        "status_error": status.get("error"),
        "fs_isolated": None,
        "network_isolated": None,
        "network_control_reachable": None,
        "ok": False,
        "details": {},
    }
    if status.get("error") or not status.get("active"):
        result["details"]["config"] = status.get("error") or "sandbox not active"
        return result

    run = runner or _default_canary_runner
    cleanup_sentinel = False
    if sentinel_path is None:
        fd, sp = tempfile.mkstemp(prefix="bangkah-sentinel-", suffix=".txt")
        os.close(fd)
        sentinel_path = Path(sp)
        sentinel_path.write_text("bangkah-outside-project-sentinel", encoding="utf-8")
        cleanup_sentinel = True
    else:
        sentinel_path = Path(sentinel_path).resolve()
    try:
        fs_argv = wrap_argv(["python", "-c", FS_CANARY_SCRIPT, str(sentinel_path)], project_dir, source)
        fs = run(fs_argv, project_dir, 30)
        fs_payload = _canary_payload(fs)
        leaked_fs = bool(fs_payload.get("leaked")) if isinstance(fs_payload, dict) else False
        fs_ran = _canary_ran(fs_payload)
        result["fs_isolated"] = bool(fs_ran and leaked_fs is False)
        result["details"]["filesystem"] = {"exit_code": fs.returncode, "payload": fs_payload, "ran": fs_ran}

        net_argv = wrap_argv(["python", "-c", NET_CANARY_SCRIPT], project_dir, source)
        net = run(net_argv, project_dir, 30)
        net_payload = _canary_payload(net)
        leaked_net = bool(net_payload.get("leaked")) if isinstance(net_payload, dict) else False
        net_ran = _canary_ran(net_payload)

        # Control probe: the same network check outside the sandbox. Without a
        # successful control, a blocked sandbox probe could simply mean the host
        # itself is offline, which proves nothing about wrapper isolation.
        control = run(["python", "-c", NET_CANARY_SCRIPT], project_dir, 30)
        control_payload = _canary_payload(control)
        control_ran = _canary_ran(control_payload)
        control_reachable = bool(control_ran and control_payload.get("leaked") is True)
        result["network_control_reachable"] = control_reachable
        result["details"]["network_control"] = {
            "exit_code": control.returncode,
            "payload": control_payload,
            "ran": control_ran,
            "reachable": control_reachable,
        }

        network_isolated = bool(net_ran and leaked_net is False and control_reachable)
        result["network_isolated"] = network_isolated
        network_details = {"exit_code": net.returncode, "payload": net_payload, "ran": net_ran}
        if net_ran and leaked_net is False and not control_reachable:
            network_details["inconclusive"] = True
            network_details["inconclusive_reason"] = (
                "control probe outside the sandbox could not reach 1.1.1.1:53; "
                "sandbox network isolation cannot be concluded"
            )
        result["details"]["network"] = network_details
    finally:
        if cleanup_sentinel:
            try:
                sentinel_path.unlink(missing_ok=True)
            except Exception:
                pass
    result["ok"] = bool(result["fs_isolated"] and result["network_isolated"])
    return result


_CANARY_CACHE: dict[tuple[str, str, str], dict] = {}


def clear_canary_cache() -> None:
    _CANARY_CACHE.clear()


def ensure_sandbox_canaries(
    project_dir: str | Path,
    source: dict | None = None,
    audit: Callable[[str, str, str, str | None], None] | None = None,
    runner: Callable[[list[str], Path, int], subprocess.CompletedProcess] | None = None,
    force: bool = False,
) -> dict:
    """Run canaries once per (wrapper config, project) and require isolation when required.

    ``audit`` signature: (event_type, actor, detail, entity_id).
    """
    project_dir = Path(project_dir).resolve()
    src = os.environ if source is None else source
    key = (str(src.get(SANDBOX_REQUIRED_ENV, "")), str(src.get(SANDBOX_CMD_ENV, "")), str(project_dir))
    if not force and key in _CANARY_CACHE:
        cached = _CANARY_CACHE[key]
        if sandbox_required(source) and not cached.get("ok"):
            raise SandboxConfigurationError(cached.get("details", {}).get("config") or "sandbox canaries failed")
        return cached
    result = run_sandbox_canaries(project_dir, source=source, runner=runner)
    _CANARY_CACHE[key] = result
    detail = json.dumps({k: result.get(k) for k in ("ok", "fs_isolated", "network_isolated", "status_error", "details")}, ensure_ascii=False, default=str)[:1800]
    if audit is not None:
        try:
            audit("sandbox_canary", "system", detail, str(project_dir))
        except Exception:
            logger.warning("failed to audit sandbox canary result")
    if sandbox_required(source):
        if result.get("status_error"):
            raise SandboxConfigurationError(result["status_error"])
        if not result.get("ok"):
            raise SandboxConfigurationError(f"sandbox canaries failed (NFR-SEC-09/10 not evidenced): {detail}")
    return result
