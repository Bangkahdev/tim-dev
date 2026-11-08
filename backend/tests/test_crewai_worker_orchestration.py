"""Orchestration tests for CrewAIAgentWorker (no real LLM calls).

A fake subclass replaces only ``_run_task`` with canned file content. Everything
else is exercised for real: content cleaning, AST validation, safe path writes,
the public unittest command, the public spec probe, and the advisory review.
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import business_cycle  # noqa: E402
from core.business_cycle import CrewAIAgentWorker  # noqa: E402

CORE = '''"""Pure counting logic for the wordcount CLI."""
from __future__ import annotations


def count_text(text: str) -> dict:
    """Return line, word and character counts for *text*."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    lines = text.count("\\n") + (1 if text and not text.endswith("\\n") else 0)
    return {"lines": lines, "words": len(text.split()), "characters": len(text)}
'''

CLI = '''"""Command-line entry point for wordcount."""
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
'''

TESTS = '''"""Behavior tests for wordcount."""
import subprocess
import sys
import unittest
from pathlib import Path

from wordcount.core import count_text


class CountTextTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(count_text(""), {"lines": 0, "words": 0, "characters": 0})

    def test_no_trailing_newline(self):
        self.assertEqual(count_text("a b\\nc"), {"lines": 2, "words": 3, "characters": 5})

    def test_unicode_characters_not_bytes(self):
        self.assertEqual(count_text("halo café\\n")["characters"], 10)


