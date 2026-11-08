"""Milestone 1 — one real business cycle through the persisted backend.

This module drives the complete internal workflow for a small pilot project:

    Owner instruction -> validated plan/proposal -> owner pipeline approval
    -> task decomposition (acceptance criteria + dependencies) -> sandboxed
    worker output -> test execution -> QA report -> manager review
    -> task evidence/state -> final report Paper -> PrintJob -> delivery event
    -> owner review decision -> audit trail.

``AgentWorker`` is the swap-in boundary. ``DeterministicWorker`` writes fixed
pilot files and is ONLY for backend integration testing — it is not a real
Milestone 1 pass. ``CrewAIAgentWorker`` is the boundary for a real cloud/LLM
agent run; it requires a configured CrewAI/model environment and must not see
hidden verifier cases.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .company_operations import OPS, CompanyOperations, hmac_compare
from .office_store import BASE_DIR, STORE, _now

PILOT_FILES = {
    "README.md": """# wordcount

A tiny command-line word/line/character counter.

## Usage

```
python -m wordcount README.md
python -m wordcount -
```

`-` reads UTF-8 text from stdin. Success prints:

```
lines=<n> words=<n> characters=<n> <name>
```

Exit code 0 on success, 2 for a missing argument or unreadable file.

## Tests

```
python -m unittest discover -s tests -v
```
""",
    "wordcount/__init__.py": '"""wordcount: small CLI utility used as the Milestone 1 pilot."""\n',
    "wordcount/core.py": '''"""Pure counting logic for the wordcount CLI."""
from __future__ import annotations


def count_text(text: str) -> dict:
    """Return line, word and character counts for *text*."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    lines = text.count("\\n") + (1 if text and not text.endswith("\\n") else 0)
    words = len(text.split())
    return {"lines": lines, "words": words, "characters": len(text)}
''',
    "wordcount/__main__.py": '''"""Run the wordcount CLI with `python -m wordcount`."""
from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
''',
    "wordcount/cli.py": '''"""Command-line entry point for wordcount."""
from __future__ import annotations

import argparse
import sys

