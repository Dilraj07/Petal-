# Petal
Petal is a prototype energy-aware compilation demo for C matrix multiplication workloads. It includes:
- A Python backend pipeline that detects nested-loop hotspots, rewrites code with loop tiling, compiles with GCC, and estimates energy from runtime CPU load.
- A Flask server that streams pipeline logs via Server-Sent Events (SSE).
- A static frontend report/demo page.

## Current architecture
The backend flow is:
1. Read source C file.
2. Detect O(N³)-style nested loop patterns (`backend/core/analyzer.py`).
3. Apply source-to-source loop tiling via string rewriting (`backend/core/transformer.py`).
4. Compile with GCC and run telemetry sampling (`backend/core/telemetry.py`).
5. Stream progress to frontend (`backend/server.py`).

## Repository structure
```text
.
├── backend/
│   ├── core/
│   │   ├── analyzer.py
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
│       └── test_pipeline_core.py
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

## Run the web demo
Start the backend server:
```bash
python3 backend/server.py
```

Then open:
- `http://127.0.0.1:5000/`

The `/compile` endpoint accepts source code, runs the backend pipeline, and streams logs/events to the frontend.

## Tests
Run backend unit tests:
```bash
python3 -m unittest discover -s backend/tests -p "test_*.py"
```

## Notes and limitations
- Energy numbers are currently estimated using CPU utilization and a fixed TDP constant, not direct hardware power counters.
- The transformation pass is heuristic and depends on recognizable loop structure.
- This is a prototype/demo codebase and not a production compiler plugin.