class CliTests(unittest.TestCase):
    def run_cli(self, args, stdin_text=None):
        return subprocess.run(
            [sys.executable, "-m", "wordcount", *args],
            cwd=Path(__file__).resolve().parents[1],
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    def test_missing_file_exits_2(self):
        cp = self.run_cli(["does-not-exist.txt"])
        self.assertEqual(cp.returncode, 2)
        self.assertTrue(cp.stderr.strip())

    def test_missing_argument_exits_2(self):
        cp = self.run_cli([])
        self.assertEqual(cp.returncode, 2)
        self.assertTrue(cp.stderr.strip())


if __name__ == "__main__":
    unittest.main()
'''

BAD_TESTS = TESTS.replace(
    '{"lines": 0, "words": 0, "characters": 0}',
    '{"lines": 1, "words": 0, "characters": 0}',
)

FAKE_FILES = {
    "wordcount/__init__.py": '"""wordcount: small CLI utility used as the Milestone 1 pilot."""\n',
    "wordcount/core.py": CORE,
    "wordcount/cli.py": CLI,
    "wordcount/__main__.py": (
        '"""Run the wordcount CLI with `python -m wordcount`."""\n'
        "from .cli import main\n\n\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(main())\n"
    ),
    "README.md": "# wordcount\n\nUsage: `python -m wordcount <path|->`.\n",
    "tests/test_wordcount.py": TESTS,
}


def local_runner(project_dir, args, timeout=120, stdin_text=None):
    """Run the command locally without the operator sandbox for this unit test."""
    completed = subprocess.run(
        args, cwd=project_dir, input=stdin_text, capture_output=True, text=True,
        timeout=timeout, shell=False,
    )
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def local_runner_split(project_dir, args, timeout=120, stdin_text=None):
    completed = subprocess.run(
        args, cwd=project_dir, input=stdin_text, capture_output=True, text=True,
        timeout=timeout, shell=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


class FakeWorker(CrewAIAgentWorker):
    def _run_task(self, role, goal, backstory, description, expected_output, model):
        if role == "Lead Manager / Reviewer":
            return "STATUS: PASS\nAll required files match the behavior spec."
        match = re.search(r"complete content of `([^`]+)`", description)
        if match is None:
            raise AssertionError(f"prompt did not name a file: {description[:200]}")
        return FAKE_FILES[match.group(1)]


BAD_CLI = CLI.replace(
    '    if args.path is None:\n'
    '        parser.error("the following arguments are required: path")',
    '    if args.path is None:\n'
    '        parser.print_help()\n'
    '        return 2',
)


class RepairingFakeWorker(CrewAIAgentWorker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.repaired = []

    def _run_task(self, role, goal, backstory, description, expected_output, model):
        if role == "Lead Manager / Reviewer":
            return "STATUS: PASS\nAll required files match the behavior spec."
        if "CURRENT CONTENT OF tests/test_wordcount.py" in description:
            return TESTS
        match = re.search(r"complete content of `([^`]+)`", description)
        if match is None:
            raise AssertionError(f"prompt did not name a file: {description[:200]}")
        relative = match.group(1)
        return BAD_TESTS if relative == "tests/test_wordcount.py" else FAKE_FILES[relative]

    def _repair(self, relative, failure):
        self.repaired.append(relative)
        return super()._repair(relative, failure)


class CliRepairFakeWorker(CrewAIAgentWorker):
    """First CLI prints help to stdout for a missing arg; repair fixes stderr."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.repaired = []

    def _run_task(self, role, goal, backstory, description, expected_output, model):
        if role == "Lead Manager / Reviewer":
            return "STATUS: PASS\nAll required files match the behavior spec."
        if "CURRENT CONTENT OF wordcount/cli.py" in description:
            return CLI
        match = re.search(r"complete content of `([^`]+)`", description)
        if match is None:
            raise AssertionError(f"prompt did not name a file: {description[:200]}")
        relative = match.group(1)
        return BAD_CLI if relative == "wordcount/cli.py" else FAKE_FILES[relative]

    def _repair(self, relative, failure):
        self.repaired.append(relative)
        return super()._repair(relative, failure)


class CrewAIWorkerOrchestrationTests(unittest.TestCase):
    def test_worker_generates_validates_tests_and_probes_without_llm(self):
        spec_path = Path(__file__).resolve().parents[2] / "docs" / "specs" / "wordcount-behavior.md"
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td) / "pilot"
            with patch.object(business_cycle, "run_sandboxed", local_runner), \
                 patch.object(business_cycle, "run_sandboxed_split", local_runner_split):
                meta = FakeWorker(max_repair_rounds=1).produce(
                    project_dir, "Build wordcount", spec_path,
                )

            for relative in CrewAIAgentWorker.GENERATION_ORDER:
                self.assertTrue((project_dir / relative).is_file(), relative)
            self.assertIn("def count_text", (project_dir / "wordcount" / "core.py").read_text())
            self.assertTrue(meta["public_tests_passed"])
            self.assertTrue(meta["public_spec_probe_passed"])
            self.assertTrue(meta["lead_review"].startswith("STATUS: PASS"))
            self.assertFalse((project_dir / ".selfcheck").exists(), "probe fixtures must be cleaned up")

    def test_bad_agent_tests_fall_back_to_spec_scaffold_without_touching_implementation(self):
        spec_path = Path(__file__).resolve().parents[2] / "docs" / "specs" / "wordcount-behavior.md"
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td) / "pilot"
            worker = RepairingFakeWorker(max_repair_rounds=2)
            with patch.object(business_cycle, "run_sandboxed", local_runner), \
                 patch.object(business_cycle, "run_sandboxed_split", local_runner_split):
                meta = worker.produce(project_dir, "Build wordcount", spec_path)

            self.assertTrue(meta["public_tests_passed"])
            self.assertEqual(
                meta["tests_source"],
                "worker_spec_scaffold_after_agent_tests_failed",
            )
            self.assertEqual(worker.repaired, [])
            self.assertIn("def count_text", (project_dir / "wordcount" / "core.py").read_text())
            self.assertIn("class CliTests", (project_dir / "tests" / "test_wordcount.py").read_text())

    def test_probe_requires_stderr_and_repairs_cli(self):
        spec_path = Path(__file__).resolve().parents[2] / "docs" / "specs" / "wordcount-behavior.md"
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td) / "pilot"
            worker = CliRepairFakeWorker(max_repair_rounds=2)
            with patch.object(business_cycle, "run_sandboxed", local_runner), \
                 patch.object(business_cycle, "run_sandboxed_split", local_runner_split):
                meta = worker.produce(project_dir, "Build wordcount", spec_path)

            self.assertTrue(meta["public_tests_passed"])
            self.assertIn("wordcount/cli.py", worker.repaired)
            self.assertIn("parser.error", (project_dir / "wordcount" / "cli.py").read_text())

    def test_clean_content_extracts_a_fenced_block(self):
        raw = "Here is the file:\n```python\nprint('hi')\n```\nDone."
        self.assertEqual(CrewAIAgentWorker._clean_content(raw), "print('hi')\n")

    def test_repair_target_rules(self):
        self.assertEqual(
            CrewAIAgentWorker._choose_repair_target("spec_probe.missing_arg: rc=0"),
            "wordcount/cli.py",
        )
        self.assertEqual(
            CrewAIAgentWorker._choose_repair_target("AssertionError: {'lines': 1}"),
            "wordcount/core.py",
        )
        self.assertEqual(
            CrewAIAgentWorker._choose_repair_target("NameError in tests/test_wordcount.py"),
            "tests/test_wordcount.py",
        )


if __name__ == "__main__":
    unittest.main()
