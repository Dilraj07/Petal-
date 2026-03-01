import time
import psutil
import subprocess

# Assume a standard laptop CPU has a max TDP (Thermal Design Power) of 45 Watts
ESTIMATED_TDP_WATTS = 45.0 

def profile_binary(executable_path):
    print(f"[\033[95mTelemetry\033[0m] Profiling physical execution of {executable_path}...")
    
    start_time = time.perf_counter()
    
    # Run the binary and monitor CPU usage
    process = subprocess.Popen([executable_path])
    cpu_percentages = []
    
    while process.poll() is None:
        cpu_percentages.append(psutil.cpu_percent(interval=0.1))
        
    end_time = time.perf_counter()
    
    execution_time = end_time - start_time
    avg_cpu_load = sum(cpu_percentages) / len(cpu_percentages) if cpu_percentages else 100.0
    
    # Formula: Joules = Time (s) * Power (Watts)
    # Power = (CPU Load %) * Max TDP
    estimated_power = (avg_cpu_load / 100.0) * ESTIMATED_TDP_WATTS
    total_joules = execution_time * estimated_power
    
    return execution_time, total_joules
