import argparse
import json
import os
import subprocess
import time
import hashlib
import statistics
import shutil

from core.analyzer import analyze_energy_hotspots
from core.policy import POLICY_CONFIGS, decide_transformation, normalize_policy
from core.transformer import apply_loop_tiling
from core.telemetry import profile_binary
import structlog

logger = structlog.get_logger("main")

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
    logger.info(advisory)
    return advisory

def run_pipeline(file_path, optimize="speed", policy="balanced", collector="auto", tdp_arg=None, runs=1, emit_report=False, output_dir="./out", output_bin=None, metadata_file=None):
    # Validate GCC is available
    if not shutil.which("gcc"):
        raise RuntimeError("GCC compiler not found. Please install GCC or ensure it is in your PATH.")
    
    policy_name = normalize_policy(policy)
    policy_cfg = POLICY_CONFIGS[policy_name]

    logger.info("Initializing Energy-Aware Compilation Pipeline...")
    logger.info("Reading source file", file_path=file_path)
    logger.info("Policy profile and Collector", policy=policy_name, collector=collector)

    if not os.path.exists(file_path):
        logger.error("File not found", file_path=file_path)
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        source_code = f.read()

    # Make output dir if emitting report
    out_dir = output_dir if emit_report else os.path.dirname(file_path)
    if emit_report and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    if optimize == "energy":
        logger.info("Initiating Core Pipeline...")
        run_started_at = time.time()
        
        has_hotspot = analyze_energy_hotspots(source_code)
        hotspot_confidence = 0.9 if has_hotspot else 0.0
        decision = decide_transformation(has_hotspot, policy_name, hotspot_confidence)
        logger.info("Policy decision", reason=decision['reason'])
        
        # Compile Baseline
        baseline_bin = os.path.join(out_dir, "baseline.bin")
        if os.name == 'nt' and not baseline_bin.lower().endswith(".exe"):
            baseline_bin += ".exe"
        try:
            subprocess.run(["gcc", *policy_cfg.baseline_flags, file_path, "-o", baseline_bin], check=True, timeout=120)
            logger.info("Compiled Baseline Binary", binary=baseline_bin)
        except subprocess.TimeoutExpired:
            logger.error("Baseline compilation timed out after 120 seconds")
            raise RuntimeError("Baseline compilation timed out after 120 seconds.")
        except subprocess.CalledProcessError as e:
            error_msg = (
                f"Compilation failed with exit code {e.returncode}.\n"
                f"GCC Output:\n{e.stderr if e.stderr else 'No output captured.'}\n"
                "Hint: Ensure GCC is installed and the source code is valid C."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from None
        except Exception as e:
            logger.error("Error compiling baseline", error=str(e))
            raise RuntimeError(f"Error compiling baseline: {e}")

        opt_file = None
        optimized_bin = None
        apply_opt = decision["apply_transform"]
        
        if apply_opt:
            optimized_code = apply_loop_tiling(source_code, block_size=policy_cfg.block_size)
            
            root, ext = os.path.splitext(os.path.basename(file_path))
            opt_file = os.path.join(out_dir, f"{root}_optimized{ext or '.c'}")
            with open(opt_file, "w", encoding="utf-8") as f:
                f.write(optimized_code)
            
            optimized_bin = os.path.join(out_dir, "optimized.bin")
            if os.name == 'nt' and not optimized_bin.lower().endswith(".exe"):
                optimized_bin += ".exe"
            try:
                subprocess.run(["gcc", *policy_cfg.optimized_flags, opt_file, "-o", optimized_bin], check=True, timeout=120)
                logger.info("Compiled Optimized Binary", binary=optimized_bin)
            except subprocess.TimeoutExpired:
                logger.error("Optimized compilation timed out after 120 seconds")
                raise RuntimeError("Optimized compilation timed out after 120 seconds.")
            except subprocess.CalledProcessError as e:
                error_msg = (
                    f"Compilation failed with exit code {e.returncode}.\n"
                    f"GCC Output:\n{e.stderr if e.stderr else 'No output captured.'}\n"
                    "Hint: Ensure GCC is installed and the source code is valid C."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg) from None
            except Exception as e:
                logger.error("Error compiling optimized", error=str(e))
                raise RuntimeError(f"Error compiling optimized: {e}")

        logger.info("Running profiles", runs_per_variant=runs)
        
        baseline_runs = []
        optimized_runs = []
        
        base_runs_file = os.path.join(out_dir, "baseline_runs.jsonl")
        opt_runs_file = os.path.join(out_dir, "optimized_runs.jsonl")

        for r_idx in range(1, runs + 1):
            res = profile_binary(baseline_bin, collector)
            update_evt = {
                "variant": "baseline",
                "run_index": r_idx,
                "runtime_s": res["runtime_s"],
                "energy_j": res["energy_j"],
                "collector_used": res["collector"]["used"],
                "confidence": res["collector"]["confidence"]
            }
            logger.info("run_update", run_data=update_evt)
            baseline_runs.append(res)
            
        if apply_opt:
            for r_idx in range(1, runs + 1):
                res = profile_binary(optimized_bin, collector)
                update_evt = {
                    "variant": "optimized",
                    "run_index": r_idx,
                    "runtime_s": res["runtime_s"],
                    "energy_j": res["energy_j"],
                    "collector_used": res["collector"]["used"],
                    "confidence": res["collector"]["confidence"]
                }
                logger.info("run_update", run_data=update_evt)
                optimized_runs.append(res)
        
        if emit_report:
            with open(base_runs_file, "w") as bf:
                for br in baseline_runs:
                    bf.write(json.dumps(br) + "\n")
            if apply_opt:
                with open(opt_runs_file, "w") as of:
                    for _or in optimized_runs:
                        of.write(json.dumps(_or) + "\n")

        # Gather standard pipeline stats...
        if not baseline_runs:
            logger.error("No baseline profiling results collected")
            raise RuntimeError("Baseline profiling failed: no results collected")
        
        base_runtimes = [r["runtime_s"] for r in baseline_runs]
        base_energies = [r["energy_j"] for r in baseline_runs]
        opt_runtimes = [r["runtime_s"] for r in optimized_runs] if apply_opt else []
        opt_energies = [r["energy_j"] for r in optimized_runs] if apply_opt else []
        
        base_runtime_stats = calculate_stats(base_runtimes)
        base_energy_stats = calculate_stats(base_energies)
        opt_runtime_stats = calculate_stats(opt_runtimes)
        opt_energy_stats = calculate_stats(opt_energies)
        
        col_details = baseline_runs[0]["collector"] if baseline_runs else {}
        meas_details = baseline_runs[0]["measurement"] if baseline_runs else {}

        comparison = None
        correctness = {"passed": None, "note": "No optimization applied."}
        
        if apply_opt and baseline_runs and optimized_runs:
            b_out_hash = hashlib.sha256(baseline_runs[0].get("stdout", "").encode()).hexdigest()
            o_out_hash = hashlib.sha256(optimized_runs[0].get("stdout", "").encode()).hexdigest()
            correctness = {
                "passed": b_out_hash == o_out_hash,
                "note": "Outputs identical." if b_out_hash == o_out_hash else "Output mismatch detected!",
                "baseline_hash": b_out_hash,
                "optimized_hash": o_out_hash
            }
            
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
                "source_file": file_path,
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
                "notes": _tdp_advisory(tdp_arg, base_energy_stats, base_runtime_stats)
            },
            "collector": col_details,
            "measurement": meas_details,
            "runs": {
                "per_variant": runs,
                "runtime_unit": "seconds",
                "energy_unit": "joules"
            },
            "comparison": comparison,
            "correctness": correctness,
            "files": {
                "baseline_binary": baseline_bin,
                "optimized_binary": optimized_bin,
                "baseline_runs_log": base_runs_file if emit_report else None,
                "optimized_runs_log": opt_runs_file if emit_report and apply_opt else None
            }
        }
        
        mf = metadata_file or os.path.join(out_dir, "metadata.json")
        with open(mf, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        logger.info("METADATA", metadata_file=mf)
        
        return metadata
        
    else:
        logger.info("Standard compilation...")
        out_bin = output_bin or "a.out"
        try:
            subprocess.run(["gcc", file_path, "-o", out_bin], check=True, timeout=120)
        except subprocess.TimeoutExpired:
            logger.error("Standard compilation timed out after 120 seconds")
            raise RuntimeError("Compilation timed out after 120 seconds.")
        logger.info("Compiled", binary=out_bin)
        return {"status": "ok", "binary": out_bin}

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
    
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
        ]
    )
    
    try:
        run_pipeline(
            file_path=args.file,
            optimize=args.optimize,
            policy=args.policy,
            collector=args.collector,
            tdp_arg=args.tdp,
            runs=args.runs,
            emit_report=args.emit_report,
            output_dir=args.output_dir,
            output_bin=args.output_bin,
            metadata_file=args.metadata_file
        )
    except Exception as e:
        logger.error("Pipeline execution failed", error=str(e))
        raise SystemExit(1)

if __name__ == "__main__":
    main()
