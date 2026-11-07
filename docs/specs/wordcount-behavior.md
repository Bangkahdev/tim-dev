# `wordcount` CLI — Behavior Spec (agent-facing, Milestone 1)

Implement a small Python CLI utility `wordcount`.

## Interface
- Run as: `python -m wordcount <path|->` (module `wordcount`; `wordcount.cli`/`__main__` acceptable).
- Input: a UTF-8 text file path, or `-` to read from stdin.
- Output (stdout, success): a single line containing `lines`, `words`, and `characters` counts plus the input name, e.g. `lines=2 words=4 characters=24 <name>` (exact spacing/labels may vary if clearly labeled and parseable).
- Exit codes: `0` on success; `2` on missing argument or missing/unreadable file, with a human-readable error on stderr.

## Counting rules
- `characters`: Unicode character count of the text (not bytes).
- `words`: whitespace-delimited tokens (`str.split()` semantics are acceptable).
- `lines`: number of lines in the text. For a non-empty text that does not end with a newline, count the final unterminated line; for empty text, `0`.

## Deliverables
- `wordcount/` package (`core.py` with `count_text(text) -> {lines,words,characters}`, `cli.py`/`__main__.py`).
- `README.md` (usage + test command).
- `tests/test_wordcount.py` (pytest or unittest) covering at minimum: normal file, empty file, stdin (`-`), missing file/arg (exit 2 + stderr).
- `artifacts/test-output.txt` with the test command, exit code, and output.

## Notes
- UTF-8. No external services. Keep it small and deterministic.
- Your tests are necessary but not sufficient; correctness is verified independently by the Owner.
