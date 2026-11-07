import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.sandbox_exec import (
    SANDBOX_CMD_ENV,
    SANDBOX_REQUIRED_ENV,
    SandboxConfigurationError,
    enforce_sandbox,
    sandbox_required,
    sandbox_status,
    sandbox_wrapper,
    wrap_argv,
)


class SandboxExecTests(unittest.TestCase):
    def test_no_wrapper_returns_argv(self):
        self.assertEqual(wrap_argv(["python", "-m", "x"], "/p", source={}), ["python", "-m", "x"])

    def test_wrapper_prefix_and_project_dir_token(self):
        src = {SANDBOX_CMD_ENV: "docker run --rm -v {project_dir}:/work -w /work img"}
        got = wrap_argv(["python", "-m", "wordcount", "-"], "C:/proj", source=src)
        self.assertEqual(
            got[:6],
            ["docker", "run", "--rm", "-v", str(Path("C:/proj").resolve()) + ":/work", "-w"],
        )
        self.assertEqual(got[6:], ["/work", "img", "python", "-m", "wordcount", "-"])

    def test_empty_wrapper(self):
        self.assertEqual(sandbox_wrapper(source={SANDBOX_CMD_ENV: "  "}), [])

    def test_required_flag(self):
        self.assertTrue(sandbox_required(source={SANDBOX_REQUIRED_ENV: "1"}))
        self.assertTrue(sandbox_required(source={SANDBOX_REQUIRED_ENV: "true"}))
        self.assertFalse(sandbox_required(source={}))

    def test_status_reports_missing_when_required(self):
        status = sandbox_status(source={SANDBOX_REQUIRED_ENV: "1"})
        self.assertTrue(status["required"])
        self.assertFalse(status["active"])
        self.assertIn("BANGKAH_SANDBOX_CMD", status["error"])

    def test_enforce_blocks_when_required_and_missing(self):
        with self.assertRaises(SandboxConfigurationError):
            enforce_sandbox(["python", "-m", "x"], "/p", source={SANDBOX_REQUIRED_ENV: "1"})

    def test_enforce_wraps_when_configured(self):
        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: "docker run {project_dir} img"}
        got = enforce_sandbox(["python", "-m", "x"], "/p", src)
        self.assertEqual(got[0:2], ["docker", "run"])
        self.assertIn("python", got)

    def test_enforce_warns_but_allows_when_not_required(self):
        got = enforce_sandbox(["python", "-m", "x"], "/p", source={})
        self.assertEqual(got, ["python", "-m", "x"])

    def test_invalid_wrapper_config_fails_closed_when_required(self):
        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: 'docker run "unterminated'}
        with self.assertRaises(SandboxConfigurationError):
            enforce_sandbox(["python"], "/p", source=src)


if __name__ == "__main__":
    unittest.main()
