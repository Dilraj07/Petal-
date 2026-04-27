import argparse
import json
import os
import subprocess
import time
import hashlib
import statistics

from core.analyzer import analyze_energy_hotspots
from core.policy import POLICY_CONFIGS, decide_transformation, normalize_policy
from core.transformer import apply_loop_tiling
from core.telemetry import profile_binary

def calculate_stats(data_list):
    if not data_list:
        return {"median": 0, "min": 0, "max": 0}
    return {
        "median": statistics.median(data_list),
        "min": min(data_list),
        "max": max(data_list)
    }

def _tdp_advisory(tdp_arg, energy_stats, runtime_stats):
    """Return a TDP budget advisory string, or None if --tdp was not set."""
    if not tdp_arg:
        return None
    try:
        tdp_w = float(tdp_arg.rstrip("Ww"))
    except ValueError:
        return f"Could not parse TDP value: {tdp_arg!r}"
    med_e = energy_stats.get("median", 0)
    med_r = runtime_stats.get("median", 0)
    avg_power = (med_e / med_r) if med_r > 0 else 0
    status = "within budget ✓" if avg_power <= tdp_w else "EXCEEDS BUDGET ✗"
    advisory = (
        f"TDP Budget: {tdp_w:.0f}W | "
        f"Estimated avg power: {avg_power:.2f}W → {status}"
    )
    print(f"[\033[92mPetal\033[0m] {advisory}")
    return advisory