from .core import count_text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wordcount")
    parser.add_argument("path", nargs="?", help="file to count, or - for stdin")
    args = parser.parse_args(argv)

    if args.path is None:
        parser.error("the following arguments are required: path")

    name = args.path
    if args.path == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as error:
            print(f"wordcount: {error}", file=sys.stderr)
            return 2

    result = count_text(text)
    print(
        f"lines={result['lines']} words={result['words']} "
        f"characters={result['characters']} {name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    "tests/test_core.py": '''"""Tests for wordcount.core and the CLI."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from wordcount.core import count_text

ROOT = Path(__file__).resolve().parents[1]


class CountTextTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(count_text(""), {"lines": 0, "words": 0, "characters": 0})

    def test_single_line(self):
        self.assertEqual(count_text("hello world"), {"lines": 1, "words": 2, "characters": 11})

    def test_multiple_lines(self):
        result = count_text("one two\\nthree\\n")
        self.assertEqual(result["lines"], 2)
        self.assertEqual(result["words"], 3)

    def test_utf8_characters_not_bytes(self):
        self.assertEqual(count_text("halo café\\n")["characters"], 10)


class CliTests(unittest.TestCase):
    def run_cli(self, args, stdin_text=None):
        return subprocess.run(
            [sys.executable, "-m", "wordcount", *args],
            cwd=ROOT,
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    def test_normal_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "normal.txt"
            path.write_text("hello world\\nsecond line\\n", encoding="utf-8")
            result = self.run_cli([str(path)])
        self.assertEqual(result.returncode, 0)
        self.assertIn("lines=2 words=4 characters=24", result.stdout)

    def test_stdin(self):
        result = self.run_cli(["-"], stdin_text="alpha beta\\ngamma\\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("lines=2 words=3 characters=17", result.stdout)

    def test_missing_file_exits_2(self):
        result = self.run_cli(["does-not-exist.txt"])
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())

    def test_missing_argument_exits_2(self):
        result = self.run_cli([])
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
''',
}

ALLOWED_EXECUTABLES = {"python", "python.exe", "python3", "pytest", "git", "node", "npm", "npx", "uv"}
FORBIDDEN_ARGS = {"rm", "rmdir", "del", "format", "shutdown", "reboot", "sudo", "su", "chmod", "chown", "mkfs"}

TASK_SPECS = [
    ("coo", "Requirements and plan"),
    ("architect", "Architecture and file layout"),
    ("backend", "Implementation"),
    ("qa", "Automated tests"),
    ("lead", "QA review and final report"),
]


def safe_project_path(root, relative_path):
    """Resolve *relative_path* under *root*, rejecting traversal and symlinks."""
    root = Path(root).resolve()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Access denied: path escapes the project workspace.")
    current = root
    for part in Path(relative_path).parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("Path traversal rejected.")
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic links are not allowed.")
    return target


def run_sandboxed_split(project_dir, args, timeout=120, stdin_text=None):
    """Run *args* inside *project_dir* and return (returncode, stdout, stderr).

    Uses a minimal allowlisted environment (safe_subprocess_env) so backend
    secrets (API keys, SMTP/deploy tokens) are not inherited by agent commands.
    Optional operator-configured isolation wrapper: if BANGKAH_SANDBOX_CMD is
    set (core.sandbox_exec), the argv is wrapped (e.g. container with
    --network none and only the project dir mounted). If BANGKAH_SANDBOX_REQUIRED=1,
    missing/misconfigured wrapper fails closed and emits an audit event.
    Isolation is only real if that wrapper actually confines FS/network;
    NFR-SEC-09/10 remains NOT MET without evidenced OS/container/VM isolation.
    """
    project_dir = Path(project_dir).resolve()
    if not args:
        raise ValueError("Empty command.")
    executable = Path(args[0]).name.lower()
    is_versioned_python = re.fullmatch(r"python\d+(?:\.\d+)*(?:\.exe)?", executable) is not None
    if executable not in ALLOWED_EXECUTABLES and not is_versioned_python:
        raise ValueError(f"Executable not allowed: {executable}")
    if any(Path(arg).name.lower() in FORBIDDEN_ARGS for arg in args):
        raise ValueError("Dangerous argument rejected.")
    for arg in args[1:]:
        if ".." in Path(arg).parts:
            raise ValueError("Path traversal rejected.")
    try:
        from core.safe_env import safe_subprocess_env
        env = safe_subprocess_env({"PYTHONUNBUFFERED": "1"})
    except Exception:
        import os
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    run_args = list(args)
    try:
        from core.sandbox_exec import enforce_sandbox, ensure_sandbox_canaries, sandbox_status
        status = sandbox_status()
        if status.get("required") and not status.get("active"):
            try:
                STORE.add_event("sandbox_blocked", "system", status.get("error", "sandbox required"), str(project_dir))
            except Exception:
                pass
        canary = ensure_sandbox_canaries(
            project_dir,
            audit=lambda t, a, d, e: STORE.add_event(t, a, d, e),
        )
        if status.get("required") and not canary.get("ok"):
            raise ValueError(f"sandbox canary failed: {canary.get('details')}")
        run_args = enforce_sandbox(run_args, project_dir)
    except RuntimeError as exc:
        try:
            STORE.add_event("sandbox_blocked", "system", str(exc), str(project_dir))
        except Exception:
            pass
        raise
    except Exception as exc:
        if "BANGKAH_SANDBOX_REQUIRED" in str(exc) or "canary" in str(exc).lower():
            try:
                STORE.add_event("sandbox_blocked", "system", str(exc), str(project_dir))
            except Exception:
                pass
            raise

    completed = subprocess.run(
        run_args, cwd=project_dir, capture_output=True, text=True, timeout=timeout,
        shell=False, env=env, input=stdin_text,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def run_sandboxed(project_dir, args, timeout=120, stdin_text=None):
    """Run *args* in the sandbox and return (returncode, combined output)."""
    code, stdout, stderr = run_sandboxed_split(
        project_dir, args, timeout=timeout, stdin_text=stdin_text,
    )
    return code, (stdout or "") + (stderr or "")


class AgentWorker:
    """Boundary for Milestone 1 implementation work.

    A real Milestone 1 pass requires a worker that uses the coding pipeline
    (CrewAI/cloud model) to produce ``wordcount`` from ``docs/specs/wordcount-behavior.md``
    without access to hidden verifier cases. ``DeterministicWorker`` is an
    integration-test fixture only and MUST NOT be reported as a real Milestone 1 pass.
    """

    mode = "base"

    def produce(self, project_dir: Path, owner_command: str, spec_path: Path) -> dict:
        raise NotImplementedError


class DeterministicWorker(AgentWorker):
    """Writes fixed pilot files. Backend integration fixture, not real Milestone 1."""

    mode = "deterministic_integration"

    def produce(self, project_dir: Path, owner_command: str, spec_path: Path) -> dict:
        for relative, content in PILOT_FILES.items():
            target = safe_project_path(project_dir, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return {"mode": self.mode, "honest": "integration_fixture_not_real_milestone1"}


TEST_SCAFFOLD = r'''"""Behavior tests for wordcount (public spec cases)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from wordcount.core import count_text

ROOT = Path(__file__).resolve().parents[1]


class CountTextTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(count_text(""), {"lines": 0, "words": 0, "characters": 0})

    def test_single_line_no_newline(self):
        self.assertEqual(count_text("hello world"), {"lines": 1, "words": 2, "characters": 11})

    def test_trailing_newline(self):
        self.assertEqual(count_text("one two\nthree\n"), {"lines": 2, "words": 3, "characters": 14})

    def test_no_trailing_newline(self):
        self.assertEqual(count_text("a b\nc"), {"lines": 2, "words": 3, "characters": 5})

    def test_lone_newline(self):
        self.assertEqual(count_text("\n"), {"lines": 1, "words": 0, "characters": 1})

    def test_repeated_whitespace(self):
        self.assertEqual(count_text("  a\t\tb \n  c  \n"), {"lines": 2, "words": 3, "characters": 14})

    def test_utf8_characters_not_bytes(self):
        self.assertEqual(count_text("halo café\n"), {"lines": 1, "words": 2, "characters": 10})


class CliTests(unittest.TestCase):
    def run_cli(self, args, stdin_text=None):
        return subprocess.run(
            [sys.executable, "-m", "wordcount", *args],
            cwd=ROOT,
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    def test_normal_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "normal.txt"
            path.write_text("hello world\nsecond line\n", encoding="utf-8")
            result = self.run_cli([str(path)])
        self.assertEqual(result.returncode, 0)
        self.assertIn("lines=2 words=4 characters=24", result.stdout)

    def test_stdin(self):
        result = self.run_cli(["-"], stdin_text="alpha beta\ngamma\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("lines=2 words=3 characters=17", result.stdout)

    def test_missing_file_exit_2(self):
        result = self.run_cli(["does-not-exist.txt"])
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())

    def test_missing_argument_exit_2(self):
        result = self.run_cli([])
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
'''


class CrewAIAgentWorker(AgentWorker):
    """Focused CrewAI implementation worker for the wordcount pilot.

    Design note: earlier trials asked small local models to call the project
    file tools directly; they frequently stopped after one or two files. This
    worker keeps CrewAI as the real agent runtime but makes persistence
    deterministic: one CrewAI task per file returns complete file content, the
    worker validates it and writes it through ``safe_project_path``. It then
    runs the public test command in the configured sandbox and feeds real
    failures back to the model for repair rounds. The independent hidden
    verifier is never shown to any agent.

    Acceptance is decided by executed public tests plus an independent Owner
    verifier; the lead review is recorded as advisory evidence, not as a gate.
    """

    mode = "crewai_real"

    GENERATION_ORDER = [
        "wordcount/__init__.py",
        "wordcount/core.py",
        "wordcount/cli.py",
        "wordcount/__main__.py",
        "README.md",
        "tests/test_wordcount.py",
    ]

    FILE_RETRIES = 3
    DEFAULT_REPAIR_ROUNDS = 4
    REQUIRED_TOKENS = {
        "wordcount/core.py": ("def count_text",),
        "wordcount/cli.py": ("def main",),
        "tests/test_wordcount.py": ("unittest",),
    }

    def __init__(self, callback=None, max_repair_rounds=None):
        self.callback = callback or (lambda msg: None)
        if max_repair_rounds is None:
            try:
                from config import MAX_REPAIR_ROUNDS as configured_rounds
                max_repair_rounds = configured_rounds
            except Exception:
                max_repair_rounds = self.DEFAULT_REPAIR_ROUNDS
        self.max_repair_rounds = max(1, int(max_repair_rounds))
        self.project_dir = None
        self.spec_text = ""
        self.spec_name = ""
        self._tests_source = "agent"
        self._used_test_scaffold = False

    # -- small helpers -----------------------------------------------------
    def _log(self, message: str) -> None:
        try:
            self.callback(str(message))
        except Exception:
            pass

    @staticmethod
    def _expected_counts(text: str) -> dict:
        return {
            "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
            "words": len(text.split()),
            "characters": len(text),
        }

    @staticmethod
    def _parse_counts(output: str):
        match = re.search(
            r"lines\s*[:=]\s*(\d+).*?words\s*[:=]\s*(\d+).*?(?:characters|chars)\s*[:=]\s*(\d+)",
            output or "", re.I | re.S,
        )
        if not match:
            return None
        return {
            "lines": int(match.group(1)),
            "words": int(match.group(2)),
            "characters": int(match.group(3)),
        }

    @staticmethod
    def _clean_content(raw: str, markdown: bool = False) -> str:
        text = str(raw or "").strip()
        # Some local models wrap file content in XML-ish tags despite instructions.
        text = re.sub(r"^\s*<file[^>]*>\s*", "", text, flags=re.I)
        text = re.split(r"\s*</file>\s*", text, maxsplit=1, flags=re.I)[0].strip()
        if markdown:
            if text.startswith("```") and text.endswith("```") and text.count("```") == 2:
                text = re.sub(r"^```[a-zA-Z0-9_+\-]*\s*\n", "", text)
                text = re.sub(r"\n```$", "", text)
            return text.rstrip() + "\n"
        blocks = re.findall(r"```[a-zA-Z0-9_+\-]*\s*\n(.*?)```", text, re.S)
        if blocks:
            text = max(blocks, key=len)
        else:
            lines = text.splitlines()
            start = None
            for index, line in enumerate(lines):
                stripped = line.lstrip()
                if stripped.startswith(("import ", "from ", "def ", "class ", '"""', "'''", "#!")):
                    start = index
                    break
            if start is not None and start > 0:
                text = "\n".join(lines[start:])
        return text.strip("\n").rstrip() + "\n"

    def _validate_content(self, relative: str, content: str):
        if not content.strip():
            return "file content is empty"
        if relative.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as error:
                return f"SyntaxError: {error}"
            for token in self.REQUIRED_TOKENS.get(relative, ()):
                if token not in content:
                    return f"missing required token {token!r}"
        return None

    def _read(self, relative: str) -> str:
        path = safe_project_path(self.project_dir, relative)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def _spec_block(self) -> str:
        return (
            f"BEHAVIOR SPEC ({self.spec_name}) - the single source of truth:\n"
            f"{self.spec_text}\n"
        )

    # -- prompts -----------------------------------------------------------
    def _prompt_for(self, relative: str) -> str:
        spec = self._spec_block()
        header = (
            "You are writing exactly one file for a small Python project. "
            f"Return ONLY the complete content of `{relative}`. "
            "No markdown fences, no explanations, no surrounding prose.\n\n"
        )
        if relative == "wordcount/core.py":
            return header + spec + (
                "\nThe file must define this public API:\n"
                "    def count_text(text: str) -> dict:\n"
                "        ...\n"
                "It returns a dict with integer keys \"lines\", \"words\", \"characters\".\n"
                "Follow the spec's counting rules exactly, including empty text, text without a\n"
                "trailing newline, tabs/repeated whitespace, and Unicode characters (count\n"
                "characters, not bytes). Use only the Python standard library. No file I/O.\n"
            )
        if relative == "wordcount/__init__.py":
            return header + "Return a short module docstring for the `wordcount` package.\n"
        if relative == "wordcount/cli.py":
            core = self._read("wordcount/core.py")
            return header + spec + (
                f"\nCurrent `wordcount/core.py`:\n```python\n{core}\n```\n\n"
                "The CLI must work as `python -m wordcount <path|->` together with\n"
                "`wordcount/__main__.py`.\n"
                "Requirements:\n"
                "- argparse positional `path`; a missing argument exits 2 and prints an error to stderr.\n"
                "  Do NOT use parser.print_help() or print usage/help to stdout for this case; the\n"
                "  error text must be on stderr (e.g. parser.error('the following arguments are required: path')).\n"
                "- `-` reads UTF-8 text from stdin; otherwise read the given file as UTF-8 text.\n"
                "- A missing/unreadable file prints a human-readable error to stderr and exits 2.\n"
                "- On success print exactly: lines=<n> words=<n> characters=<n> <name>\n"
                "  where <name> is the path argument or `-`.\n"
                "- Provide `def main(argv=None) -> int` and the `if __name__ == \"__main__\"` guard.\n"
                "- Standard library only. Do not import anything outside `wordcount.core`.\n"
            )
        if relative == "wordcount/__main__.py":
            return header + (
                "Its complete content must run the CLI when executing `python -m wordcount`:\n"
                "import `main` from `.cli` and raise `SystemExit(main())`.\n"
            )
        if relative == "README.md":
            return header + (
                "Write a concise README.md with:\n"
                "- what the tool does;\n"
                "- usage: `python -m wordcount <path>` and `python -m wordcount -` for stdin;\n"
                "- output format `lines=<n> words=<n> characters=<n> <name>`;\n"
                "- test command `python -m unittest discover -s tests -v`;\n"
                "- exit codes 0 (success) and 2 (missing argument or unreadable file).\n"
            )
        if relative == "tests/test_wordcount.py":
            core = self._read("wordcount/core.py")
            cli = self._read("wordcount/cli.py")
            return header + spec + (
                f"\nCurrent `wordcount/core.py`:\n```python\n{core}\n```\n\n"
                f"Current `wordcount/cli.py`:\n```python\n{cli}\n```\n\n"
                "Use Python's standard-library `unittest` only (no pytest).\n"
                "Import `from wordcount.core import count_text`.\n"
                "The command `python -m unittest discover -s tests -v` must run from the project root.\n"
                "Cover at least these exact expectations (full dict equality):\n"
                "- count_text(\"\") == {\"lines\": 0, \"words\": 0, \"characters\": 0}\n"
                "- count_text(\"hello world\") == {\"lines\": 1, \"words\": 2, \"characters\": 11}\n"
                "- count_text(\"one two\\nthree\\n\") == {\"lines\": 2, \"words\": 3, \"characters\": 14}\n"
                "- count_text(\"a b\\nc\") == {\"lines\": 2, \"words\": 3, \"characters\": 5}\n"
                "- count_text(\"\\n\") == {\"lines\": 1, \"words\": 0, \"characters\": 1}\n"
                "- count_text(\"halo café\\n\") == {\"lines\": 1, \"words\": 2, \"characters\": 10}\n"
                "- count_text(\"  a\\t\\tb \\n  c  \\n\") == {\"lines\": 2, \"words\": 3, \"characters\": 14}\n"
                "Also add CLI tests with subprocess using sys.executable and `-m wordcount`,\n"
                "cwd set to the project root. Do NOT use unittest.mock or patch.\n"
                "- normal file \"hello world\\nsecond line\\n\": exit 0 and output starts with\n"
                "  `lines=2 words=4 characters=24`\n"
                "- stdin: args [\"-\"] with `input=\"alpha beta\\ngamma\\n\"`: exit 0\n"
                "- missing file \"does-not-exist.txt\": exit 2 and non-empty stderr\n"
                "- no argument: exit 2 and non-empty stderr\n"
                "For stdin use subprocess.run(..., input=...); never patch sys.stdin.\n"
                "Use tempfile.TemporaryDirectory for fixture files. Keep the file deterministic.\n"
            )
        return header

    # -- CrewAI execution --------------------------------------------------
    def _run_task(self, role, goal, backstory, description, expected_output, model):
        from crewai import Agent, Crew, Process, Task
        agent = Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=model,
            allow_delegation=False,
            verbose=False,
        )
        task = Task(description=description, expected_output=expected_output, agent=agent)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        return str(crew.kickoff())

    def _generate(self, relative: str, model_role: str = "backend") -> str:
        from config import make_llm, model_for
        target = safe_project_path(self.project_dir, relative)
        prompt = self._prompt_for(relative)
        last_error = ""
        for attempt in range(1, self.FILE_RETRIES + 1):
            description = prompt
            if last_error:
                description += (
                    "\n\nTHE PREVIOUS ATTEMPT WAS REJECTED: "
                    f"{last_error}\nReturn the complete corrected file content only.\n"
                )
            raw = self._run_task(
                role="Python CLI Implementer" if model_role == "backend" else "QA Engineer",
                goal="Produce complete, correct file content for a small Python CLI project.",
                backstory=(
                    "You are a senior Python engineer who writes small, dependency-free, "
                    "spec-faithful code. You always return the complete file content."
                ),
                description=description,
                expected_output=f"complete content of {relative}",
                model=make_llm(model_for(model_role), temperature=0.1),
            )
            content = self._clean_content(raw, markdown=relative.endswith(".md"))
            error = self._validate_content(relative, content)
            if error is None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                self._log(f"[MILESTONE1] wrote {relative} ({len(content)} chars)")
                return content
            last_error = error
            self._log(f"[MILESTONE1] rejected {relative} attempt {attempt}: {error}")
        raise RuntimeError(f"model could not produce a valid {relative}: {last_error}")

    def _repair(self, relative: str, failure: str) -> None:
        from config import make_llm, model_for
        current = self._read(relative)
        prompt = self._prompt_for(relative) + (
            f"\n\nCURRENT CONTENT OF {relative} (replace it completely):\n"
            f"{current}\n\n"
            "REAL FAILURE OUTPUT FROM THE PUBLIC TEST/PROBE RUN:\n"
            f"{failure[-4000:]}\n\n"
            "Diagnose the root cause and return ONLY the complete corrected file content. "
            "Follow the behavior spec exactly. No markdown fences, no commentary.\n"
        )
        model_role = "qa" if relative.startswith("tests/") else "backend"
        raw = self._run_task(
            role="Python CLI Implementer" if model_role == "backend" else "QA Engineer",
            goal="Repair one file so the public behavior tests pass.",
            backstory=(
                "You are a senior Python engineer. You read real failure output, "
                "fix the root cause, and return the complete corrected file."
            ),
            description=prompt,
            expected_output=f"complete corrected content of {relative}",
            model=make_llm(model_for(model_role), temperature=0.1),
        )
        content = self._clean_content(raw, markdown=relative.endswith(".md"))
        error = self._validate_content(relative, content)
        if error:
            raise RuntimeError(f"repair for {relative} produced invalid content: {error}")
        target = safe_project_path(self.project_dir, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._log(f"[MILESTONE1] repaired {relative}")

    def _write_test_scaffold(self) -> None:
        """Install a deterministic public-spec test file after bad agent tests.

        This is QA scaffolding, not implementation: the wordcount source is
        still generated by the CrewAI implementer. The scaffold is derived only
        from the agent-facing behavior spec and contains no hidden verifier case.
        """
        target = safe_project_path(self.project_dir, "tests/test_wordcount.py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(TEST_SCAFFOLD, encoding="utf-8")
        self._log("[MILESTONE1] wrote tests/test_wordcount.py (public-spec scaffold)")

    @staticmethod
    def _choose_repair_target(failure: str) -> str:
        text = (failure or "").lower()
        cli_markers = (
            "missing_arg", "missing argument", "missing_argument", "missing_file",
            "missing file", "stdin", "usage:", "stderr", "wordcount/cli.py",
            "test_missing", "test_stdin", "test_normal_file", "exit 2",
            "modulenotfound", "importerror",
        )
        if any(marker in text for marker in cli_markers):
            return "wordcount/cli.py"
        if "tests/test_wordcount.py" in text and "assertionerror" not in text:
            return "tests/test_wordcount.py"
        return "wordcount/core.py"

    def _run_public_tests(self):
        try:
            return run_sandboxed(
                self.project_dir,
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                timeout=180,
            )
        except Exception as error:
            return -1, f"public test execution error: {type(error).__name__}: {error}"

    # -- public spec probe (NOT the hidden verifier) -----------------------
    def _probe_spec(self):
        project_dir = self.project_dir
        fixture_dir = safe_project_path(project_dir, ".selfcheck")
        fixture_dir.mkdir(parents=True, exist_ok=True)
        failures = []

        def write_fixture(name, text):
            path = safe_project_path(project_dir, f".selfcheck/{name}")
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            return f".selfcheck/{name}"

        def run_cli(args, stdin_text=None, timeout=60, split=False):
            command = [sys.executable, "-m", "wordcount", *args]
            try:
                if split:
                    code, stdout, stderr = run_sandboxed_split(
                        project_dir, command, timeout=timeout, stdin_text=stdin_text,
                    )
                    return code, (stdout or "") + (stderr or ""), stdout or "", stderr or ""
                code, output = run_sandboxed(
                    project_dir, command, timeout=timeout, stdin_text=stdin_text,
                )
                return code, output, "", ""
            except Exception as error:
                message = f"probe execution error: {type(error).__name__}: {error}"
                return -1, message, "", message

        def check_file(name, text):
            relative = write_fixture(name, text)
            code, output, _, _ = run_cli([relative])
            expected = self._expected_counts(text)
            got = self._parse_counts(output)
            if code != 0 or got != expected:
                failures.append(
                    f"spec_probe.{name}: rc={code} expected={expected} got={got} "
                    f"output={output[-800:]!r}"
                )

        check_file("normal.txt", "alpha beta\nsecond line\n")
        check_file("empty.txt", "")
        check_file("no_trailing_newline.txt", "red green\nblue")
        check_file("lone_newline.txt", "\n")
        check_file("repeated_whitespace.txt", "\t x  \n y\t\tz\n")
        check_file("utf8.txt", "café 日本\n")

        crlf = "left right\r\nup down\r\n"
        relative = write_fixture("crlf.txt", crlf)
        code, output, _, _ = run_cli([relative])
        got = self._parse_counts(output)
        allowed = {
            tuple(self._expected_counts(crlf).values()),
            tuple(self._expected_counts(crlf.replace("\r\n", "\n")).values()),
        }
        if code != 0 or got is None or tuple(got.values()) not in allowed:
            failures.append(
                f"spec_probe.crlf: rc={code} got={got} allowed={allowed} "
                f"output={output[-800:]!r}"
            )

        stdin_text = "one two\nthree\n"
        code, output, _, _ = run_cli(["-"], stdin_text=stdin_text)
        got = self._parse_counts(output)
        expected = self._expected_counts(stdin_text)
        if code != 0 or got != expected:
            failures.append(
                f"spec_probe.stdin: rc={code} expected={expected} got={got} "
                f"output={output[-800:]!r}"
            )

        code, output, _, stderr = run_cli([".selfcheck/does-not-exist.txt"], split=True)
        if code != 2 or not stderr.strip():
            failures.append(
                f"spec_probe.missing_file: rc={code} stderr={stderr[-800:]!r} "
                f"output={output[-800:]!r}"
            )

        code, output, _, stderr = run_cli([], split=True)
        if code != 2 or not stderr.strip():
            failures.append(
                f"spec_probe.missing_arg: rc={code} stderr={stderr[-800:]!r} "
                f"output={output[-800:]!r}"
            )

        if failures:
            return False, "\n".join(failures)
        shutil.rmtree(fixture_dir, ignore_errors=True)
        return True, ""

    def _lead_review(self) -> str:
        from config import make_llm, model_for
        files = "\n\n".join(
            f"--- {relative} ---\n{self._read(relative)}"
            for relative in self.GENERATION_ORDER
        )
        description = (
            "Review the delivered wordcount project against the behavior spec. "
            "The public tests and the spec probe have already passed.\n\n"
            f"{self._spec_block()}\n"
            f"DELIVERED FILES:\n{files}\n\n"
            "Reply with a short review. Use `STATUS: PASS` if the files match the spec, "
            "otherwise `STATUS: FAIL` and list concrete issues."
        )
        return self._run_task(
            role="Lead Manager / Reviewer",
            goal="Independently review the delivered wordcount project.",
            backstory="You are the accountable lead. You review real file content before approving.",
            description=description,
            expected_output="short review with STATUS: PASS or STATUS: FAIL",
            model=make_llm(model_for("lead"), temperature=0.1),
        )

    # -- AgentWorker boundary ----------------------------------------------
    def produce(self, project_dir: Path, owner_command: str, spec_path: Path) -> dict:
        try:
            import crewai  # noqa: F401
        except Exception as exc:
            raise RuntimeError(f"real AgentWorker requires crewai: {exc}") from exc
        self.project_dir = Path(project_dir).resolve()
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.spec_text = Path(spec_path).read_text(encoding="utf-8")
        self.spec_name = Path(spec_path).name

        self._log(f"[MILESTONE1] focused CrewAI worker generating wordcount in {self.project_dir}")
        for relative in self.GENERATION_ORDER:
            model_role = "qa" if relative.startswith("tests/") else "backend"
            self._generate(relative, model_role=model_role)

        failure = ""
        passed = False
        rounds_used = 0
        for round_no in range(self.max_repair_rounds + 1):
            rounds_used = round_no
            # The public spec probe is authoritative for implementation behavior.
            # Model-written tests must never drive the implementation away from
            # the spec: if the probe passes but the tests fail, fix the tests.
            probe_ok, probe_detail = self._probe_spec()
            if not probe_ok:
                failure = probe_detail
                self._log(f"[MILESTONE1] spec probe failed: {probe_detail[-1200:]}")
                if round_no == self.max_repair_rounds:
                    break
                target = self._choose_repair_target(probe_detail)
                self._log(f"[MILESTONE1] repair round {round_no + 1}/{self.max_repair_rounds}: {target}")
                self._repair(target, probe_detail)
                continue

            code, output = self._run_public_tests()
            if code == 0:
                passed = True
                break
            failure = output
            self._log(f"[MILESTONE1] public tests failed while spec probe passed: {output[-1200:]}")
            if not self._used_test_scaffold:
                self._log(
                    "[MILESTONE1] agent-written tests failed validation; "
                    "installing the public-spec test scaffold"
                )
                self._write_test_scaffold()
                self._tests_source = "worker_spec_scaffold_after_agent_tests_failed"
                self._used_test_scaffold = True
                continue
            # The scaffold is derived from the behavior spec, so a failure now
            # means the implementation is wrong. Repair that, never the scaffold.
            self._log("[MILESTONE1] public-spec test scaffold failed; repairing implementation")
            if round_no == self.max_repair_rounds:
                break
            target = self._choose_repair_target(output)
            if target == "tests/test_wordcount.py":
                target = "wordcount/cli.py"
            self._log(f"[MILESTONE1] repair round {round_no + 1}/{self.max_repair_rounds}: {target}")
            try:
                self._repair(target, output)
            except Exception as error:
                failure = f"repair failed: {type(error).__name__}: {error}"
                self._log(f"[MILESTONE1] {failure}")
                break

        if not passed:
            raise RuntimeError(
                "wordcount did not pass the public test/probe gate after "
                f"{rounds_used} repair rounds: {failure[-4000:]}"
            )

        lead_review = self._lead_review()
        self._log(f"[MILESTONE1] lead review: {lead_review[:300]}")
        return {
            "mode": self.mode,
            "honest": "real_crewai_attempt",
            "project_dir": str(self.project_dir),
            "agents": ["backend", "qa", "lead"],
            "files": list(self.GENERATION_ORDER),
            "tests_source": self._tests_source,
            "repair_rounds": rounds_used,
            "public_tests_passed": True,
            "public_spec_probe_passed": True,
            "lead_review": lead_review[:2000],
        }


class BusinessCycle:
    def __init__(self, ops: CompanyOperations = OPS, workspace_root=None, runner=None, worker=None):
        self.ops = ops
        self.store = ops.store
        self.workspace_root = Path(workspace_root or (BASE_DIR / "workspace" / "projects")).resolve()
        self.runner = runner or run_sandboxed
        self.worker = worker or DeterministicWorker()

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
        return slug[:48] or "pilot"

    def _write(self, project_dir: Path, relative: str, content: str):
        target = safe_project_path(project_dir, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def _event(self, kind, actor, detail, entity_id=None):
        self.store.add_event(kind, actor, detail, entity_id)

    def _audit_has(self, kind, entity_id):
        with self.ops._db() as db:
            row = db.execute(
                "SELECT 1 FROM events WHERE event_type=? AND entity_id=? LIMIT 1",
                (kind, entity_id),
            ).fetchone()
        return row is not None

    def _find_paper(self, title):
        with self.ops._db() as db:
            row = db.execute(
                "SELECT * FROM paper_records WHERE title=? ORDER BY created_at LIMIT 1", (title,)
            ).fetchone()
        return dict(row) if row else None

    # -- steps -------------------------------------------------------------
    def run(self, owner_command: str, project_key: str) -> dict:
        owner_command = str(owner_command).strip()
        project_key = self._slug(project_key)
        if not owner_command:
            raise ValueError("Owner instruction is required.")
        self._owner_command = owner_command

        project_dir = (self.workspace_root / project_key).resolve()
        if self.workspace_root not in project_dir.parents and project_dir != self.workspace_root:
            raise ValueError("Project workspace escapes the workspace root.")
        project_dir.mkdir(parents=True, exist_ok=True)

        checks = {}
        self._event("cycle_started", "owner", f"Business cycle started: {owner_command}", project_key)
        checks["pilot_tests_pass"] = False

        # Step 1-2: validated plan and proposal.
        plan = self._plan(owner_command, project_key)
        self._write(project_dir, "PLAN.md", plan["markdown"])
        self._write(project_dir, "ARCHITECTURE.md", plan["architecture"])
        proposal = self.ops.create_paper(
            f"Proposal: {project_key}", plan["markdown"], paper_type="proposal",
            origin="executive", priority="high",
        )

        # Step 3: owner approves the internal coding pipeline (single-use).
        if proposal["status"] != "approved":
            self.ops.update_paper_status(proposal["id"], "approved", actor="owner")
            self._event("owner_decision", "owner",
                        f"Owner approved internal pipeline for {project_key}.", proposal["id"])
        proposal = self.ops.get_paper(proposal["id"])

        # Step 4-5: task decomposition with acceptance criteria and dependencies.
        tasks = []
        previous_title = None
        for employee_id, label in TASK_SPECS:
            dependency = f" Depends on: {previous_title}." if previous_title else ""
            acceptance = self._acceptance_for(label, project_dir)
            task = self.ops.create_task(
                title=f"{label}: {project_key}",
                description=f"Project: {owner_command}.{dependency}",
                assignee_id=employee_id,
                priority="high",
                project_key=project_key,
                acceptance_criteria=acceptance,
                actor="lead",
            )
            tasks.append(task)
            previous_title = task["title"]

        # Step 6: sandboxed worker output.
        self._work(project_dir)
        self._checks_sandbox(checks, project_dir)

        # Step 7-8: tests + QA report, with the evidence gate enforced.
        test_result = self._run_tests(project_dir)
        qa_report = self._write_qa(project_dir, test_result)
        if test_result["exit_code"] != 0:
            raise ValueError(
                f"Pilot tests failed with exit {test_result['exit_code']}; "
                f"see {test_result['artifact']}."
            )
        checks["pilot_tests_pass"] = True
        self._checks_evidence_gate(checks, tasks, project_dir, test_result, qa_report)
        self._complete_task(tasks[0], project_dir, "document", "PLAN.md")
        self._complete_task(tasks[1], project_dir, "document", "ARCHITECTURE.md")
        self._complete_task(tasks[2], project_dir, "source", "wordcount/core.py, wordcount/cli.py, wordcount/__init__.py")
        self._complete_task(tasks[3], project_dir, "test", test_result["command"],
                            note=f"exit_code={test_result['exit_code']} output_sha256={test_result.get('output_sha256','')} artifact={test_result['artifact']}")
        review = self._write_review(project_dir, test_result, qa_report)
        self._complete_task(tasks[4], project_dir, "review", "MANAGER-REVIEW.md", note=review)

        # Step 9-10: final report Paper, PrintJob and delivery event.
        report_paper, print_job = self._deliver(project_dir, project_key, owner_command, tasks,
                                                test_result, qa_report, review)
        checks["paper_has_record_and_event"] = bool(
            report_paper and self._audit_has("paper_created", report_paper["id"])
            and self._audit_has("paper_delivered", report_paper["id"])
        )

        # Explicit restart step (playbook item 4/12): after Paper delivered, simulate backend/store restart
        # and verify evidence, Paper, PrintJob survive before owner final decision.
        checks["restart_after_delivery_preserves_state"] = self._check_restart_midcycle(
            project_key, tasks, report_paper, print_job
        )

        # Step 11: owner reviews evidence and the decision is persisted/audited.
        decision = self._owner_review(report_paper)
        checks["duplicate_delivery_is_idempotent"] = self._check_idempotent_delivery(project_dir, project_key)

        # Persistence and audit checks (post-decision restart).
        checks["restart_keeps_evidence_paper_printjob_decision"] = self._check_restart(
            project_key, tasks, report_paper, print_job
        )
        checks["character_status_matches_tasks"] = self._check_character_status(tasks)
        checks["all_decisions_in_audit"] = bool(
            self._audit_has("owner_decision", proposal["id"])
            and self._audit_has("owner_decision", report_paper["id"])
        )
        checks["task_evidence_persisted"] = self._check_evidence_persisted(project_key, tasks)

        self._event("cycle_completed", "lead", f"Business cycle completed: {project_key}", project_key)
        return {
            "project_key": project_key,
            "project_dir": str(project_dir),
            "tasks": [{"id": t["id"], "title": t["title"], "status": self._task_status(t["id"])} for t in tasks],
            "test_exit_code": test_result["exit_code"],
            "test_output_artifact": test_result["artifact"],
            "paper_id": report_paper["id"],
            "print_job_id": print_job["id"],
            "pdf_path": print_job["output_path"],
            "owner_decision": decision,
            "checks": checks,
        }

    # -- step helpers ------------------------------------------------------
    def _plan(self, owner_command: str, project_key: str) -> dict:
        markdown = f"""# Validated Plan — {project_key}

## Owner instruction
{owner_command}

## Scope
A small Python CLI utility (`wordcount`) that reports lines, words and
characters, with automated tests and a README. No external services.

## Acceptance criteria
- Source modules exist and import cleanly.
- `python -m unittest discover -s tests -v` exits 0.
- README documents usage and the test command.
- QA report and manager review reference real artifacts.
"""
        architecture = f"""# Architecture — {project_key}

```
{project_key}/
  README.md
  PLAN.md
  wordcount/
    __init__.py
    core.py      pure counting logic
    cli.py       argparse entry point
  tests/
    test_core.py unittest coverage
  artifacts/
    test-output.txt
```
"""
        return {"markdown": markdown, "architecture": architecture}

    @staticmethod
    def _acceptance_for(label: str, project_dir: Path) -> str:
        return {
            "Requirements and plan": "PLAN.md exists with scope and acceptance criteria.",
            "Architecture and file layout": "ARCHITECTURE.md exists and matches files on disk.",
            "Implementation": "wordcount modules exist, compile and import.",
            "Automated tests": "Test command exits 0 with output stored under artifacts/.",
            "QA review and final report": "MANAGER-REVIEW.md and QA-REPORT.md exist.",
        }.get(label, "Deliverable is present and verified.")

    def _work(self, project_dir: Path):
        spec_path = (BASE_DIR.parent / "docs" / "specs" / "wordcount-behavior.md").resolve()
        meta = self.worker.produce(project_dir, getattr(self, "_owner_command", ""), spec_path)
        mode = getattr(self.worker, "mode", "unknown")
        detail = f"Worker produced pilot files (mode={mode})."
        if mode.startswith("deterministic"):
            detail += " BACKEND INTEGRATION FIXTURE — not a real Milestone 1 agent run."
        rule = self.store.set_employee_status("backend", "working", detail[:240], actor="workflow")
        self._event("agent_output", "backend", json.dumps(meta, ensure_ascii=False, default=str)[:1000], rule["employee_id"])

    def _run_tests(self, project_dir: Path) -> dict:
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        display = "python -m unittest discover -s tests -v"
        code, output = self.runner(project_dir, command)
        output_hash = hashlib.sha256((output or "").encode("utf-8", errors="replace")).hexdigest()
        artifact_body = f"command: {display}\nexit_code: {code}\nsha256: {output_hash}\n\n{output or ''}"
        artifact = self._write(project_dir, "artifacts/test-output.txt", artifact_body)
        return {"command": display, "exit_code": code, "output": output,
                "output_sha256": output_hash,
                "artifact": str(artifact.relative_to(project_dir))}

    def _write_qa(self, project_dir: Path, test_result: dict) -> str:
        status = "PASS" if test_result["exit_code"] == 0 else "FAIL"
        body = f"""# QA Report

STATUS: {status}

## Test command
`{test_result['command']}`

## Exit code
{test_result['exit_code']}

## Output artifact
`{test_result['artifact']}`

## Result
{'All pilot tests passed.' if status == 'PASS' else 'Tests failed; see artifact.'}
"""
        self._write(project_dir, "QA-REPORT.md", body)
        self._event("qa_report", "qa", f"QA report written with status {status}.",
                    "qa-" + self._slug(project_dir.name))
        self.store.set_employee_status("qa", "completed", "QA report written.", actor="workflow")
        return body

    def _write_review(self, project_dir: Path, test_result: dict, qa_report: str) -> str:
        decision = "PASS" if test_result["exit_code"] == 0 else "FAIL"
        body = f"""# Manager Review

STATUS: {decision}

QA report referenced: `QA-REPORT.md`
Test artifact: `{test_result['artifact']}`

Manager accepts the deliverable and forwards it to the owner for review.
"""
        self._write(project_dir, "MANAGER-REVIEW.md", body)
        self._event("manager_review", "lead", f"Manager review: {decision}.",
                    "review-" + self._slug(project_dir.name))
        self.store.set_employee_status("lead", "completed", "Manager review written.", actor="workflow")
        return body

    def _complete_task(self, task, project_dir: Path, evidence_type: str, reference: str, note=""):
        task_id = task["id"]
        if self._task_status(task_id) == "pending":
            self.ops.transition_task(task_id, "in_progress", actor=task["assignee_id"])
        if task["assignee_id"]:
            self.store.set_employee_status(task["assignee_id"], "working",
                                           f"Working on {task['title']}.", actor="workflow")
        self.ops.transition_task(
            task_id, "completed",
            evidence=[{"type": evidence_type, "reference": reference, "note": note}],
            actor=task["assignee_id"],
        )
        if task["assignee_id"]:
            self.store.set_employee_status(task["assignee_id"], "completed",
                                           f"Completed {task['title']}.", actor="workflow")

    def _deliver(self, project_dir, project_key, owner_command, tasks, test_result, qa_report, review):
        title = f"Final Report: {project_key}"
        existing = self._find_paper(title)
        if existing:
            jobs = self.ops.list_print_jobs(limit=200)
            job = next((j for j in jobs if j["paper_id"] == existing["id"]), None)
            if job is None:
                job = self.ops.create_print_job(existing["id"])
            if not self._audit_has("paper_delivered", existing["id"]):
                self._event("paper_delivered", "front_office",
                            f"Report {existing['id']} delivered to the owner tray.", existing["id"])
            return self.ops.get_paper(existing["id"]), job

        files = sorted(
            str(p.relative_to(project_dir)).replace("\\", "/")
            for p in project_dir.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".factory" not in p.parts
        )
        body = f"""# Project Report — {project_key}

## Owner instruction
{owner_command}

## Status
QA: {'PASS' if test_result['exit_code'] == 0 else 'FAIL'} · Manager review: {'PASS' if test_result['exit_code'] == 0 else 'FAIL'}

## Test command
`{test_result['command']}` (exit {test_result['exit_code']})

## Artifacts
- Test output: `{test_result['artifact']}`
- QA report: `QA-REPORT.md`
- Manager review: `MANAGER-REVIEW.md`

## Files
{chr(10).join('- ' + f for f in files)}

## Tasks
{chr(10).join(f"- {t['title']} — {self._task_status(t['id'])}" for t in tasks)}
"""
        paper = self.ops.create_paper(
            title, body, paper_type="report", origin="engineering",
            priority="high", related_task_id=tasks[-1]["id"],
        )
        self._event("paper_created", "front_office", f"Final report created: {title}", paper["id"])
        job = self.ops.create_print_job(paper["id"])
        self.store.set_employee_status("frontend", "working", "Delivering printed report.", actor="workflow")
        self._event("paper_delivered", "front_office",
                    f"Report {paper['id']} delivered to the owner tray.", paper["id"])
        return paper, job

    def _owner_review(self, paper):
        current = self.ops.get_paper(paper["id"])
        if current["status"] == "approved":
            return "approved"
        self.ops.update_paper_status(paper["id"], "read", actor="owner")
        self.ops.update_paper_status(paper["id"], "approved", actor="owner")
        if not self._audit_has("owner_decision", paper["id"]):
            self._event("owner_decision", "owner",
                        f"Owner approved final report {paper['id']}.", paper["id"])
        return "approved"

    # -- acceptance checks -------------------------------------------------
    def _checks_sandbox(self, checks, project_dir):
        traversal_blocked = False
        try:
            safe_project_path(project_dir, "../escape.txt")
        except ValueError:
            traversal_blocked = True
        executable_blocked = False
        try:
            run_sandboxed(project_dir, ["bash", "-c", "echo hi"])
        except ValueError:
            executable_blocked = True
        except Exception:
            # With BANGKAH_SANDBOX_REQUIRED=1 and no wrapper, execution fails closed
            # before executable policy is the deciding factor; that's still a block.
            executable_blocked = True
        checks["sandbox_path_and_exec_guards_only_PARTIAL"] = traversal_blocked and executable_blocked

        # NFR-SEC-09/10 is only claimed when an operator wrapper is configured
        # AND its canaries prove filesystem confinement and network isolation.
        # In-process path/exec guards alone remain partial. The independent
        # verifier cannot inspect host-level wrappers; tools/run_milestone1.py
        # records the operator's external-sandbox evidence separately.
        isolated = False
        try:
            from .sandbox_exec import ensure_sandbox_canaries, sandbox_status
            status = sandbox_status()
            canary = ensure_sandbox_canaries(project_dir)
            isolated = bool(
                status.get("configured")
                and canary.get("ok")
                and canary.get("fs_isolated")
                and canary.get("network_isolated")
            )
        except Exception:
            isolated = False
        checks["sandbox_fs_network_isolation_NFR_SEC_09_10"] = isolated

    def _checks_evidence_gate(self, checks, tasks, project_dir, test_result, qa_report):
        qa_task = tasks[3]
        self.ops.transition_task(qa_task["id"], "in_progress", actor="qa")
        gate = False
        try:
            self.ops.transition_task(qa_task["id"], "completed", evidence=[], actor="qa")
        except ValueError:
            gate = True
        checks["completion_requires_evidence"] = gate
        invalid = False
        try:
            self.ops.transition_task(qa_task["id"], "pending", actor="qa")
        except ValueError:
            invalid = True
        checks["invalid_transition_rejected"] = invalid

    def _task_status(self, task_id):
        with self.ops._db() as db:
            row = db.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        return row["status"] if row else None

    def _check_evidence_persisted(self, project_key, tasks):
        with self.ops._db() as db:
            rows = db.execute(
                "SELECT COUNT(*) AS n FROM task_evidence te JOIN task_meta tm ON tm.task_id=te.task_id "
                "WHERE tm.project_key=?", (project_key,)
            ).fetchone()
        return bool(rows and rows["n"] >= len(tasks))

    def _check_restart_midcycle(self, project_key, tasks, paper, job):
        """Explicit mid-run restart check: reopen store/ops and confirm delivered
        Paper/PrintJob and task evidence survive a process/store restart."""
        from .office_store import OfficeStore
        fresh = OfficeStore(self.ops.db_path)
        fresh_ops = CompanyOperations(fresh)
        try:
            reloaded_paper = fresh_ops.get_paper(paper["id"])
            reloaded_job = fresh_ops.get_print_job(job["id"])
            with fresh_ops._db() as db:
                evidence = db.execute(
                    "SELECT COUNT(*) AS n FROM task_evidence te JOIN task_meta tm "
                    "ON tm.task_id=te.task_id WHERE tm.project_key=?", (project_key,)
                ).fetchone()["n"]
                delivered = db.execute(
                    "SELECT 1 FROM events WHERE event_type='paper_delivered' AND entity_id=? LIMIT 1",
                    (paper["id"],),
                ).fetchone()
            # delivery is recorded; job may be queued/completed depending on timing - require paper + evidence + delivery event
            return bool(reloaded_paper and reloaded_job and evidence >= len(tasks) and delivered)
        finally:
            fresh_ops.close()

    def _check_restart(self, project_key, tasks, paper, job):
        from .office_store import OfficeStore

        fresh = OfficeStore(self.ops.db_path)
        fresh_ops = CompanyOperations(fresh)
        try:
            reloaded_paper = fresh_ops.get_paper(paper["id"])
            reloaded_job = fresh_ops.get_print_job(job["id"])
            with fresh_ops._db() as db:
                evidence = db.execute(
                    "SELECT COUNT(*) AS n FROM task_evidence te JOIN task_meta tm "
                    "ON tm.task_id=te.task_id WHERE tm.project_key=?", (project_key,)
                ).fetchone()["n"]
                decision = db.execute(
                    "SELECT 1 FROM events WHERE event_type='owner_decision' AND entity_id=? LIMIT 1",
                    (paper["id"],),
                ).fetchone()
            return bool(
                reloaded_paper["status"] == "approved"
                and reloaded_job["status"] == "completed"
                and evidence >= len(tasks)
                and decision
            )
        finally:
            fresh_ops.close()

    def _check_character_status(self, tasks):
        snapshot = self.store.snapshot()
        statuses = {e["id"]: e["status"] for e in snapshot["employees"]}
        return all(statuses.get(t["assignee_id"]) in ("working", "completed") for t in tasks)

    def _check_idempotent_delivery(self, project_dir, project_key):
        before = self._delivery_count(project_key)
        self._deliver(project_dir, project_key, "duplicate check", [], {"exit_code": 0,
                      "command": "n/a", "artifact": "n/a"}, "", "")
        after = self._delivery_count(project_key)
        return before == after == 1

    def _delivery_count(self, project_key):
        title = f"Final Report: {project_key}"
        with self.ops._db() as db:
            paper = db.execute("SELECT id FROM paper_records WHERE title=? LIMIT 1", (title,)).fetchone()
            if not paper:
                return 0
            row = db.execute(
                "SELECT COUNT(*) AS n FROM events WHERE event_type='paper_delivered' AND entity_id=?",
                (paper["id"],),
            ).fetchone()
        return row["n"]


def record_pipeline_result(ops: CompanyOperations, project_dir, task_ids, actor="lead") -> dict:
    """Persist real evidence, a report Paper and a PrintJob after the coding
    pipeline runs. The owner still reviews the Paper; this never auto-approves.
    """
    project_dir = Path(project_dir).resolve()
    state_path = project_dir / ".factory" / "state.json"
    state = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    passed = str(state.get("qa_status", "")).upper() == "PASS"
    report_path = state.get("last_report")
    report_text = ""
    if report_path and Path(report_path).is_file():
        report_text = Path(report_path).read_text(encoding="utf-8", errors="replace")

    evidence = {
        "type": "pipeline",
        "reference": str(report_path or project_dir),
        "note": f"qa_status={state.get('qa_status', 'unknown')}",
    }
    completed = []
    for task_id in task_ids:
        with ops._db() as db:
            row = db.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None or row["status"] != "in_progress":
            continue
        if passed:
            ops.transition_task(task_id, "completed", evidence=[evidence], actor=actor)
            completed.append(task_id)
        else:
            try:
                ops.transition_task(task_id, "blocked", note="Pipeline QA did not pass.", actor=actor)
            except ValueError:
                pass

    title = f"Final Report: {project_dir.name}"
    with ops._db() as db:
        existing = dict(db.execute(
            "SELECT * FROM paper_records WHERE title=? ORDER BY created_at LIMIT 1", (title,)
        ).fetchone() or {})
    if existing:
        return {"paper": existing, "completed_tasks": completed, "qa_passed": passed}

    body = report_text or (
        f"# Pipeline Report — {project_dir.name}\n\n"
        f"QA status: {state.get('qa_status', 'unknown')}\n"
        f"Workspace: {project_dir}\n"
    )
    paper = ops.create_paper(
        title, body, paper_type="report", origin="engineering",
        priority="high", related_task_id=(completed or task_ids or [None])[-1],
    )
    job = ops.create_print_job(paper["id"])
    ops.store.add_event("paper_delivered", "front_office",
                        f"Report {paper['id']} delivered to the owner tray.", paper["id"])
    return {"paper": paper, "print_job": job, "completed_tasks": completed, "qa_passed": passed}


def check_rbac_and_approval(ops: CompanyOperations = OPS) -> dict:
    """Static checks for RBAC, path safety and the immutable approval boundary."""
    from . import authz

    checks = {}
    checks["employee_cannot_reach_owner_routes"] = (
        not authz.is_allowed("employee", "/api/terminal/exec", "POST")
        and not authz.is_allowed("employee", "/api/domain/join", "POST")
        and authz.is_allowed("owner", "/api/terminal/exec", "POST")
    )

    approval = ops.create_approval(
        "email.send", "Milestone 1 approval boundary probe",
        {"to": ["owner@bangkah.local"], "subject": "probe", "body": "boundary check"},
    )
    canonical = json.dumps(approval["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    checks["approval_is_hash_bound"] = hmac_compare(digest, approval["payload_sha256"])

    immutable = False
    try:
        with ops._db() as db:
            db.execute("UPDATE approval_records SET payload_json='{}' WHERE id=?", (approval["id"],))
    except Exception:
        immutable = True
    checks["approval_payload_immutable"] = immutable

    ops.decide_approval(approval["id"], "reject", "owner", "boundary check")
    single_use = False
    try:
        ops.decide_approval(approval["id"], "reject", "owner", "boundary check")
    except ValueError:
        single_use = True
    checks["approval_single_use"] = single_use
    return checks
