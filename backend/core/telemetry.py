import os
import re
import shutil
import subprocess
import time

import psutil

# Assume a standard laptop CPU has a max TDP (Thermal Design Power) of 45 Watts
ESTIMATED_TDP_WATTS = 45.0


class BaseTelemetryCollector:
    name: str = "base"
    confidence_tier: str = "unknown"
    note: str = ""

    def is_available(self) -> bool:
        return True

    def collect(self, executable_path: str) -> dict:
        raise NotImplementedError

    @property
    def quality_label(self) -> str:
        if self.confidence_tier == "high":
            return f"source: {self.name}, quality: hardware"
        return f"source: {self.name}, quality: estimated ±35%"


# ---------------------------------------------------------------------------
# Priority 4 — Synthetic (CPU load × TDP, last resort)
# ---------------------------------------------------------------------------
class SyntheticCpuTelemetryCollector(BaseTelemetryCollector):
    name = "synthetic"
    confidence_tier = "low"
    note = "Energy numbers are derived from a synthetic CPU-time model, not from a hardware Joule counter."

    def collect(self, executable_path: str) -> dict:
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


# ---------------------------------------------------------------------------
# Priority 1 — AMD uProf (bare-metal AMD, highest accuracy, Zen PMCs)
# ---------------------------------------------------------------------------
class AmdUprofTelemetryCollector(BaseTelemetryCollector):
    name = "amd_uprof"
    confidence_tier = "high"
    note = "Hardware counter via AMD uProf."

    def is_available(self) -> bool:
        return shutil.which("AMDuProfCLI") is not None

    def collect(self, executable_path: str) -> dict:
        raise NotImplementedError("AMD uProf collector adapter is not implemented yet.")


# ---------------------------------------------------------------------------
# Priority 2 — Intel/AMD RAPL via /sys/class/powercap (Linux only)
# ---------------------------------------------------------------------------
_RAPL_ENERGY_PATH = "/sys/class/powercap/intel-rapl:0/energy_uj"


class RaplTelemetryCollector(BaseTelemetryCollector):
    name = "rapl"
    confidence_tier = "high"
    note = "Package energy via /sys/class/powercap/intel-rapl:0/energy_uj"

    def is_available(self) -> bool:
        return os.path.isfile(_RAPL_ENERGY_PATH) and os.access(_RAPL_ENERGY_PATH, os.R_OK)

    def _read_energy_uj(self) -> int:
        with open(_RAPL_ENERGY_PATH, "r") as f:
            return int(f.read().strip())

    def collect(self, executable_path: str) -> dict:
        energy_before = self._read_energy_uj()
        start_time = time.perf_counter()

        process = subprocess.Popen(
            [executable_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout_out, stderr_out = process.communicate()

        end_time = time.perf_counter()
        energy_after = self._read_energy_uj()

        wall_time = end_time - start_time
        # energy_uj is in micro-joules; handle counter wraparound
        delta_uj = energy_after - energy_before
        if delta_uj < 0:
            # Counter wrapped around (typical max_energy_range_uj ~ 2^32)
            try:
                with open("/sys/class/powercap/intel-rapl:0/max_energy_range_uj", "r") as f:
                    max_range = int(f.read().strip())
                delta_uj += max_range
            except (FileNotFoundError, ValueError):
                delta_uj = abs(delta_uj)

        total_joules = delta_uj / 1_000_000.0

        return {
            "runtime_s": wall_time,
            "energy_j": total_joules,
            "stdout": stdout_out,
            "stderr": stderr_out,
            "exit_code": process.returncode
        }


# ---------------------------------------------------------------------------
# Priority 3 — perf stat --event=power/energy-pkg/ (Linux, broad support)
# ---------------------------------------------------------------------------
_PERF_ENERGY_RE = re.compile(r"([\d.]+)\s+Joules\s+power/energy-pkg/", re.IGNORECASE)


class PerfStatTelemetryCollector(BaseTelemetryCollector):
    name = "perf_stat"
    confidence_tier = "high"
    note = "Hardware energy via `perf stat -e power/energy-pkg/`."

    def is_available(self) -> bool:
        if shutil.which("perf") is None:
            return False
        # Probe whether the power/energy-pkg/ event is accessible
        try:
            result = subprocess.run(
                ["perf", "stat", "-e", "power/energy-pkg/", "--", "true"],
                capture_output=True, text=True, timeout=5
            )
            return "<not supported>" not in result.stderr and result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def collect(self, executable_path: str) -> dict:
        perf_cmd = [
            "perf", "stat", "-e", "power/energy-pkg/",
            "--", executable_path
        ]
        start_time = time.perf_counter()
        process = subprocess.run(
            perf_cmd,
            capture_output=True, text=True
        )
        end_time = time.perf_counter()
        wall_time = end_time - start_time

        # perf stat writes to stderr
        match = _PERF_ENERGY_RE.search(process.stderr)
        if match:
            total_joules = float(match.group(1))
        else:
            # Fallback: if perf didn't report energy, estimate from wall time
            total_joules = wall_time * ESTIMATED_TDP_WATTS * 0.5

        # perf wraps stdout — the binary's stdout is in process.stdout
        return {
            "runtime_s": wall_time,
            "energy_j": total_joules,
            "stdout": process.stdout,
            "stderr": "",  # perf's own stderr is consumed, not the binary's
            "exit_code": process.returncode
        }


# ---------------------------------------------------------------------------
# Collector registry & resolution
# ---------------------------------------------------------------------------
COLLECTORS = {
    "synthetic": SyntheticCpuTelemetryCollector,
    "amd_uprof": AmdUprofTelemetryCollector,
    "rapl": RaplTelemetryCollector,
    "perf_stat": PerfStatTelemetryCollector,
}

# Priority order for auto-detection (plan Layer 0)
_AUTO_PRIORITY = ("amd_uprof", "rapl", "perf_stat")


def resolve_collector(collector_name: str):
    requested = (collector_name or "auto").strip().lower()
    synthetic = SyntheticCpuTelemetryCollector()

    if requested == "auto":
        for name in _AUTO_PRIORITY:
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


def profile_binary(executable_path: str, collector_name: str = "auto") -> dict:
    collector, requested = resolve_collector(collector_name)
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
            "note": collector.note,
            "quality_label": collector.quality_label,
        },
        "measurement": {
            "energy_domain": None if is_est else "package",
            "unit": "joules-est" if is_est else "joules",
            "is_estimate": is_est
        }
    }
    return payload
