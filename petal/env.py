"""Environment setup for hardware telemetry permissions."""

import os
import platform
import subprocess
import sys


def setup_telemetry_environment() -> int:
    """Configure Linux to allow perf_stat to read hardware energy counters."""
    if platform.system().lower() != "linux":
        print("⚠ Petal hardware telemetry setup is only supported on Linux.")
        print("  On macOS/Windows, Petal will use Synthetic telemetry.")
        return 0

    print("Petal Telemetry Environment Setup")
    print("-----------------------------------")
    print("To read hardware energy counters (RAPL / perf), Petal needs permission")
    print("to access kernel performance events.")
    print("\nWe will run: `sudo sysctl -w kernel.perf_event_paranoid=-1`")
    print("This allows user-space tools to monitor energy consumption.")
    print("Warning: This slightly lowers the system's security profile against local profiling.\n")

    try:
        response = input("Proceed with setup? [y/N]: ").strip().lower()
        if response not in ("y", "yes"):
            print("Setup aborted.")
            return 1
    except KeyboardInterrupt:
        print("\nSetup aborted.")
        return 1
    except EOFError:
        # E.g. in CI
        print("\nNon-interactive mode: aborting. Run manually or set explicitly.")
        return 1

    try:
        print("\nRequesting sudo privileges...")
        result = subprocess.run(
            ["sudo", "sysctl", "-w", "kernel.perf_event_paranoid=-1"],
            check=True,
            text=True,
            capture_output=True
        )
        print("✓ Telemetry environment configured successfully.")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Error executing sysctl: {e.stderr}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("Error: 'sudo' or 'sysctl' not found.", file=sys.stderr)
        return 1
