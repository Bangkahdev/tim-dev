"""Accounting tests for the Milestone 1 acceptance runner.

Sandbox isolation is evidenced externally (wrapper canaries + operator note),
while the independent verifier explicitly cannot claim it. Those checks must not
hard-fail an otherwise-passing attempt.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.run_milestone1 import _hard_failures  # noqa: E402


class RunnerHardFailureTests(unittest.TestCase):
    def test_sandbox_and_manual_items_are_not_hard_failures(self):
        checks = {
            "pilot_tests_pass": True,
            "verify.OVERALL_VERIFIABLE": True,
            "sandbox.fs_network_isolation_NFR_SEC_09_10": True,
            "sandbox_fs_network_isolation_NFR_SEC_09_10": False,
            "verify.sandbox.fs_network_isolation_NFR_SEC_09_10": False,
            "manual.godot_status_tray_paper_match_backend": "MANUAL_REQUIRED",
        }
        self.assertEqual(_hard_failures(checks, []), [])

    def test_real_false_checks_still_fail(self):
        checks = {
            "pilot_tests_pass": True,
            "verify.hidden.all_pass": False,
            "verify.OVERALL_VERIFIABLE": False,
            "sandbox_fs_network_isolation_NFR_SEC_09_10": False,
        }
        self.assertEqual(
            _hard_failures(checks, []),
            ["verify.hidden.all_pass", "verify.OVERALL_VERIFIABLE"],
        )

    def test_explicit_failure_strings_are_kept(self):
        checks = {"sandbox.fs_network_isolation_NFR_SEC_09_10": False}
        self.assertEqual(
            _hard_failures(checks, ["sandbox FS/network isolation NOT evidenced"]),
            ["sandbox FS/network isolation NOT evidenced"],
        )


if __name__ == "__main__":
    unittest.main()
