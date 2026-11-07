"""White-box + self-test of the Owner verifier (tools/verify_milestone1.py).

Builds temporary wordcount implementations (correct and intentionally wrong) and
asserts the verifier returns PASS only for the correct one and FAIL (with
specific hidden-case failures) for the wrong ones. This validates the verifier
before trusting it for Milestone 1.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_milestone1 import hidden_tests, expected, _parse_output  # noqa: E402


def _write_project(root: Path, core_src: str, cli_src: str):
    (root / "wordcount").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "wordcount" / "__init__.py").write_text("", encoding="utf-8")
    (root / "wordcount" / "core.py").write_text(core_src, encoding="utf-8")
    (root / "wordcount" / "cli.py").write_text(cli_src, encoding="utf-8")
    (root / "README.md").write_text("# wc\n", encoding="utf-8")
    (root / "QA-REPORT.md").write_text("QA PASS exit 0\n", encoding="utf-8")
    (root / "MANAGER-REVIEW.md").write_text("review\n", encoding="utf-8")
    (root / "artifacts" / "test-output.txt").write_text("ok\n", encoding="utf-8")


CORE_OK = r'''
def count_text(text):
    if not isinstance(text, str): raise TypeError
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    words = len(text.split())
    return {"lines": lines, "words": words, "characters": len(text)}
'''
CLI_OK = r'''
import argparse, sys
from .core import count_text
def main(argv=None):
    p = argparse.ArgumentParser(prog="wordcount")
    p.add_argument("path", nargs="?")
    p.add_argument("--text")
    a = p.parse_args(argv)
    if a.text is not None:
        text = a.text
    elif a.path and a.path != "-":
        try:
            with open(a.path, "r", encoding="utf-8") as f: text = f.read()
        except FileNotFoundError:
            print("not found", file=sys.stderr); return 2
    elif a.path == "-":
        text = sys.stdin.read()
    else:
        print("missing arg", file=sys.stderr); return 2
    r = count_text(text)
    print(f"lines={r['lines']} words={r['words']} characters={r['characters']} -")
    return 0
if __name__ == "__main__": raise SystemExit(main())
'''

# wrong: counts bytes not characters for utf8
CORE_BYTES = r'''
def count_text(text):
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    words = len(text.split())
    return {"lines": lines, "words": words, "characters": len(text.encode("utf-8"))}
'''
# wrong: off-by-one lines
CORE_LINE = r'''
def count_text(text):
    lines = text.count("\n")
    words = len(text.split())
    return {"lines": lines, "words": words, "characters": len(text)}
'''
# wrong: missing file exits 0
CLI_EXIT0 = r'''
import argparse, sys
from .core import count_text
def main(argv=None):
    p = argparse.ArgumentParser(prog="wordcount")
    p.add_argument("path", nargs="?")
    a = p.parse_args(argv)
    if a.path and a.path != "-":
        try:
            with open(a.path, "r", encoding="utf-8") as f: text = f.read()
        except FileNotFoundError:
            print("lines=0 words=0 characters=0 -"); return 0
    elif a.path == "-":
        text = sys.stdin.read()
    else:
        print("missing", file=sys.stderr); return 2
    r = count_text(text)
    print(f"lines={r['lines']} words={r['words']} characters={r['characters']} -"); return 0
if __name__ == "__main__": raise SystemExit(main())
'''
# wrong: no stdin support (treat '-' as file)
CLI_NOSTDIN = r'''
import argparse, sys
from .core import count_text
def main(argv=None):
    p = argparse.ArgumentParser(prog="wordcount")
    p.add_argument("path", nargs="?")
    a = p.parse_args(argv)
    if not a.path:
        print("missing", file=sys.stderr); return 2
    try:
        with open(a.path, "r", encoding="utf-8") as f: text = f.read()
    except FileNotFoundError:
        print("nf", file=sys.stderr); return 2
    r = count_text(text)
    print(f"lines={r['lines']} words={r['words']} characters={r['characters']} -"); return 0
if __name__ == "__main__": raise SystemExit(main())
'''


class VerifierSelfTest(unittest.TestCase):
    def _run(self, core, cli):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_project(root, core, cli)
            cases = hidden_tests(root)
            return cases

    def _assert_all_pass(self, cases):
        failed = [c for c in cases if not c["pass"]]
        self.assertFalse(failed, failed)

    def _assert_fails(self, cases, name_contains):
        self.assertTrue(any((not c["pass"]) and name_contains in c["name"] for c in cases), cases)

    def test_expected_computation(self):
        self.assertEqual(expected("a\nb\n"), {"lines": 2, "words": 2, "chars": 4})
        self.assertEqual(expected("a\nb"), {"lines": 2, "words": 2, "chars": 3})
        self.assertEqual(expected(""), {"lines": 0, "words": 0, "chars": 0})

    def test_parse_output(self):
        self.assertEqual(_parse_output("lines=1 words=2 characters=11 x"), {"lines": 1, "words": 2, "chars": 11})

    def test_correct_impl_passes_all_hidden(self):
        self._assert_all_pass(self._run(CORE_OK, CLI_OK))

    def test_bytes_not_chars_fails_utf8(self):
        self._assert_fails(self._run(CORE_BYTES, CLI_OK), "utf8")

    def test_line_off_by_one_fails(self):
        # Hidden cases use trailing-newline text, so an impl that always
        # undercounts by 1 when lines>0 must fail them.
        bad = r'''
def count_text(text):
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    if lines:
        lines -= 1
    words = len(text.split())
    return {"lines": lines, "words": words, "characters": len(text)}
'''
        cases = self._run(bad, CLI_OK)
        self.assertTrue(
            any(not c["pass"] and c["name"] in ("hidden.normal_file", "hidden.stdin", "hidden.utf8_multibyte_chars") for c in cases),
            cases,
        )

    def test_missing_file_exit0_fails(self):
        self._assert_fails(self._run(CORE_OK, CLI_EXIT0), "missing_file")

    def test_no_stdin_fails(self):
        self._assert_fails(self._run(CORE_OK, CLI_NOSTDIN), "stdin")
