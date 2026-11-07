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
        src = {SANDBOX_CMD_ENV: "python -c 'import sys; sys.exit(0)' {project_dir} --"}
        got = wrap_argv(["python", "-m", "wordcount", "-"], "C:/proj", source=src)
        self.assertEqual(got[-4:], ["python", "-m", "wordcount", "-"])
        self.assertIn(str(Path("C:/proj").resolve()), " ".join(got))

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
        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: "python -c 'import sys; sys.exit(0)' {project_dir} --"}
        got = enforce_sandbox(["python", "-m", "x"], "/p", src)
        self.assertIn(str(Path("/p").resolve()), " ".join(got))
        self.assertEqual(got[-3:], ["python", "-m", "x"])

    def test_enforce_warns_but_allows_when_not_required(self):
        got = enforce_sandbox(["python", "-m", "x"], "/p", source={})
        self.assertEqual(got, ["python", "-m", "x"])

    def test_invalid_wrapper_config_fails_closed_when_required(self):
        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: 'docker run "unterminated'}
        with self.assertRaises(SandboxConfigurationError):
            enforce_sandbox(["python"], "/p", source=src)

    def test_rejects_missing_project_dir_token_when_required(self):
        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: "python -c 'import sys; sys.exit(0)'"}
        status = sandbox_status(source=src)
        self.assertIn("{project_dir}", status["error"])
        with self.assertRaises(SandboxConfigurationError):
            enforce_sandbox(["python"], "/p", source=src)

    def test_rejects_missing_wrapper_binary(self):
        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: "/definitely/missing/bangkah-sandbox {project_dir} --"}
        status = sandbox_status(source=src)
        self.assertIn("binary not found", status["error"])

    def test_canaries_pass_with_mock_runner(self):
        from core.sandbox_exec import run_sandbox_canaries
        import json
        import subprocess

        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: "python -c 'import sys; sys.exit(0)' {project_dir} --"}

        def runner(argv, cwd, timeout):
            script = argv[3] if len(argv) > 3 else ""
            if "sentinel" in " ".join(argv) or "Path(sys.argv[1])" in script:
                return subprocess.CompletedProcess(argv, 1, stdout=json.dumps({"ok": True, "leaked": False, "error": "FileNotFoundError"}), stderr="")
            return subprocess.CompletedProcess(argv, 1, stdout=json.dumps({"ok": True, "leaked": False, "error": "OSError"}), stderr="")

        result = run_sandbox_canaries("/tmp", source=src, runner=runner)
        self.assertTrue(result["ok"])
        self.assertTrue(result["fs_isolated"])
        self.assertTrue(result["network_isolated"])

    def test_canaries_reject_when_wrapper_breaks_execution(self):
        from core.sandbox_exec import run_sandbox_canaries
        import subprocess

        # Simulates `env {project_dir}`-style misbehavior: command fails, no canary JSON.
        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: "python -c 'import sys; sys.exit(0)' {project_dir} --"}

        def runner(argv, cwd, timeout):
            return subprocess.CompletedProcess(argv, 127, stdout="", stderr="exec failed")

        result = run_sandbox_canaries("/tmp", source=src, runner=runner)
        self.assertFalse(result["ok"])
        self.assertFalse(result["fs_isolated"])
        self.assertFalse(result["network_isolated"])


if __name__ == "__main__":
    unittest.main()

    def test_canaries_reject_leak(self):
        from core.sandbox_exec import run_sandbox_canaries, FS_CANARY_SCRIPT
        import json
        import subprocess

        src = {SANDBOX_REQUIRED_ENV: "1", SANDBOX_CMD_ENV: "python -c 'import sys; sys.exit(0)' {project_dir} --"}

        def runner(argv, cwd, timeout):
            joined = "\n".join(argv)
            if FS_CANARY_SCRIPT in joined or "Path(sys.argv[1])" in joined:
                return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"ok": True, "leaked": True, "bytes": 5}), stderr="")
            return subprocess.CompletedProcess(argv, 1, stdout=json.dumps({"ok": True, "leaked": False, "error": "OSError"}), stderr="")

        result = run_sandbox_canaries("/tmp", source=src, runner=runner)
        self.assertFalse(result["ok"])
        self.assertFalse(result["fs_isolated"])
