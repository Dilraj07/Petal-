import os
import re
import shutil
import subprocess
import time

import psutil
import structlog

logger = structlog.get_logger("telemetry")

try:
    import pyRAPL
    pyRAPL.setup()
    HAS_RAPL = True
except Exception:
    HAS_RAPL = False

try:
    from zeus_apple_silicon import AppleEnergyMonitor
    HAS_APPLE_IO = True
except Exception:
    HAS_APPLE_IO = False

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
        start_time = time.perf_counter()
        
        process = subprocess.run(
            ["AMDuProfCLI", "timechart", "--event", "power", "--", executable_path],
            capture_output=True, text=True
        )
        end_time = time.perf_counter()
        wall_time = end_time - start_time
        
        # Try to parse output for energy
        joules = None
        output = process.stdout + "\n" + process.stderr
        for line in output.splitlines():
            if "energy" in line.lower() or "joules" in line.lower():
                try:
                    nums = re.findall(r"[-+]?\d*\.\d+|\d+", line)
                    if nums:
                        joules = float(nums[-1])
                        break
                except ValueError:
                    continue
        
        if joules is not None:
            return {
                "runtime_s": wall_time,
                "energy_j": joules,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "exit_code": process.returncode
            }
        else:
            # Fallback to synthetic if parsing fails
            logger.warning("AMDuProfCLI output parsing failed. Falling back to synthetic estimation.")
            self.confidence_tier = "low"
            self.note = "Fallback to synthetic: AMDuProfCLI output could not be parsed."
            fallback_joules = wall_time * ESTIMATED_TDP_WATTS * 0.5  # 50% avg load guess
            return {
                "runtime_s": wall_time,
                "energy_j": fallback_joules,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "exit_code": process.returncode
            }


# ---------------------------------------------------------------------------
# Priority 2 — Intel/AMD RAPL via /sys/class/powercap (Linux only)
# ---------------------------------------------------------------------------
_RAPL_ENERGY_PATH = "/sys/class/powercap/intel-rapl:0/energy_uj"


class RaplTelemetryCollector(BaseTelemetryCollector):
    name = "rapl"
    confidence_tier = "high"
    note = "Package energy via /sys/class/powercap/intel-rapl:0/energy_uj"

    def is_available(self):
        return HAS_RAPL

    def collect(self, executable_path):
        start_time = time.perf_counter()
        
        process = subprocess.Popen(
            [executable_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        meter = pyRAPL.Measurement('rapl_meter')
        meter.begin()
        stdout_out, stderr_out = process.communicate()
        meter.end()
        
        end_time = time.perf_counter()
        wall_time = end_time - start_time
        
        try:
            # result.pkg is a list of microjoules (one per socket)
            pkg_energy_uj = sum(meter.result.pkg)
            energy_j = pkg_energy_uj / 1_000_000.0
        except (AttributeError, TypeError):
            energy_j = 0.0

        return {
            "runtime_s": wall_time,
            "energy_j": energy_j,
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
# Priority 2.1 — Apple Silicon IOReport (macOS)
# ---------------------------------------------------------------------------
class AppleIoTelemetryCollector(BaseTelemetryCollector):
    name = "apple_io"
    confidence_tier = "high"
    note = "Hardware energy via Apple Silicon IOReport."

    def is_available(self) -> bool:
        return HAS_APPLE_IO

    def collect(self, executable_path: str) -> dict:
        monitor = AppleEnergyMonitor()
        monitor.begin_window("run")
        
        start_time = time.perf_counter()
        process = subprocess.Popen(
            [executable_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout_out, stderr_out = process.communicate()
        end_time = time.perf_counter()
        
        m = monitor.end_window("run")
        wall_time = end_time - start_time
        
        # Depending on M-series chip, sum up available fields (cpu_joules, dram_joules, gpu_joules)
        total_joules = 0.0
        try:
            if hasattr(m, 'cpu_joules'): total_joules += getattr(m, 'cpu_joules')
            if hasattr(m, 'gpu_joules'): total_joules += getattr(m, 'gpu_joules')
            if hasattr(m, 'dram_joules'): total_joules += getattr(m, 'dram_joules')
        except Exception:
            pass

        return {
            "runtime_s": wall_time,
            "energy_j": total_joules,
            "stdout": stdout_out,
            "stderr": stderr_out,
            "exit_code": process.returncode
        }


# ---------------------------------------------------------------------------
# Priority 2.2 — Intel PCM (Cross-platform)
# ---------------------------------------------------------------------------
class IntelPcmTelemetryCollector(BaseTelemetryCollector):
    name = "intel_pcm"
    confidence_tier = "high"
    note = "Hardware energy via Intel PCM (pcm-power)."

    def _get_pcm_exe(self) -> str | None:
        for exe in ("pcm-power", "pcm-power.exe", "pcm-power.x"):
            if shutil.which(exe):
                return exe
        return None

    def is_available(self) -> bool:
        return self._get_pcm_exe() is not None

    def collect(self, executable_path: str) -> dict:
        pcm_exe = self._get_pcm_exe()
        
        # Start pcm-power in background
        pcm = subprocess.Popen(
            [pcm_exe, "-i", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        start_time = time.perf_counter()
        process = subprocess.run(
            [executable_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        end_time = time.perf_counter()
        wall_time = end_time - start_time

        # Give pcm-power a moment to flush final samples, then terminate
        time.sleep(1.0)
        pcm.terminate()
        out, _ = pcm.communicate()

        joules = 0.0
        for line in (out or "").splitlines():
            if "Processor" in line and "Joules" in line:
                parts = line.split()
                try:
                    joules = float(parts[-1])
                except ValueError:
                    pass

        return {
            "runtime_s": wall_time,
            "energy_j": joules,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "exit_code": process.returncode
        }


# ---------------------------------------------------------------------------
# Collector registry & resolution
# ---------------------------------------------------------------------------
COLLECTORS = {
    "synthetic": SyntheticCpuTelemetryCollector,
    "amd_uprof": AmdUprofTelemetryCollector,
    "apple_io": AppleIoTelemetryCollector,
    "intel_pcm": IntelPcmTelemetryCollector,
    "rapl": RaplTelemetryCollector,
    "perf_stat": PerfStatTelemetryCollector,
}

# Priority order for auto-detection (plan Layer 0)
_AUTO_PRIORITY = ("apple_io", "intel_pcm", "amd_uprof", "rapl", "perf_stat")


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
    logger.info("Profiling execution", collector=collector.name, requested=requested)
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
