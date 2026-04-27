import shutil
import subprocess
import time
from dataclasses import asdict, dataclass

import psutil

# Assume a standard laptop CPU has a max TDP (Thermal Design Power) of 45 Watts
ESTIMATED_TDP_WATTS = 45.0


@dataclass
class TelemetryMetrics:
    collector: str
    confidence_tier: str
    execution_time_s: float
    avg_cpu_load_pct: float
    avg_power_w: float
    energy_j: float
    sample_count: int


class BaseTelemetryCollector:
    name = "base"
    confidence_tier = "unknown"

    def is_available(self):
        return True

    def collect(self, executable_path):
        raise NotImplementedError


class SyntheticCpuTelemetryCollector(BaseTelemetryCollector):
    name = "synthetic_cpu_load"
    confidence_tier = "low"

    def collect(self, executable_path):
        start_time = time.perf_counter()
        process = subprocess.Popen([executable_path])
        cpu_percentages = []

        while process.poll() is None:
            cpu_percentages.append(psutil.cpu_percent(interval=0.1))

        end_time = time.perf_counter()
        execution_time = end_time - start_time
        avg_cpu_load = sum(cpu_percentages) / len(cpu_percentages) if cpu_percentages else 100.0
        estimated_power = (avg_cpu_load / 100.0) * ESTIMATED_TDP_WATTS
        total_joules = execution_time * estimated_power
        return TelemetryMetrics(
            collector=self.name,
            confidence_tier=self.confidence_tier,
            execution_time_s=execution_time,
            avg_cpu_load_pct=avg_cpu_load,
            avg_power_w=estimated_power,
            energy_j=total_joules,
            sample_count=len(cpu_percentages),
        )


class AmdUprofTelemetryCollector(BaseTelemetryCollector):
    name = "amd_uprof"
    confidence_tier = "high"

    def is_available(self):
        return shutil.which("AMDuProfCLI") is not None

    def collect(self, executable_path):
        raise NotImplementedError("AMD uProf collector adapter is not implemented yet.")


class RaplTelemetryCollector(BaseTelemetryCollector):
    name = "rapl"
    confidence_tier = "medium"

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
    print(f"[\033[95mTelemetry\033[0m] Profiling execution via collector '{collector.name}' (requested: '{requested}')...")
    metrics = collector.collect(executable_path)
    payload = asdict(metrics)
    payload["requested_collector"] = requested
    payload["fallback_used"] = collector.name == "synthetic_cpu_load" and requested not in ("synthetic", "auto")
    return payload
