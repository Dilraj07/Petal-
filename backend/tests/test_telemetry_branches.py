import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import core.telemetry as telemetry


class TestTelemetryBranches(unittest.TestCase):
    def test_high_confidence_collectors_report_hardware_quality(self):
        self.assertIn("quality: hardware", telemetry.RaplTelemetryCollector().quality_label)

    def test_profile_binary_marks_fallback_for_unknown_requested_collector(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, "noop.sh")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(script_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

            metrics = telemetry.profile_binary(script_path, collector_name="missing_collector")
            self.assertEqual(metrics["collector"]["requested"], "missing_collector")
            self.assertEqual(metrics["collector"]["used"], "synthetic")
            self.assertTrue(metrics["collector"]["fallback_used"])

    def test_resolve_collector_auto_uses_first_available_in_priority_order(self):
        class Unavailable:
            name = "unavailable"
            confidence_tier = "high"
            note = ""

            def is_available(self):
                return False

        class Available:
            name = "available"
            confidence_tier = "high"
            note = ""

            def is_available(self):
                return True

        with patch.dict(
            telemetry.COLLECTORS,
            {"amd_uprof": Unavailable, "rapl": Available, "perf_stat": Unavailable},
            clear=False,
        ):
            collector, requested = telemetry.resolve_collector("auto")
        self.assertEqual(requested, "auto")
        self.assertEqual(collector.name, "available")

    def test_perf_stat_is_unavailable_when_perf_missing(self):
        with patch("core.telemetry.shutil.which", return_value=None):
            self.assertFalse(telemetry.PerfStatTelemetryCollector().is_available())

    def test_perf_stat_is_unavailable_on_probe_timeout(self):
        with patch("core.telemetry.shutil.which", return_value="/usr/bin/perf"):
            with patch("core.telemetry.subprocess.run", side_effect=TimeoutExpired("perf", 5)):
                self.assertFalse(telemetry.PerfStatTelemetryCollector().is_available())

    def test_rapl_is_available_checks_file_and_permissions(self):
        with patch("core.telemetry.os.path.isfile", return_value=True), patch(
            "core.telemetry.os.access", return_value=True
        ):
            self.assertTrue(telemetry.RaplTelemetryCollector().is_available())
        with patch("core.telemetry.os.path.isfile", return_value=False), patch(
            "core.telemetry.os.access", return_value=True
        ):
            self.assertFalse(telemetry.RaplTelemetryCollector().is_available())


if __name__ == "__main__":
    unittest.main()
