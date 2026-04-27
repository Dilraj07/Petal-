import shutil
import subprocess
import time
from dataclasses import asdict, dataclass

import psutil

# Assume a standard laptop CPU has a max TDP (Thermal Design Power) of 45 Watts
ESTIMATED_TDP_WATTS = 45.0

class BaseTelemetryCollector:
    name = "base"
    confidence_tier = "unknown"
    note = ""

    def is_available(self):
        return True

    def collect(self, executable_path):
        raise NotImplementedError

class SyntheticCpuTelemetryCollector(BaseTelemetryCollector):
    name = "synthetic"
    confidence_tier = "low"
    note = "Energy numbers are derived from a synthetic CPU-time model, not from a hardware Joule counter."

    def collect(self, executable_path):
        start_time = time.perf_counter()

        process = subprocess.Popen(
            [executable_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            ps_proc = psutil.Process(process.pid)
            start_cpu = ps_proc.cpu_times()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            start_cpu = None

        stdout_out, stderr_out = process.communicate()
        end_time = time.perf_counter()
        wall_time = end_time - start_time

        # Use CPU-time accounting instead of polling:
        # cpu_times() is always populated by the OS, even for sub-100ms binaries.
        try:
            if start_cpu is not None:
                end_cpu = ps_proc.cpu_times()
                cpu_time_s = (
                    (end_cpu.user - start_cpu.user) +
                    (end_cpu.system - start_cpu.system)
                )
            else:
                cpu_time_s = wall_time  # conservative fallback
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            cpu_time_s = wall_time

        # cpu_utilisation ratio: how much of wall time was active CPU work
        cpu_ratio = (cpu_time_s / wall_time) if wall_time > 0 else 1.0
        # Clamp to [0, 1] — multicore can push ratio > 1 on a single-threaded workload
        cpu_ratio = min(cpu_ratio, 1.0)
        estimated_power = cpu_ratio * ESTIMATED_TDP_WATTS
        total_joules = wall_time * estimated_power

        return {
            "runtime_s": wall_time,
            "energy_j": total_joules,
            "stdout": stdout_out,
            "stderr": stderr_out,
            "exit_code": process.returncode
        }

class AmdUprofTelemetryCollector(BaseTelemetryCollector):
    name = "amd_uprof"
    confidence_tier = "high"
    note = "Hardware counter via AMD uProf."

    def is_available(self):
        return shutil.which("AMDuProfCLI") is not None

    def collect(self, executable_path):
        raise NotImplementedError("AMD uProf collector adapter is not implemented yet.")

class RaplTelemetryCollector(BaseTelemetryCollector):
    name = "rapl"
    confidence_tier = "high"
    note = "Package energy via /sys/class/powercap/intel-rapl:0/energy_uj"

    def is_available(self):
        return False

    def collect(self, executable_path):
        raise NotImplementedError("RAPL collector adapter is not implemented yet.")

COLLECTORS = {
    "synthetic": SyntheticCpuTelemetryCollector,
    "amd_uprof": AmdUprofTelemetryCollector,
    "rapl": RaplTelemetryCollector,
}

def resolve_collector(collector_name):
    requested = (collector_name or "auto").strip().lower()
    synthetic = SyntheticCpuTelemetryCollector()
    if requested == "auto":
        for name in ("amd_uprof", "rapl"):
            collector = COLLECTORS[name]()
            if collector.is_available():
                return collector, requested
        return synthetic, requested
    collector_cls = COLLECTORS.get(requested)
    if not collector_cls:
        return synthetic, requested
    collector = collector_cls()
    if collector.is_available():
        return collector, requested
    return synthetic, requested

def profile_binary(executable_path, collector_name="auto"):
    collector, requested = resolve_collector(collector_name)
    # print(f"[\033[95mTelemetry\033[0m] Profiling execution via collector '{collector.name}' (requested: '{requested}')...")
    result = collector.collect(executable_path)
    
    fallback_used = collector.name == "synthetic" and requested not in ("synthetic", "auto")
    
    is_est = collector.confidence_tier == "low"
    payload = {
        "runtime_s": result["runtime_s"],
        "energy_j": result["energy_j"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "collector": {
            "requested": requested,
            "used": collector.name,
            "fallback_used": fallback_used,
            "confidence": collector.confidence_tier,
            "note": collector.note
        },
        "measurement": {
            "energy_domain": None if is_est else "package",
            "unit": "joules-est" if is_est else "joules",
            "is_estimate": is_est
        }
    }
    return payload
