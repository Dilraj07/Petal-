import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from petal import cli


class TestCliHelpers(unittest.TestCase):
    def test_fmt_energy_uses_expected_units(self):
        self.assertEqual(cli._fmt_energy(0.0000009), "0.9 µJ")
        self.assertEqual(cli._fmt_energy(0.2), "200.0 mJ")
        self.assertEqual(cli._fmt_energy(2.5), "2.50 J")

    def test_fmt_time_uses_expected_units(self):
        self.assertEqual(cli._fmt_time(0.0000009), "1 µs")
        self.assertEqual(cli._fmt_time(0.2), "200.0 ms")
        self.assertEqual(cli._fmt_time(2.5), "2.500 s")

    def test_fmt_time_rounding_behavior_for_microseconds(self):
        self.assertEqual(cli._fmt_time(0.0000014), "1 µs")
        self.assertEqual(cli._fmt_time(0.0000016), "2 µs")

    def test_quality_tag_for_high_and_estimated(self):
        self.assertEqual(
            cli._quality_tag({"used": "rapl", "confidence": "high"}),
            "[source: rapl]",
        )
        self.assertEqual(
            cli._quality_tag({"used": "synthetic", "confidence": "low"}),
            "[source: synthetic, estimated ±35%]",
        )

    def test_build_parser_json_flag(self):
        parser = cli._build_parser()
        args = parser.parse_args(["input.c", "--json"])
        self.assertTrue(args.json_out)
        self.assertEqual(args.file, "input.c")

    def test_main_defaults_to_optimise_when_no_mode_specified(self):
        with patch.object(cli, "_run_pipeline", return_value={}) as run_pipeline:
            with patch.object(sys, "argv", ["petal", "input.c"]):
                cli.main()

        called_args = run_pipeline.call_args[0][0]
        self.assertTrue(called_args.optimise)
        self.assertTrue(called_args.optimize)

    def test_main_routes_to_check_regression_subcommand(self):
        with patch.object(cli, "_check_regression") as check:
            with patch.object(
                sys,
                "argv",
                ["petal", "check-regression", "--result", "r.json", "--baseline", "b.json"],
            ):
                cli.main()
        check.assert_called_once()

    def test_main_exits_without_file_argument(self):
        with patch.object(sys, "argv", ["petal"]):
            with self.assertRaises(SystemExit) as ctx:
                cli.main()
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
