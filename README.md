# Petal
Petal is a prototype energy-aware compilation demo for C matrix multiplication workloads. It includes:
- A Python backend pipeline that detects nested-loop hotspots, rewrites code with loop tiling, compiles with GCC, and estimates energy from runtime CPU load.
- A Flask server that streams pipeline logs via Server-Sent Events (SSE).
- A static frontend report/demo page.

## Current architecture
The backend flow is:
1. Read source C file.
2. Detect O(N³)-style nested loop patterns (`backend/core/analyzer.py`).
3. Apply policy gating (`eco|balanced|perf`) before transformation (`backend/core/policy.py`).
4. Apply source-to-source loop tiling via string rewriting (`backend/core/transformer.py`).
5. Compile with GCC and run telemetry sampling through collector adapters (`backend/core/telemetry.py`).
6. Emit run metadata JSON artifact and stream progress/events to frontend (`backend/server.py`).

## Repository structure
```text
.
├── backend/
│   ├── core/
│   │   ├── analyzer.py
│   │   ├── policy.py
│   │   ├── telemetry.py
│   │   └── transformer.py
│   ├── main.py
│   ├── petal_build.py
│   ├── server.py
│   ├── requirements.txt
│   ├── src/
│   │   ├── target_naive.c
│   │   └── target_petal.c
│   └── tests/
│       ├── test_pipeline_core.py
│       └── test_policy_telemetry.py
├── data/
│   ├── matrix_mult.c
│   ├── matrix_mult_optimized.c
│   └── test_workloads/
└── frontend/
    ├── assets/
    └── report/
        └── index.html
```

## Setup
Install dependencies:
```bash
python3 -m pip install -r backend/requirements.txt
```

Required tools:
- Python 3.x
- GCC

## CLI usage
Canonical CLI entrypoint:
```bash
python3 backend/main.py backend/src/target_naive.c --optimize=energy
```

Wrapper entrypoint (delegates to `main.py`):
```bash
python3 backend/petal_build.py backend/src/target_naive.c --optimize=energy
```

Optional flags:
- `--tdp=15W` (informational hardware budget messaging)
- `--output-bin=<path>` (override output binary location)
- `--policy=eco|balanced|perf` (controls transformation aggressiveness)
- `--collector=auto|synthetic|amd_uprof|rapl` (selects telemetry backend with fallback)
- `--metadata-file=<path>` (writes run metadata artifact JSON)

## Run the web demo
Start the backend server:
```bash
python3 backend/server.py
```

Then open:
- `http://127.0.0.1:5000/`

The `/compile` endpoint accepts source code, runs the backend pipeline, and streams:
- log lines (`data:` messages)
- `optimized_code` event (optimized source, if generated)
- `run_metadata` event (structured run details)
- `done` event

## Tests
Run backend unit tests:
```bash
python3 -m unittest discover -s backend/tests -p "test_*.py"
```

## Notes and limitations
- Energy numbers are currently estimated using CPU utilization and a fixed TDP constant, not direct hardware power counters.
- Collector adapters for AMD uProf/RAPL are scaffolded, with automatic fallback to synthetic CPU-load telemetry when unavailable.
- The transformation pass is heuristic and depends on recognizable loop structure.
- This is a prototype/demo codebase and not a production compiler plugin.