def main():
    parser = argparse.ArgumentParser(description="Petal Energy-Aware Compiler (Heuristic Prototype)")
    parser.add_argument("file", help="Source C file to compile")
    parser.add_argument("--optimize", help="Optimization target (e.g., energy)", default="speed")
    parser.add_argument("--tdp", help="Thermal Design Power target (e.g., 15W)", default=None)
    parser.add_argument("--output-bin", help="Output binary path override", default=None)
    parser.add_argument("--policy", help="Optimization policy profile: eco|balanced|perf", default="balanced")
    parser.add_argument("--collector", help="Telemetry collector: auto|synthetic|amd_uprof|rapl", default="auto")
    parser.add_argument("--metadata-file", help="Run metadata JSON output path override", default=None)
    parser.add_argument("--runs", type=int, help="Number of times to run each binary", default=1)
    parser.add_argument("--emit-report", action="store_true", help="Emit full artifact report")
    parser.add_argument("--output-dir", help="Output directory for artifacts", default="./out")
    args = parser.parse_args()
    
    policy_name = normalize_policy(args.policy)
    policy_cfg = POLICY_CONFIGS[policy_name]

    print(f"[\033[92mPetal\033[0m] Initializing LLVM 22.0 Frontend (Prototype)...")
    print(f"[\033[92mPetal\033[0m] Reading source file: {args.file}")
    print(f"[\033[92mPetal\033[0m] Policy profile: {policy_name} | Collector: {args.collector}")

    if not os.path.exists(args.file):
        print(f"Error: {args.file} not found.")
        return

    with open(args.file, "r", encoding="utf-8", errors="replace") as f:
        source_code = f.read()

    # Make output dir if emitting report
    out_dir = args.output_dir if args.emit_report else os.path.dirname(args.file)
    if args.emit_report and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    if args.optimize == "energy":
        print("\n[\033[93mTELEMETRY\033[0m] Initiating Core Pipeline...")
        run_started_at = time.time()
        
        has_hotspot = analyze_energy_hotspots(source_code)
        hotspot_confidence = 0.9 if has_hotspot else 0.0
        decision = decide_transformation(has_hotspot, policy_name, hotspot_confidence)
        print(f"[\033[92mPetal\033[0m] Policy decision: {decision['reason']}")
        
        # Compile Baseline
        baseline_bin = os.path.join(out_dir, "baseline.bin")
        if os.name == 'nt' and not baseline_bin.lower().endswith(".exe"):
            baseline_bin += ".exe"
        try:
            subprocess.run(["gcc", *policy_cfg.baseline_flags, args.file, "-o", baseline_bin], check=True)
            print(f"[\033[92mPetal\033[0m] Compiled Baseline Binary: {baseline_bin}")
        except Exception as e:
            print(f"Error compiling baseline: {e}")
            return

        opt_file = None
        optimized_bin = None
        apply_opt = decision["apply_transform"]
        
        if apply_opt:
            optimized_code = apply_loop_tiling(source_code)
            
            root, ext = os.path.splitext(os.path.basename(args.file))
            opt_file = os.path.join(out_dir, f"{root}_optimized{ext or '.c'}")
            with open(opt_file, "w", encoding="utf-8") as f:
                f.write(optimized_code)
            
            optimized_bin = os.path.join(out_dir, "optimized.bin")
            if os.name == 'nt' and not optimized_bin.lower().endswith(".exe"):
                optimized_bin += ".exe"
            try:
                subprocess.run(["gcc", *policy_cfg.optimized_flags, opt_file, "-o", optimized_bin], check=True)
                print(f"[\033[92mPetal\033[0m] Compiled Optimized Binary: {optimized_bin}")
            except Exception as e:
                print(f"Error compiling optimized: {e}")
                return

        print(f"[\033[92mPetal\033[0m] Running profiles ({args.runs} runs per variant)...")
        
        baseline_runs = []
        optimized_runs = []
        
        def run_variant(binary_path, variant_name, runs_list, jsonl_file):
            abs_bin = binary_path if os.path.isabs(binary_path) else os.path.abspath(binary_path)
            for i in range(args.runs):
                res = profile_binary(abs_bin, collector_name=args.collector)
                
                stdout_str = res["stdout"] or ""
                stdout_sha256 = hashlib.sha256(stdout_str.encode()).hexdigest()
                
                run_data = {
                    "run_id": i + 1,
                    "variant": variant_name,
                    "runtime_s": res["runtime_s"],
                    "energy_j": res["energy_j"],
                    "stdout_sha256": stdout_sha256,
                    "stderr_truncated": (res["stderr"] or "")[:200],
                    "exit_code": res["exit_code"]
                }
                runs_list.append(run_data)
                
                # Emit live update for server.py
                update_evt = {
                    "variant": variant_name,
                    "run_index": i + 1,
                    "runtime_s": res["runtime_s"],
                    "energy_j": res["energy_j"],
                    "collector_used": res["collector"]["used"],
                    "confidence": res["collector"]["confidence"]
                }
                print(f"@@RUN_UPDATE@@: {json.dumps(update_evt)}")
                
                if args.emit_report:
                    with open(jsonl_file, "a") as f:
                        f.write(json.dumps(run_data) + "\n")
                        
            # Store the collector details to include in global metadata later
            return res["collector"], res["measurement"]
        
        base_runs_file = os.path.join(out_dir, "baseline.runs.jsonl")
        opt_runs_file = os.path.join(out_dir, "optimized.runs.jsonl")
        
        if args.emit_report:
            # Clear old files
            open(base_runs_file, 'w').close()
            if apply_opt:
                open(opt_runs_file, 'w').close()

        col_details, meas_details = run_variant(baseline_bin, "baseline", baseline_runs, base_runs_file)
        
        if apply_opt:
            run_variant(optimized_bin, "optimized", optimized_runs, opt_runs_file)

        # Correctness check
        correctness = {
            "passed": True,
            "method": "stdout_hash_sha256",
            "mismatches": 0,
            "total_runs_per_variant": args.runs,
            "details": "Only baseline ran."
        }
        
        if apply_opt:
            mismatches = 0
            for i in range(args.runs):
                base_sha = baseline_runs[i]["stdout_sha256"]
                opt_sha = optimized_runs[i]["stdout_sha256"]
                optimized_runs[i]["correctness"] = {
                    "passed": base_sha == opt_sha,
                    "method": "stdout_hash_sha256",
                    "baseline_stdout_sha256": base_sha
                }
                if base_sha != opt_sha:
                    mismatches += 1
            
            correctness["mismatches"] = mismatches
            correctness["passed"] = mismatches == 0
            if mismatches == 0:
                correctness["details"] = "All optimized outputs matched baseline (exact hash)."
            else:
                correctness["details"] = f"Detected {mismatches} mismatch(es) between baseline and optimized."
                
        # Stats
        base_runtimes = [r["runtime_s"] for r in baseline_runs]
        base_energies = [r["energy_j"] for r in baseline_runs]
        base_runtime_stats = calculate_stats(base_runtimes)
        base_energy_stats = calculate_stats(base_energies)
        
        comparison = {}
        if apply_opt:
            opt_runtimes = [r["runtime_s"] for r in optimized_runs]
            opt_energies = [r["energy_j"] for r in optimized_runs]
            opt_runtime_stats = calculate_stats(opt_runtimes)
            opt_energy_stats = calculate_stats(opt_energies)
            
            b_e = base_energy_stats["median"]
            o_e = opt_energy_stats["median"]
            energy_delta_pct = 100 * (o_e - b_e) / b_e if b_e else 0
            
            b_r = base_runtime_stats["median"]
            o_r = opt_runtime_stats["median"]
            runtime_delta_pct = 100 * (o_r - b_r) / b_r if b_r else 0

            comparison = {
                "energy_delta_pct": round(energy_delta_pct, 2),
                "runtime_delta_pct": round(runtime_delta_pct, 2),
                "energy_median": {"baseline": b_e, "optimized": o_e},
                "energy_min": {"baseline": base_energy_stats["min"], "optimized": opt_energy_stats["min"]},
                "energy_max": {"baseline": base_energy_stats["max"], "optimized": opt_energy_stats["max"]},
                "runtime_median": {"baseline": b_r, "optimized": o_r},
                "runtime_min": {"baseline": base_runtime_stats["min"], "optimized": opt_runtime_stats["min"]},
                "runtime_max": {"baseline": base_runtime_stats["max"], "optimized": opt_runtime_stats["max"]},
                "policy_used": policy_name,
                "flags_used": " ".join(policy_cfg.optimized_flags)
            }

        metadata = {
            "tool": "petal",
            "version": "0.1.0",
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "input": {
                "source_file": args.file,
                "deterministic": True
            },
            "policy": {
                "requested": policy_name,
                "applied_transform": apply_opt,
                "transform_type": "loop_tiling" if apply_opt else None
            },
            "build": {
                "compiler": "gcc",
                "baseline_flags": " ".join(policy_cfg.baseline_flags),
                "optimized_flags": " ".join(policy_cfg.optimized_flags) if apply_opt else None,
                "notes": _tdp_advisory(args.tdp, base_energy_stats, base_runtime_stats)
            },
            "collector": col_details,
            "measurement": meas_details,
            "runs": {
                "per_variant": args.runs,
                "runtime_unit": "seconds",
                "energy_unit": "joules"
            },
            "comparison": comparison,
            "correctness": correctness,
            "files": {
                "baseline_binary": baseline_bin,
                "optimized_binary": optimized_bin,
                "baseline_runs_log": base_runs_file if args.emit_report else None,
                "optimized_runs_log": opt_runs_file if args.emit_report and apply_opt else None
            }
        }
        
        metadata_file = args.metadata_file or os.path.join(out_dir, "metadata.json")
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        print(f"[\033[92mPetal\033[0m] METADATA: {metadata_file}")
        
    else:
        print("Standard compilation...")
        try:
            out_bin = args.output_bin or "a.out"
            subprocess.run(["gcc", args.file, "-o", out_bin], check=True)
            print(f"[\033[92mPetal\033[0m] Compiled: {out_bin}")
        except Exception as e:
            print(f"[\033[91mError\033[0m] gcc failed: {e}")
            raise SystemExit(1)

if __name__ == "__main__":
    main()
