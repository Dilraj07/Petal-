import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.policy import decide_transformation, normalize_policy
from core.telemetry import profile_binary, resolve_collector


class TestPolicyAndTelemetry(unittest.TestCase):
    def test_normalize_policy_defaults_to_balanced(self):
        self.assertEqual(normalize_policy("invalid"), "balanced")
        self.assertEqual(normalize_policy("ECO"), "eco")

    def test_policy_decision_respects_threshold(self):
        perf_reject = decide_transformation(True, "perf", 0.7)
        self.assertFalse(perf_reject["apply_transform"])
        eco_accept = decide_transformation(True, "eco", 0.7)
        self.assertTrue(eco_accept["apply_transform"])

    def test_unknown_collector_falls_back_to_synthetic(self):
        collector, requested = resolve_collector("unknown")
        self.assertEqual(requested, "unknown")
        self.assertEqual(collector.name, "synthetic")

    def test_profile_binary_returns_expected_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, "noop.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("import sys; sys.exit(0)\n")
            
            # Since profile_binary runs executable directly, and we need python on windows
            # Let's wrap python call or just profile python.exe
            # For this test, profiling python itself running our script is easiest
            # Wait, `profile_binary` takes `executable_path`. On Windows, we can't just pass `noop.py`.
            # Let's create a .bat file on Windows and .sh on Linux.
            if os.name == 'nt':
                script_path = os.path.join(tmpdir, "noop.bat")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write("@echo off\nexit /b 0\n")
            else:
                script_path = os.path.join(tmpdir, "noop.sh")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write("#!/bin/sh\nexit 0\n")
                os.chmod(script_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

            metrics = profile_binary(script_path, collector_name="synthetic")
            # Top-level keys
            for key in ("runtime_s", "energy_j", "stdout", "stderr", "exit_code",
                        "collector", "measurement"):
                self.assertIn(key, metrics)
            # Nested collector sub-keys
            for key in ("requested", "used", "fallback_used", "confidence", "note"):
                self.assertIn(key, metrics["collector"])
            # Nested measurement sub-keys
            for key in ("energy_domain", "unit", "is_estimate"):
                self.assertIn(key, metrics["measurement"])
            # Confirm fallback is correctly identified
            self.assertEqual(metrics["collector"]["used"], "synthetic")
            self.assertFalse(metrics["collector"]["fallback_used"])

    def test_quality_label_present_in_collector_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            if os.name == 'nt':
                script_path = os.path.join(tmpdir, "noop.bat")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write("@echo off\nexit /b 0\n")
            else:
                script_path = os.path.join(tmpdir, "noop.sh")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write("#!/bin/sh\nexit 0\n")
                os.chmod(script_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

            metrics = profile_binary(script_path, collector_name="synthetic")
            self.assertIn("quality_label", metrics["collector"])
            self.assertIn("synthetic", metrics["collector"]["quality_label"])

    def test_perf_stat_collector_in_registry(self):
        from core.telemetry import COLLECTORS
        self.assertIn("perf_stat", COLLECTORS)

    def test_rapl_collector_in_registry(self):
        from core.telemetry import COLLECTORS
        self.assertIn("rapl", COLLECTORS)

    def test_auto_resolution_returns_collector(self):
        collector, requested = resolve_collector("auto")
        self.assertEqual(requested, "auto")
        # Should always return a valid collector (synthetic at minimum)
        self.assertIn(collector.name, ("synthetic", "rapl", "perf_stat", "amd_uprof"))

    def test_synthetic_quality_label_contains_estimated(self):
        from core.telemetry import SyntheticCpuTelemetryCollector
        c = SyntheticCpuTelemetryCollector()
        self.assertIn("estimated", c.quality_label)

    def test_auto_priority_order(self):
        from core.telemetry import _AUTO_PRIORITY
        self.assertEqual(_AUTO_PRIORITY, ("amd_uprof", "rapl", "perf_stat"))


if __name__ == "__main__":
    unittest.main()
