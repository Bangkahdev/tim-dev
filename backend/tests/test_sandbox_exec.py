import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.sandbox_exec import sandbox_wrapper, wrap_argv, SANDBOX_CMD_ENV

class SandboxExecTests(unittest.TestCase):
    def test_no_wrapper_returns_argv(self):
        self.assertEqual(wrap_argv(["python","-m","x"], "/p", source={}), ["python","-m","x"])

    def test_wrapper_prefix_and_project_dir_token(self):
        src = {SANDBOX_CMD_ENV: 'docker run --rm -v {project_dir}:/work -w /work img'}
        got = wrap_argv(["python", "-m", "wordcount", "-"], "C:/proj", source=src)
        self.assertEqual(got[:6], ["docker", "run", "--rm", "-v", str(Path("C:/proj").resolve()) + ":/work", "-w"])
        self.assertEqual(got[6:], ["/work", "img", "python", "-m", "wordcount", "-"])

    def test_empty_wrapper(self):
        self.assertEqual(sandbox_wrapper(source={SANDBOX_CMD_ENV: "  "}), [])

if __name__ == "__main__":
    unittest.main()
