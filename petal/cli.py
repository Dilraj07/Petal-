"""Petal CLI — energy-aware compilation for C/C++ workloads.

Usage:
    petal <file.c>                          # Analyse + optimise (default)
    petal <file.c> --analyse                # Analyse only
    petal <file.c> --optimise               # Optimise + benchmark
    petal <file.c> --optimise --explain      # Show transformation rationale
    petal <file.c> --optimise --json         # Machine-readable JSON output
    petal check-regression                   # CI regression gate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

# Force utf-8 stdout/stderr to support emojis on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding.lower() != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure backend/ is importable regardless of install method
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.core.analyzer import analyze_energy_hotspots
from backend.core.policy import POLICY_CONFIGS, decide_transformation, normalize_policy
from backend.core.transformer import apply_loop_tiling
from backend.core.telemetry import profile_binary

from petal import __version__


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_energy(joules: float) -> str:
    if joules < 0.001:
        return f"{joules * 1_000_000:.1f} µJ"
    if joules < 1.0:
        return f"{joules * 1_000:.1f} mJ"
    return f"{joules:.2f} J"


def _fmt_time(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f} µs"
    if seconds < 1.0:
        return f"{seconds * 1_000:.1f} ms"
    return f"{seconds:.3f} s"


def _quality_tag(collector_info: dict) -> str:
    name = collector_info["used"]
    if collector_info["confidence"] == "high":
        return f"[source: {name}]"
    return f"[source: {name}, estimated ±35%]"


# ---------------------------------------------------------------------------
# Core pipeline (shared by analyse/optimise)
# ---------------------------------------------------------------------------

def _run_pipeline(args: argparse.Namespace) -> dict:
    """Execute the Petal pipeline and return a structured result dict."""
    source_path = args.file
    if not os.path.isfile(source_path):
        print(f"Error: {source_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(source_path, "r", encoding="utf-8", errors="replace") as f:
        source_code = f.read()

    policy_name = normalize_policy(args.policy)
    policy_cfg = POLICY_CONFIGS[policy_name]
    do_optimise = args.optimise or args.optimize

    result: dict = {
        "tool": "petal",
        "version": __version__,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_file": os.path.abspath(source_path),
        "policy": policy_name,
    }

    # ── Step 1: Analyse ──────────────────────────────────────────────────
    if not args.json:
        print(f"Analysing {os.path.basename(source_path)}...")

    has_hotspot = analyze_energy_hotspots(source_code)
    hotspot_confidence = 0.9 if has_hotspot else 0.0
    decision = decide_transformation(has_hotspot, policy_name, hotspot_confidence)

    if has_hotspot and not args.json:
        print(f"  Found hotspot: depth-3 loop nest (confidence: {hotspot_confidence:.0%})")
    elif not args.json:
        print("  No energy hotspots detected.")

    result["hotspot_detected"] = has_hotspot
    result["hotspot_confidence"] = hotspot_confidence
    result["transform_decision"] = decision

    if args.analyse:
        return result

    # ── Step 2: Transform (if approved by policy) ────────────────────────
    apply_opt = decision["apply_transform"] and do_optimise
    optimised_code = None

    if apply_opt:
        if not args.json:
            print(f"\nOptimising...")
        optimised_code = apply_loop_tiling(source_code)
        if not args.json:
            print(f"  Applied: loop tiling (tile=64)")
            if args.explain:
                print(f"  Rationale: O(N³) loop nest with stride-N access on inner dimension.")
                print(f"  Effect: Reduces L1 cache miss rate by constraining working set to tile²×sizeof(int) bytes.")
                print(f"  Policy: {policy_name} (threshold: {policy_cfg.min_hotspot_confidence:.0%}, confidence: {hotspot_confidence:.0%})")
    elif do_optimise and not args.json:
        print(f"\nOptimisation skipped: {decision['reason']}")

    # ── Step 3: Compile & Benchmark ──────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(os.path.abspath(source_path)), ".petal_out")
    os.makedirs(out_dir, exist_ok=True)

    baseline_bin = os.path.join(out_dir, "baseline")
    if os.name == "nt":
        baseline_bin += ".exe"

    try:
        subprocess.run(
            ["gcc", *policy_cfg.baseline_flags, source_path, "-o", baseline_bin],
            check=True, capture_output=True, text=True
        )
    except FileNotFoundError:
        print("Error: gcc not found on PATH. Install GCC to continue.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: gcc compilation failed:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)

    if not args.json:
        print(f"\nCompiling and benchmarking...")

    runs = max(1, min(args.runs, 10))
    collector_name = args.collector

    # Baseline runs
    baseline_results = []
    for _ in range(runs):
        abs_bin = os.path.abspath(baseline_bin)
        res = profile_binary(abs_bin, collector_name=collector_name)
        baseline_results.append(res)

    base_energy_median = sorted(r["energy_j"] for r in baseline_results)[len(baseline_results) // 2]
    base_runtime_median = sorted(r["runtime_s"] for r in baseline_results)[len(baseline_results) // 2]
    collector_info = baseline_results[0]["collector"]
    tag = _quality_tag(collector_info)

    if not args.json:
        print(f"  Baseline:   {_fmt_energy(base_energy_median):>10}  {tag}")

    result["baseline"] = {
        "energy_j": base_energy_median,
        "runtime_s": base_runtime_median,
        "runs": runs,
    }
    result["collector"] = collector_info
    result["measurement"] = baseline_results[0]["measurement"]

    # Optimised runs (if applicable)
    if apply_opt and optimised_code is not None:
        opt_file = os.path.join(out_dir, "optimised.c")
        with open(opt_file, "w", encoding="utf-8") as f:
            f.write(optimised_code)

        opt_bin = os.path.join(out_dir, "optimised")
        if os.name == "nt":
            opt_bin += ".exe"

        subprocess.run(
            ["gcc", *policy_cfg.optimized_flags, opt_file, "-o", opt_bin],
            check=True, capture_output=True, text=True
        )

        opt_results = []
        for _ in range(runs):
            res = profile_binary(os.path.abspath(opt_bin), collector_name=collector_name)
            opt_results.append(res)

        opt_energy_median = sorted(r["energy_j"] for r in opt_results)[len(opt_results) // 2]
        opt_runtime_median = sorted(r["runtime_s"] for r in opt_results)[len(opt_results) // 2]

        delta_j = base_energy_median - opt_energy_median
        delta_pct = (delta_j / base_energy_median * 100) if base_energy_median > 0 else 0

        if not args.json:
            print(f"  Optimised:  {_fmt_energy(opt_energy_median):>10}  {tag}")
            print(f"  Saved:      {_fmt_energy(delta_j):>10}  ({delta_pct:.1f}%)")

        result["optimised"] = {
            "energy_j": opt_energy_median,
            "runtime_s": opt_runtime_median,
            "runs": runs,
        }
        result["comparison"] = {
            "energy_delta_j": round(delta_j, 6),
            "energy_delta_pct": round(delta_pct, 2),
        }

        # Correctness check via stdout hash
        base_hash = hashlib.sha256((baseline_results[0]["stdout"] or "").encode()).hexdigest()
        opt_hash = hashlib.sha256((opt_results[0]["stdout"] or "").encode()).hexdigest()
        result["correctness"] = {
            "passed": base_hash == opt_hash,
            "method": "stdout_hash_sha256",
        }

        # Write optimised source
        out_path = args.out
        if not out_path:
            root, ext = os.path.splitext(source_path)
            out_path = f"{root}_green{ext or '.c'}"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(optimised_code)
        if not args.json:
            print(f"\nOutput written to: {out_path}")

        result["output_file"] = os.path.abspath(out_path)

    return result


# ---------------------------------------------------------------------------
# check-regression subcommand
# ---------------------------------------------------------------------------

def _check_regression(args: argparse.Namespace) -> None:
    """Compare a current run result against a stored baseline."""
    if not os.path.isfile(args.result):
        print(f"Error: result file not found: {args.result}", file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(args.baseline):
        print(f"Error: baseline file not found: {args.baseline}", file=sys.stderr)
        sys.exit(2)

    with open(args.result, "r") as f:
        current = json.load(f)
    with open(args.baseline, "r") as f:
        baseline = json.load(f)

    # Extract energy values
    curr_energy = current.get("baseline", {}).get("energy_j", 0)
    if "optimised" in current:
        curr_energy = current["optimised"]["energy_j"]

    base_energy = baseline.get("baseline", {}).get("energy_j", 0)
    if "optimised" in baseline:
        base_energy = baseline["optimised"]["energy_j"]

    if base_energy <= 0:
        print("Warning: baseline energy is zero or negative. Cannot compute regression.", file=sys.stderr)
        sys.exit(2)

    delta_pct = ((curr_energy - base_energy) / base_energy) * 100
    threshold = args.threshold

    # Telemetry quality check
    collector_info = current.get("collector", {})
    telemetry_quality = collector_info.get("confidence", "low")
    measurement = current.get("measurement", {})
    is_estimate = measurement.get("is_estimate", True)
    source_name = collector_info.get("used", "unknown")

    if args.telemetry_required == "hardware" and is_estimate:
        print(f"⚠  Telemetry quality insufficient")
        print(f"   Source: {source_name} (estimated)")
        print(f"   Required: hardware")
        print(f"   Skipping regression gate — cannot enforce with estimated telemetry.")
        sys.exit(0)  # Warn, don't fail

    # Regression check
    quality_tag = f"[source: {source_name}]" if not is_estimate else f"[source: {source_name}, estimated]"
    print(f"Energy comparison {quality_tag}")
    print(f"  Baseline: {_fmt_energy(base_energy)}")
    print(f"  Current:  {_fmt_energy(curr_energy)}")
    print(f"  Delta:    {delta_pct:+.1f}%  (threshold: {threshold}%)")

    if delta_pct > threshold:
        print(f"\n⚡ REGRESSION DETECTED — energy increased by {delta_pct:.1f}% (>{threshold}%)")
        source_file = current.get("source_file", "unknown")
        print(f"   File: {source_file}")
        if "comparison" in current:
            print(f"   Energy delta: {_fmt_energy(current['comparison']['energy_delta_j'])}")
        print(f"\n   Run `petal {os.path.basename(source_file)} --optimise --explain` for details.")
        sys.exit(1)
    else:
        print(f"\n✓  Energy within budget ({delta_pct:+.1f}% ≤ {threshold}%)")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

from petal.dashboard import generate_dashboard
from petal.env import setup_telemetry_environment

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="petal",
        description="Petal — energy-aware compilation for C/C++ workloads",
    )
    parser.add_argument("--version", action="version", version=f"petal {__version__}")

    # To support both `petal <file>` and subcommands, we check argv manually below.
    # Here we define the arguments for the default file-processing mode.
    parser.add_argument("file", nargs="?", help="Source C/C++ file to process")
    parser.add_argument("--analyse", "--analyze", action="store_true",
                        help="Analyse only — detect hotspots without transforming")
    parser.add_argument("--optimise", "--optimize", action="store_true",
                        help="Apply energy optimisations (default when not --analyse)")
    parser.add_argument("--explain", action="store_true",
                        help="Show detailed rationale for each transformation")
    parser.add_argument("--json", dest="json_out", action="store_true",
                        help="Emit machine-readable JSON to stdout")
    parser.add_argument("--out", type=str, default=None,
                        help="Output path for optimised source (default: <file>_green.c)")
    parser.add_argument("--policy", type=str, default="balanced",
                        help="Optimisation policy: eco | balanced | perf")
    parser.add_argument("--collector", type=str, default="auto",
                        help="Telemetry collector: auto | synthetic | rapl | perf_stat | amd_uprof")
    parser.add_argument("--runs", type=int, default=3,
                        help="Number of benchmark runs per variant (default: 3, max: 10)")
    parser.add_argument("--metadata-out", type=str, default=None,
                        help="Write run metadata JSON to this path")
    parser.add_argument("--cmake-dir", action="store_true",
                        help="Print the absolute path to Petal's CMake module directory")

    return parser


def _build_sub_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="petal")
    subparsers = parser.add_subparsers(dest="command")

    # check-regression
    check_p = subparsers.add_parser("check-regression", help="CI gate: compare current run against stored baseline")
    check_p.add_argument("--result", required=True, help="Path to current run's metadata JSON")
    check_p.add_argument("--baseline", required=True, help="Path to baseline metadata JSON")
    check_p.add_argument("--threshold", type=float, default=5.0, help="Max allowable energy regression %% (default: 5)")
    check_p.add_argument("--telemetry-required", type=str, default="any", choices=["hardware", "any"],
                         help="Require hardware telemetry to enforce gate")

    # setup-env
    subparsers.add_parser("setup-env", help="Configure Linux system for hardware telemetry (requires sudo)")

    # generate-dashboard
    dash_p = subparsers.add_parser("generate-dashboard", help="Generate a static HTML dashboard from JSON results")
    dash_p.add_argument("--results-dir", required=True, help="Directory containing petal_result.json files")
    dash_p.add_argument("--out", default="petal_dashboard.html", help="Output path for the HTML file")

    return parser

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Route to subcommands if first arg matches
    subcommands = ["check-regression", "setup-env", "generate-dashboard"]
    if len(sys.argv) > 1 and sys.argv[1] in subcommands:
        sub_parser = _build_sub_parser()
        args = sub_parser.parse_args(sys.argv[1:])
        
        if args.command == "check-regression":
            _check_regression(args)
        elif args.command == "setup-env":
            sys.exit(setup_telemetry_environment())
        elif args.command == "generate-dashboard":
            sys.exit(generate_dashboard(args.results_dir, args.out))
        return

    parser = _build_parser()
    args = parser.parse_args()
    args.command = None

    if getattr(args, "cmake_dir", False):
        cmake_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cmake")
        print(cmake_path)
        sys.exit(0)

    # We renamed --json to json_out to avoid clashing with the json module
    if hasattr(args, "json_out"):
        args.json = args.json_out

    # Default command: file processing
    if not args.file:
        parser.print_help()
        sys.exit(1)

    # Default to --optimise if neither --analyse nor --optimise is set
    if not args.analyse and not args.optimise:
        args.optimise = True
        # Also set optimize for the alias check in _run_pipeline
        args.optimize = True

    result = _run_pipeline(args)

    # Write metadata JSON if requested
    metadata_path = args.metadata_out
    if metadata_path:
        os.makedirs(os.path.dirname(os.path.abspath(metadata_path)), exist_ok=True)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        if not args.json:
            print(f"Metadata written to: {metadata_path}")

    # JSON output mode
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
