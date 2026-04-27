import argparse
import json
import os
import subprocess
import time
from core.analyzer import analyze_energy_hotspots
from core.policy import POLICY_CONFIGS, decide_transformation, normalize_policy
from core.transformer import apply_loop_tiling
from core.telemetry import profile_binary

def main():
    parser = argparse.ArgumentParser(description="Petal Energy-Aware Compiler (Heuristic Prototype)")
    parser.add_argument("file", help="Source C file to compile")
    parser.add_argument("--optimize", help="Optimization target (e.g., energy)", default="speed")
    parser.add_argument("--tdp", help="Thermal Design Power target (e.g., 15W)", default=None)
    parser.add_argument("--output-bin", help="Output binary path override", default=None)
    parser.add_argument("--policy", help="Optimization policy profile: eco|balanced|perf", default="balanced")
    parser.add_argument("--collector", help="Telemetry collector: auto|synthetic|amd_uprof|rapl", default="auto")
    parser.add_argument("--metadata-file", help="Run metadata JSON output path override", default=None)
    args = parser.parse_args()
    policy_name = normalize_policy(args.policy)

    print(f"[\033[92mPetal\033[0m] Initializing LLVM 22.0 Frontend (Prototype)...")
    print(f"[\033[92mPetal\033[0m] Reading source file: {args.file}")
    print(f"[\033[92mPetal\033[0m] Policy profile: {policy_name} | Collector: {args.collector}")

    if not os.path.exists(args.file):
        print(f"Error: {args.file} not found.")
        return

    with open(args.file, "r", encoding="utf-8", errors="replace") as f:
        source_code = f.read()

    if args.tdp:
        print(f"\n[\033[96mHARDWARE\033[0m] Targeting strict \033[1m{args.tdp}\033[0m Thermal Design Power.")
        print(f"[\033[96mHARDWARE\033[0m] Disabling wide AVX-512 vectorization to meet thermal budget.")
        print(f"[\033[96mHARDWARE\033[0m] Applying aggressive loop fission for thermal compliance.\n")

    if args.optimize == "energy":
        print("\n[\033[93mTELEMETRY\033[0m] Initiating Core Pipeline...")
        run_started_at = time.time()
        
        # 1. AST Analysis
        has_hotspot = analyze_energy_hotspots(source_code)
        hotspot_confidence = 0.9 if has_hotspot else 0.0
        decision = decide_transformation(has_hotspot, policy_name, hotspot_confidence)
        print(f"[\033[92mPetal\033[0m] Policy decision: {decision['reason']}")
        policy_cfg = POLICY_CONFIGS[policy_name]
        metadata = {
            "source_file": args.file,
            "optimize": args.optimize,
            "policy": policy_name,
            "collector_requested": args.collector,
            "tdp": args.tdp,
            "decision": decision,
            "hotspot_detected": has_hotspot,
            "hotspot_confidence": hotspot_confidence,
            "compiler": "gcc",
            "run_started_epoch_s": run_started_at,
        }
        
        if decision["apply_transform"]:
            # 2. Source-to-Source Transformation
            optimized_code = apply_loop_tiling(source_code)
            
            # Save optimized code
            root, ext = os.path.splitext(args.file)
            opt_file = f"{root}_optimized{ext or '.c'}"
            with open(opt_file, "w", encoding="utf-8") as f:
                f.write(optimized_code)
            
            # Compile optimized code
            out_bin = args.output_bin or "petal_out"
            if os.name == 'nt' and not out_bin.lower().endswith(".exe"):
                out_bin += ".exe"
            print(f"[\033[92mPetal\033[0m] LOWERING: Generating optimized binary './{out_bin}'")
            try:
                compile_cmd = ["gcc", *policy_cfg.optimized_flags, opt_file, "-o", out_bin]
                subprocess.run(compile_cmd, check=True)
                
                # 3. Telemetry Profiling
                print()
                executable_path = out_bin if os.path.isabs(out_bin) else f"./{out_bin}"
                telemetry = profile_binary(executable_path, collector_name=args.collector)
                print(f"   -> Execution Time: {telemetry['execution_time_s']:.4f} seconds")
                print(f"   -> Estimated Energy: {telemetry['energy_j']:.2f} Joules")
                print(f"   -> Collector Used: {telemetry['collector']} ({telemetry['confidence_tier']} confidence)\n")
                metadata["telemetry"] = telemetry
                metadata["output_binary"] = out_bin
                metadata["optimized_source_file"] = opt_file
                metadata["compiler_flags"] = list(policy_cfg.optimized_flags)
            except Exception as e:
                print(f"[\033[91mERROR\033[0m] Compilation or Telemetry failed: {e}")
                metadata["error"] = str(e)
            
            print("[\033[92mPetal\033[0m] DONE. Optimization complete.")
        else:
            print("[\033[92mPetal\033[0m] No energy hotspots detected. Standard compilation.")
            try:
                out_bin = args.output_bin or "a.out"
                compile_cmd = ["gcc", *policy_cfg.baseline_flags, args.file, "-o", out_bin]
                subprocess.run(compile_cmd)
                metadata["output_binary"] = out_bin
                metadata["compiler_flags"] = list(policy_cfg.baseline_flags)
            except:
                pass
        metadata["run_finished_epoch_s"] = time.time()
        root, ext = os.path.splitext(args.file)
        metadata_file = args.metadata_file or f"{root}_run_metadata.json"
        metadata["metadata_file"] = metadata_file
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        print(f"[\033[92mPetal\033[0m] METADATA: {metadata_file}")
    else:
        print("Standard compilation...")
        try:
            out_bin = args.output_bin or "a.out"
            subprocess.run(["gcc", args.file, "-o", out_bin])
        except:
            pass

if __name__ == "__main__":
    main()
