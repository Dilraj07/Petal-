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
        self.assertEqual(collector.name, "synthetic_cpu_load")

    def test_profile_binary_returns_expected_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, "noop.sh")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n")
                f.write("exit 0\n")
            os.chmod(script_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            metrics = profile_binary(script_path, collector_name="synthetic")
            for key in (
                "collector",
                "confidence_tier",
                "execution_time_s",
                "avg_cpu_load_pct",
                "avg_power_w",
                "energy_j",
                "sample_count",
                "requested_collector",
                "fallback_used",
            ):
                self.assertIn(key, metrics)


if __name__ == "__main__":
    unittest.main()
