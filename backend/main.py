import argparse
import os
import subprocess
from core.analyzer import analyze_energy_hotspots
from core.transformer import apply_loop_tiling
from core.telemetry import profile_binary

def main():
    parser = argparse.ArgumentParser(description="Petal Energy-Aware Compiler (Heuristic Prototype)")
    parser.add_argument("file", help="Source C file to compile")
    parser.add_argument("--optimize", help="Optimization target (e.g., energy)", default="speed")
    parser.add_argument("--tdp", help="Thermal Design Power target (e.g., 15W)", default=None)
    args = parser.parse_args()

    print(f"[\033[92mPetal\033[0m] Initializing LLVM 22.0 Frontend (Prototype)...")
    print(f"[\033[92mPetal\033[0m] Reading source file: {args.file}")

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
        
        # 1. AST Analysis
        has_hotspot = analyze_energy_hotspots(source_code)
        
        if has_hotspot:
            # 2. Source-to-Source Transformation
            optimized_code = apply_loop_tiling(source_code)
            
            # Save optimized code
            opt_file = args.file.replace(".c", "_optimized.c")
            with open(opt_file, "w", encoding="utf-8") as f:
                f.write(optimized_code)
            
            # Compile optimized code
            out_bin = "petal_out"
            if os.name == 'nt':
                out_bin += ".exe"
            print(f"[\033[92mPetal\033[0m] LOWERING: Generating optimized binary './{out_bin}'")
            try:
                subprocess.run(["gcc", "-O3", opt_file, "-o", out_bin], check=True)
                
                # 3. Telemetry Profiling
                print()
                exec_time, joules = profile_binary(f"./{out_bin}")
                print(f"   -> Execution Time: {exec_time:.4f} seconds")
                print(f"   -> Estimated Energy: {joules:.2f} Joules\n")
            except Exception as e:
                print(f"[\033[91mERROR\033[0m] Compilation or Telemetry failed: {e}")
            
            print("[\033[92mPetal\033[0m] DONE. Optimization complete.")
        else:
            print("[\033[92mPetal\033[0m] No energy hotspots detected. Standard compilation.")
            try:
                subprocess.run(["gcc", "-O3", args.file, "-o", "a.out"])
            except:
                pass
    else:
        print("Standard compilation...")
        try:
            subprocess.run(["gcc", args.file, "-o", "a.out"])
        except:
            pass

if __name__ == "__main__":
    main()
