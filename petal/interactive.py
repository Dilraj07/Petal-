"""Interactive mode for Petal CLI."""

import os
import sys
from pathlib import Path
from typing import Optional

from petal.formatter import *


def prompt_file() -> str:
    """Interactively prompt user for C source file."""
    print(info("Welcome to Petal — Energy-Aware Compilation"))
    print()
    
    while True:
        file_path = input("Enter C source file path: ").strip()
        
        if not file_path:
            print(error("File path cannot be empty"))
            continue
        
        file_path = os.path.expanduser(file_path)
        
        if not os.path.isfile(file_path):
            print(error(f"File not found: {file_path}"))
            continue
        
        if not file_path.endswith(('.c', '.cpp', '.cc', '.cxx')):
            response = input(warning("File doesn't end with .c/.cpp. Continue? (y/n): "))
            if response.lower() != 'y':
                continue
        
        print(success(f"File: {file_path}"))
        return file_path


def prompt_policy() -> str:
    """Interactively prompt user for optimization policy."""
    print()
    print("Select optimization policy:")
    print(f"  1) {info('eco')}        — Maximum energy savings (may reduce speed)")
    print(f"  2) {info('balanced')}   — Balance energy and speed (default)")
    print(f"  3) {info('perf')}       — Maximum speed (may use more energy)")
    print()
    
    while True:
        choice = input("Enter choice (1-3): ").strip()
        
        if choice == '1':
            print(success("Policy: eco"))
            return 'eco'
        elif choice == '2':
            print(success("Policy: balanced"))
            return 'balanced'
        elif choice == '3':
            print(success("Policy: perf"))
            return 'perf'
        else:
            print(error("Invalid choice. Enter 1, 2, or 3."))


def prompt_optimize() -> bool:
    """Ask if user wants optimization."""
    print()
    response = input("Optimize the code? (y/n) [default: y]: ").strip().lower()
    
    should_optimize = response != 'n'
    if should_optimize:
        print(success("Will optimize and compare"))
    else:
        print(info("ℹ Will only analyze"))
    
    return should_optimize


def prompt_explain() -> bool:
    """Ask if user wants detailed explanation."""
    print()
    response = input("Show detailed explanation? (y/n) [default: n]: ").strip().lower()
    
    should_explain = response == 'y'
    if should_explain:
        print(success("Will show transformation details"))
    else:
        print(info("ℹ Will show summary"))
    
    return should_explain


def prompt_runs() -> int:
    """Ask user how many benchmark runs."""
    print()
    
    while True:
        runs_str = input("Number of benchmark runs (1-10) [default: 5]: ").strip()
        
        if not runs_str:
            runs = 5
            print(success("Runs: 5"))
            return runs
        
        try:
            runs = int(runs_str)
            if 1 <= runs <= 10:
                print(success(f"Runs: {runs}"))
                return runs
            else:
                print(error("Enter a number between 1 and 10"))
        except ValueError:
            print(error("Invalid number. Enter 1-10"))


def prompt_collector() -> str:
    """Ask user for telemetry collector."""
    print()
    print("Select telemetry source:")
    print(f"  1) {info('auto')}       — Auto-detect best available (recommended)")
    print(f"  2) {info('synthetic')}  — CPU load estimation (always available)")
    print(f"  3) {info('rapl')}       — Intel RAPL (Linux only)")
    print(f"  4) {info('amd_uprof')}  — AMD uProf (if installed)")
    print()
    
    while True:
        choice = input("Enter choice (1-4) [default: 1]: ").strip()
        
        if not choice or choice == '1':
            print(success("Telemetry: auto"))
            return 'auto'
        elif choice == '2':
            print(success("Telemetry: synthetic"))
            return 'synthetic'
        elif choice == '3':
            print(success("Telemetry: rapl"))
            return 'rapl'
        elif choice == '4':
            print(success("Telemetry: amd_uprof"))
            return 'amd_uprof'
        else:
            print(error("Invalid choice. Enter 1-4."))


def confirm_settings(file_path: str, policy: str, optimize: bool, explain: bool, 
                     runs: int, collector: str) -> bool:
    """Show summary and ask for confirmation."""
    print()
    print_header("Summary", width=60)
    
    print(f"File:       {info(file_path)}")
    print(f"Policy:     {info(policy)}")
    print(f"Optimize:   {success('Yes') if optimize else warning('No')}")
    print(f"Explain:    {success('Yes') if explain else warning('No')}")
    print(f"Runs:       {info(str(runs))}")
    print(f"Telemetry:  {info(collector)}")
    print()
    
    response = input("Proceed? (y/n) [default: y]: ").strip().lower()
    
    if response == 'n':
        print(warning("Cancelled"))
        return False
    
    return True


def interactive_mode() -> dict:
    """Run interactive mode to gather user inputs."""
    try:
        file_path = prompt_file()
        policy = prompt_policy()
        optimize = prompt_optimize()
        explain = prompt_explain()
        runs = prompt_runs()
        collector = prompt_collector()
        
        if not confirm_settings(file_path, policy, optimize, explain, runs, collector):
            sys.exit(0)
        
        return {
            'file': file_path,
            'policy': policy,
            'optimise': optimize,
            'explain': explain,
            'runs': runs,
            'collector': collector,
        }
    
    except KeyboardInterrupt:
        print()
        print(warning("Cancelled by user"))
        sys.exit(0)
    except EOFError:
        print()
        print(warning("End of input"))
        sys.exit(0)


def show_demo_options() -> None:
    """Show available demo examples."""
    print_header("Available Examples", width=70)
    
    examples = [
        ("matrix_mult", "512×512 matrix multiplication", "~38% energy saved"),
        ("convolution", "Image convolution filter", "~35% energy saved"),
        ("matrix_exp", "Matrix exponentiation", "~30% energy saved"),
    ]
    
    print("Run examples with: petal demo <name>\n")
    
    for name, desc, savings in examples:
        print(f"{info(name):20} — {desc:40} {success(savings)}")
    
    print()
    print(f"Or run all: {accent('petal demo all')}")
    print()
