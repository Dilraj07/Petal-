import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from petal.cli import _check_regression


class TestCheckRegression(unittest.TestCase):
    """Tests for the `petal check-regression` subcommand logic."""

    def _write_json(self, tmpdir: str, name: str, data: dict) -> str:
        path = os.path.join(tmpdir, name)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def _make_result(self, energy: float, collector: str = "synthetic",
                     confidence: str = "low", is_estimate: bool = True) -> dict:
        return {
            "baseline": {"energy_j": energy, "runtime_s": 0.5, "runs": 3},
            "collector": {
                "requested": "auto",
                "used": collector,
                "fallback_used": False,
                "confidence": confidence,
                "note": "",
                "quality_label": f"source: {collector}",
            },
            "measurement": {
                "energy_domain": None if is_estimate else "package",
                "unit": "joules-est" if is_estimate else "joules",
                "is_estimate": is_estimate,
            },
            "source_file": "test.c",
        }

    def test_pass_within_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline = self._write_json(tmpdir, "baseline.json", self._make_result(10.0))
            result = self._write_json(tmpdir, "result.json", self._make_result(10.3))

            args = type("Args", (), {
                "result": result,
                "baseline": baseline,
                "threshold": 5.0,
                "telemetry_required": "any",
            })()

            with self.assertRaises(SystemExit) as ctx:
                _check_regression(args)
            self.assertEqual(ctx.exception.code, 0)

    def test_fail_exceeds_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline = self._write_json(tmpdir, "baseline.json", self._make_result(10.0))
            result = self._write_json(tmpdir, "result.json", self._make_result(11.5))

            args = type("Args", (), {
                "result": result,
                "baseline": baseline,
                "threshold": 5.0,
                "telemetry_required": "any",
            })()

            with self.assertRaises(SystemExit) as ctx:
                _check_regression(args)
            self.assertEqual(ctx.exception.code, 1)

    def test_hardware_required_with_synthetic_warns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline = self._write_json(tmpdir, "baseline.json", self._make_result(10.0))
            result = self._write_json(tmpdir, "result.json",
                                      self._make_result(15.0, "synthetic", "low", True))

            args = type("Args", (), {
                "result": result,
                "baseline": baseline,
                "threshold": 5.0,
                "telemetry_required": "hardware",
            })()

            with self.assertRaises(SystemExit) as ctx:
                _check_regression(args)
            # Should exit 0 (warn, not fail) when hardware required but synthetic used
            self.assertEqual(ctx.exception.code, 0)

    def test_hardware_telemetry_enforces_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline = self._write_json(tmpdir, "baseline.json",
                                        self._make_result(10.0, "rapl", "high", False))
            result = self._write_json(tmpdir, "result.json",
                                      self._make_result(12.0, "rapl", "high", False))

            args = type("Args", (), {
                "result": result,
                "baseline": baseline,
                "threshold": 5.0,
                "telemetry_required": "hardware",
            })()

            with self.assertRaises(SystemExit) as ctx:
                _check_regression(args)
            # 20% regression with hardware telemetry → should fail
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
