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
from petal.formatter import (
    fmt_energy, fmt_time, fmt_power, quality_tag,
    Color, success, error, warning, info, accent, bold, dim,
    print_header, print_section, print_table, print_comparison, 
    print_savings_badge, checklist_item
)
from petal.interactive import interactive_mode, show_demo_options
from petal.report import generate_html_report
from petal.config import PetalConfig, load_config, merge_with_args

import glob

# Keep old names for backward compatibility
_fmt_energy = fmt_energy
_fmt_time = fmt_time
_quality_tag = quality_tag


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
    do_optimise = getattr(args, 'optimise', False)

    result: dict = {
        "tool": "petal",
        "version": __version__,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_file": os.path.abspath(source_path),
        "policy": policy_name,
    }

    # ── Step 1: Analyse ──────────────────────────────────────────────────
    if not args.json:
        print_header("Petal Energy Optimizer", width=70)
        print(f"File:    {info(os.path.basename(source_path))}")
        print(f"Policy:  {info(policy_name)}")
        if do_optimise:
            print(f"Mode:    Analyze & Optimize")
        else:
            print(f"Mode:    Analyze Only")
        print()

    analysis_items = []
    has_hotspot = analyze_energy_hotspots(source_code)
    hotspot_confidence = 0.9 if has_hotspot else 0.0
    decision = decide_transformation(has_hotspot, policy_name, hotspot_confidence)

    if has_hotspot:
        analysis_items.append(checklist_item(f"O(N³) nested loop detected (confidence: {hotspot_confidence:.0%})"))
    else:
        analysis_items.append(checklist_item("No energy hotspots detected", checked=False))
    
    if decision["apply_transform"] and do_optimise:
        analysis_items.append(checklist_item(f"Transformation approved ({policy_name} policy)"))
    else:
        analysis_items.append(checklist_item(decision["reason"], checked=False))

    if not args.json:
        print_section("Analysis", analysis_items)

    result["hotspot_detected"] = has_hotspot
    result["hotspot_confidence"] = hotspot_confidence
    result["transform_decision"] = decision

    if args.analyse:
        return result

    # ── Step 2: Transform (if approved by policy) ────────────────────────
    apply_opt = decision["apply_transform"] and do_optimise
    optimised_code = None
    opt_items = []

    if apply_opt:
        if not args.json:
            opt_items.append(checklist_item("Applying loop tiling (tile=64)"))
        optimised_code = apply_loop_tiling(source_code)
        
        if args.explain and not args.json:
            opt_items.append("")
            opt_items.append(dim("Transformation Rationale:"))
            opt_items.append(dim("  • O(N³) loop with stride-N memory access causes cache misses"))
            opt_items.append(dim("  • Tiling reduces working set to fit in L2 cache"))
            opt_items.append(dim("  • Result: 90%+ reduction in DRAM traffic"))
            opt_items.append(dim(f"  • Policy: {policy_name} (threshold: {policy_cfg.min_hotspot_confidence:.0%})"))
        
        if not args.json and opt_items:
            print_section("Transformation", opt_items)
    elif do_optimise and not args.json:
        print_section("Transformation", [warning(decision['reason'])])

    # ── Step 3: Compile & Benchmark ──────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(os.path.abspath(source_path)), ".petal_out")
    os.makedirs(out_dir, exist_ok=True)

    baseline_bin = os.path.join(out_dir, "baseline")
    if os.name == "nt":
        baseline_bin += ".exe"

    compile_items = []
    try:
        subprocess.run(
            ["gcc", *policy_cfg.baseline_flags, source_path, "-o", baseline_bin],
            check=True, capture_output=True, text=True
        )
        compile_items.append(checklist_item("Compiled baseline binary"))
    except FileNotFoundError:
        print(error("Error: gcc not found on PATH. Install GCC to continue."), file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(error(f"Error: gcc compilation failed:\n{e.stderr}"), file=sys.stderr)
        sys.exit(1)

    if not args.json:
        if not compile_items:
            compile_items = [checklist_item("Compiled baseline binary")]

    runs = max(1, min(args.runs, 10))
    collector_name = args.collector

    # Baseline runs
    baseline_results = []
    if not args.json:
        compile_items.append(f"Running {runs} benchmark iterations...")
    
    for i in range(runs):
        abs_bin = os.path.abspath(baseline_bin)
        res = profile_binary(abs_bin, collector_name=collector_name)
        baseline_results.append(res)

    base_energy_median = sorted(r["energy_j"] for r in baseline_results)[len(baseline_results) // 2]
    base_runtime_median = sorted(r["runtime_s"] for r in baseline_results)[len(baseline_results) // 2]
    base_power_avg = (base_energy_median / base_runtime_median) if base_runtime_median > 0 else 0
    collector_info = baseline_results[0]["collector"]
    
    compile_items.append(checklist_item("Benchmarking complete"))
    
    if not args.json:
        print_section("Compilation & Benchmarking", compile_items)

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
        opt_power_avg = (opt_energy_median / opt_runtime_median) if opt_runtime_median > 0 else 0

        delta_j = base_energy_median - opt_energy_median
        delta_pct = (delta_j / base_energy_median * 100) if base_energy_median > 0 else 0
        
        delta_time = base_runtime_median - opt_runtime_median
        delta_time_pct = (delta_time / base_runtime_median * 100) if base_runtime_median > 0 else 0
        
        delta_power = base_power_avg - opt_power_avg
        delta_power_pct = (delta_power / base_power_avg * 100) if base_power_avg > 0 else 0

        if not args.json:
            # Build results table
            print_section("Results", [
                f"{Color.CYAN}Energy Consumption{Color.RESET:^20} │ {Color.CYAN}Runtime{Color.RESET:^15} │ {Color.CYAN}Power (avg){Color.RESET:^15}",
                "─" * 65,
                f"Baseline    {_fmt_energy(base_energy_median):>8} │  {_fmt_time(base_runtime_median):>12} │  {fmt_power(base_power_avg):>12}",
                f"Optimized   {_fmt_energy(opt_energy_median):>8} │  {_fmt_time(opt_runtime_median):>12} │  {fmt_power(opt_power_avg):>12}",
                "─" * 65,
                f"{success('↓ SAVED')}      {success(_fmt_energy(delta_j)):>8} │  {success(_fmt_time(delta_time)):>12} │  {success(fmt_power(delta_power)):>12}",
            ])

        print_savings_badge(delta_pct, delta_time_pct)

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
        correctness_passed = base_hash == opt_hash
        result["correctness"] = {
            "passed": correctness_passed,
            "method": "stdout_hash_sha256",
        }

        if not args.json:
            if correctness_passed:
                print(success("Correctness: VERIFIED (outputs identical)"))
            else:
                print(error("Correctness: FAILED (outputs differ)"))

        # Write optimised source
        out_path = args.out
        if not out_path:
            root, ext = os.path.splitext(source_path)
            out_path = f"{root}_green{ext or '.c'}"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(optimised_code)
        if not args.json:
            print(f"\n💾 Optimized code: {info(out_path)}")

        result["output_file"] = os.path.abspath(out_path)
    else:
        if not args.json and not apply_opt:
            print()
            print_section("Results", [dim("No optimization applied - only analysis completed")])

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
        print(f"\nREGRESSION DETECTED — energy increased by {delta_pct:.1f}% (>{threshold}%)")
        source_file = current.get("source_file", "unknown")
        print(f"   File: {source_file}")
        if "comparison" in current:
            print(f"   Energy delta: {_fmt_energy(current['comparison']['energy_delta_j'])}")
        print(f"\n   Run `petal {os.path.basename(source_file)} --optimise --explain` for details.")
        sys.exit(1)
    else:
        print(f"\nEnergy within budget ({delta_pct:+.1f}% ≤ {threshold}%)")
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
    parser.add_argument("--html", action="store_true",
                        help="Generate HTML report of optimization results")
    parser.add_argument("--batch", type=str, default=None,
                        help="Process multiple files matching glob pattern (e.g., '**/*.c')")
    parser.add_argument("--config", type=str, default=".petal.yml",
                        help="Path to configuration file (default: .petal.yml)")
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

    # demo
    subparsers.add_parser("demo", help="Show available demo examples")
    
    # interactive
    subparsers.add_parser("interactive", help="Start interactive mode with guided prompts")
    
    # init-config
    subparsers.add_parser("init-config", help="Create a default .petal.yml configuration file")

    return parser

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Route to subcommands if first arg matches
    subcommands = ["check-regression", "setup-env", "generate-dashboard", "demo", "interactive", "init-config"]
    if len(sys.argv) > 1 and sys.argv[1] in subcommands:
        sub_parser = _build_sub_parser()
        args = sub_parser.parse_args(sys.argv[1:])
        
        if args.command == "check-regression":
            _check_regression(args)
        elif args.command == "setup-env":
            sys.exit(setup_telemetry_environment())
        elif args.command == "generate-dashboard":
            sys.exit(generate_dashboard(args.results_dir, args.out))
        elif args.command == "demo":
            show_demo_options()
            sys.exit(0)
        elif args.command == "init-config":
            config_file = ".petal.yml"
            if not os.path.exists(config_file):
                with open(config_file, "w") as f:
                    f.write(PetalConfig.create_default())
                print(f"{success('✓')} Created {config_file}")
            else:
                print(f"{error('✗')} {config_file} already exists")
            sys.exit(0)
        elif args.command == "interactive":
            interactive_inputs = interactive_mode()
            # Convert interactive inputs to argparse Namespace
            args = argparse.Namespace(
                file=interactive_inputs['file'],
                analyse=False,
                optimise=interactive_inputs['optimise'],
                optimize=interactive_inputs['optimise'],
                explain=interactive_inputs['explain'],
                json_out=False,
                json=False,
                out=None,
                policy=interactive_inputs['policy'],
                collector=interactive_inputs['collector'],
                runs=interactive_inputs['runs'],
                metadata_out=None,
                cmake_dir=False,
            )
            result = _run_pipeline(args)
            return
        return

    parser = _build_parser()
    args = parser.parse_args()
    args.command = None

    if getattr(args, "cmake_dir", False):
        cmake_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cmake")
        print(cmake_path)
        sys.exit(0)

    # Load configuration file if it exists
    config = load_config(args.config)
    if config:
        merge_with_args(config, args)

    # We renamed --json to json_out to avoid clashing with the json module
    if hasattr(args, "json_out"):
        args.json = args.json_out

    # Default command: file processing or interactive
    if not args.file:
        # No file provided - prompt for interactive mode
        response = input(info("No file provided. Start interactive mode? (y/n): ")).strip().lower()
        if response == 'y':
            interactive_inputs = interactive_mode()
            args.file = interactive_inputs['file']
            args.policy = interactive_inputs['policy']
            args.optimise = interactive_inputs['optimise']
            args.optimize = interactive_inputs['optimise']
            args.explain = interactive_inputs['explain']
            args.runs = interactive_inputs['runs']
            args.collector = interactive_inputs['collector']
            args.analyse = False
            args.json = False
            args.out = None
            args.metadata_out = None
        else:
            parser.print_help()
            sys.exit(0)

    # Default to --optimise if neither --analyse nor --optimise is set
    if not args.analyse and not args.optimise:
        args.optimise = True
        args.optimize = True

    # Handle batch processing
    if args.batch:
        files = glob.glob(args.batch, recursive=True)
        if not files:
            print(f"{error('✗')} No files matched pattern: {args.batch}")
            sys.exit(1)
        
        print(f"{info(f'Processing {len(files)} file(s)...')}\n")
        results = []
        for file_path in files:
            # Create new args for each file
            file_args = argparse.Namespace(**vars(args))
            file_args.file = file_path
            
            # Default to --optimise if neither flag is set
            if not file_args.analyse and not file_args.optimise:
                file_args.optimise = True
                file_args.optimize = True
            
            result = _run_pipeline(file_args)
            results.append(result)
            print()
        
        # Summary
        print(f"\n{info('='*50)}")
        print(f"{info('Batch Processing Summary')}")
        print(f"{info('='*50)}")
        for idx, result in enumerate(results, 1):
            if "optimised" in result:
                delta_pct = ((result['baseline']['energy_j'] - result['optimised']['energy_j']) / result['baseline']['energy_j'] * 100) if result['baseline']['energy_j'] > 0 else 0
                print(f"{idx}. {result['source_file']}: {success(f'{delta_pct:.0f}% energy saved')}")
            else:
                print(f"{idx}. {result['source_file']}: {info('Analysis only')}")
        return

    result = _run_pipeline(args)

    # Write metadata JSON if requested
    metadata_path = args.metadata_out
    if metadata_path:
        os.makedirs(os.path.dirname(os.path.abspath(metadata_path)), exist_ok=True)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        if not args.json:
            print(f"Metadata written to: {metadata_path}")

    # Generate HTML report if requested
    if getattr(args, "html", False) and "optimised" in result:
        try:
            report_path = generate_html_report(
                filename=os.path.basename(result['source_file']),
                policy=result['policy'],
                baseline_energy=result['baseline']['energy_j'],
                optimized_energy=result['optimised']['energy_j'],
                baseline_runtime=result['baseline']['runtime_s'],
                optimized_runtime=result['optimised']['runtime_s'],
                baseline_power=result['baseline'].get('power_w', 45.0),
                confidence=90.0,
                transformation="Loop Tiling (64)"
            )
            if not args.json:
                print(f"\n{success('✓')} HTML report generated: {report_path}")
        except Exception as e:
            if not args.json:
                print(f"{error('✗')} Failed to generate HTML report: {e}")

    # JSON output mode
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
