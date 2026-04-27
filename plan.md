# Petal — Real-World Product Plan

> **Framing**: A developer using Petal should never have to think about compilers, LLVM, or telemetry. They write code. Petal silently enforces energy budget. If they break it, a CI check fails — exactly like failing a lint check. That's the product.

---

## Who the user actually is

Before any architecture decision: who installs this?

**Primary user — the application developer**
- Writes C or C++ for a living (HPC, embedded, game engines, ML inference, robotics, data pipelines)
- Knows nothing about LLVM internals and does not want to
- Already has a build system (CMake, Bazel, Make) and a CI pipeline (GitHub Actions, GitLab CI, Jenkins)
- Will immediately uninstall anything that requires more than 10 minutes to set up
- Only cares about energy because their cloud bill, their hardware TDP budget, or their employer's sustainability mandate forces them to

**Secondary user — the platform/infra engineer**
- Manages CI pipelines and build toolchains for a team
- Cares about enforcement, not individual run results
- Wants a dashboard showing energy trends across the team's builds over time

**What they both need that the demo does not give them**:
1. A one-command install that works on their machine today
2. Drop-in integration with their existing build system — no rewriting `CMakeLists.txt` from scratch
3. Energy numbers they can trust (hardware-backed, not CPU-load math)
4. A CI check that fails builds on regression — automatic enforcement, no discipline required
5. Actionable output: not just "your code uses 18J", but "line 47, this loop — tile it like this"

---

## What to build, in order

### Layer 0 — The trust foundation (build this first, nothing else matters without it)

**Problem**: The current synthetic energy estimator (`CPU load × TDP × time`) produces numbers that vary by 40% run to run and are not comparable across machines. No developer will change their code based on a number they cannot trust.

**What to build**:

A `CollectorFactory` that auto-detects the best available telemetry source and reports which one it used:

```
Priority 1 — AMD uProf (bare-metal AMD, highest accuracy, Zen PMCs)
Priority 2 — Intel/AMD RAPL via pyRAPL (Linux, reads /sys/class/powercap)
Priority 3 — perf stat --event=power/energy-pkg/ (Linux, broader hardware support)
Priority 4 — Synthetic (CPU load × TDP, last resort, explicitly labelled "estimated")
```

Every energy reading in every output — CLI, report, CI — must show its source:

```
Energy saved: 7.3 J  [source: rapl, quality: hardware]
Energy saved: 7.3 J  [source: synthetic, quality: estimated ±35%]
```

If the quality is `estimated`, the CI gate must not fail the build — it can warn, but not block. Developers will not accept a build failure based on numbers with ±35% error bars.

**Why this must come first**: Every other feature is meaningless if the numbers are wrong. The VS Code extension showing "this loop costs 2.3 mJ" is actively harmful if that number is fabricated. Build the telemetry stack before you build the UI around it.

---

### Layer 1 — Installation that actually works

**What a developer does today to try Petal**:
1. `git clone` the repo
2. Read the README
3. `pip install -r requirements.txt`
4. Try to run `python backend/main.py data/matrix_mult.c --optimize=energy`
5. Either it works (demo input only) or it breaks on their own code

**What they should do**:
```bash
pip install petal-compiler
petal myfile.c
```

That's it. The binary is on their PATH. It finds GCC or Clang automatically. It falls back to synthetic telemetry on macOS. It produces output they can read.

**Package structure (`pyproject.toml`)**:
```toml
[project]
name = "petal-compiler"
version = "0.1.0"
requires-python = ">=3.10"

[project.scripts]
petal = "petal.cli:main"
petal-server = "petal.server:main"
```

**The CLI contract** — every flag must be intuitive to someone who has never read the docs:

```bash
# Analyse only, no transformation
petal myfile.c --analyse

# Optimise and show what changed
petal myfile.c --optimise --explain

# Optimise and write result to a new file
petal myfile.c --optimise --out myfile_green.c

# Use a specific policy
petal myfile.c --optimise --policy eco

# Show energy comparison between two binaries
petal compare baseline.c optimised.c

# Generate the HTML report
petal myfile.c --optimise --report energy_report.html
```

**The output must be human-readable first, machine-readable second**:
```
petal myfile.c --optimise

Analysing myfile.c...
  Found 1 hotspot: matrix_multiply() at line 14 (depth-3 loop nest)

Optimising...
  Applied: loop tiling (tile=64) at line 14–28
  Applied: scalar promotion (3 loop-invariant loads hoisted)

Compiling and benchmarking...
  Baseline:   18.4 J  [source: rapl]
  Optimised:  11.1 J  [source: rapl]
  Saved:       7.3 J  (39.7%)

Output written to: myfile_green.c
Report written to: energy_report.html
```

No JSON blobs in stdout. No SSE stream tokens. No `@@RUN_UPDATE@@` markers. Just text a developer can read.

---

### Layer 2 — Build system integration

A developer does not compile individual files with a custom command. They run `cmake --build` or `make` or `bazel build`. Petal must fit into that.

**CMake integration** (highest priority — most C/C++ projects use CMake):

```cmake
# In the user's CMakeLists.txt — this is all they add
find_package(Petal REQUIRED)
petal_target(my_library POLICY eco TDP 45)
```

What `petal_target()` does internally:
1. Adds `-fpass-plugin=<petal_pass.so>` to the target's compile flags
2. Hooks `add_custom_command(POST_BUILD ...)` to run telemetry on the compiled binary
3. Writes `petal_result.json` to the build directory

**The LLVM pass plugin** is what makes this work without wrapping the entire build:

```bash
# This is what cmake generates internally — the developer never types it
clang -O2 -fpass-plugin=/usr/lib/petal/PetalEnergyPass.so \
      -Rpass=petal myfile.c -o myfile
```

The `-Rpass=petal` flag makes LLVM emit energy remarks to stderr, which appear in the build output exactly like compiler warnings — no separate tool invocation required.

**Makefile integration** (for legacy projects):

```makefile
# User adds two lines to their Makefile
include $(shell petal --makefile-include)
CFLAGS += $(PETAL_CFLAGS)
```

**Bazel integration** (stretch goal — needed for Google, large infra teams):

A `petal_cc_binary` and `petal_cc_library` rule that wraps `cc_binary` / `cc_library` with the pass plugin and telemetry hooks.

---

### Layer 3 — The LLVM pass (replace the regex transformer)

The Python string rewriter must be replaced. It cannot handle:
- Loops that use variables other than `i`, `j`, `k`
- Loops with non-constant bounds
- C++ range-based for loops
- Any loop that has been partially unrolled by a prior pass
- Templates

**The real pass (`PetalEnergyPass.cpp`)** operates on LLVM IR after `-O2`, before codegen:

```
For each function in the module:
  Run LoopInfo to find all loop nests
  For each loop nest with depth >= 2:
    Run LoopAccessInfo to determine memory access patterns
    Compute estimated cache miss rate from stride analysis
    Query XGBoost model: predicted energy cost for this nest
    If predicted cost > threshold:
      Apply LoopTiling via LLVM's LoopInterchangePass infrastructure
      Emit OptimizationRemark with before/after energy estimate
      Record transformation in energy cost dictionary
```

**The Energy Remark** is the critical developer-facing output. It looks like this in the build log:

```
myfile.c:14:5: remark: petal: loop tiling applied
  — estimated energy reduction: 38% (18.4J → 11.4J)
  — cache miss rate reduced from 42% to 8%
  — tile size: 64 (L1 cache: 32KB)
  [-Rpass=petal]
```

This is a standard LLVM remark. IDEs and build tools that already parse compiler warnings will pick it up automatically. The VS Code C/C++ extension will show it as a code annotation with zero additional integration work.

**Building the pass**:
```cmake
add_library(PetalEnergyPass MODULE
    PetalEnergyPass.cpp
    EnergyRemarks.cpp
    TransformationEngine.cpp
)
target_link_libraries(PetalEnergyPass LLVM)
set_target_properties(PetalEnergyPass PROPERTIES
    PREFIX ""
    SUFFIX ".so"
)
```

The `.so` file is what gets distributed in the pip package and placed at `/usr/lib/petal/` on install.

---

### Layer 4 — The XGBoost model (training pipeline)

The model cannot be trained without real data. Here is the complete training pipeline:

**Step 1 — Build a microbenchmark corpus**

Write 100–200 small C kernels covering:
- Square matrix multiply (various sizes: 64, 128, 256, 512, 1024)
- Rectangular matrix multiply
- Sparse matrix operations (CSR, CSC formats)
- 1D, 2D, 3D stencil operations
- Convolutions (naive, im2col, Winograd)
- FFT inner loops
- Pointer-chasing traversals (linked list, tree)
- Gather/scatter access patterns
- Reduction operations (sum, min, max, dot product)
- Mixed access patterns (read-modify-write, in-place transforms)

These live in `benchmarks/corpus/` and cover the main patterns where energy optimisation is achievable.

**Step 2 — Feature extraction**

For each kernel, the instrumented LLVM pass extracts a feature vector per basic block:
```python
features = {
    "loop_depth": int,
    "trip_count_estimate": int,        # from LoopInfo
    "memory_footprint_bytes": int,     # working set size
    "access_stride": float,            # from LoopAccessInfo
    "fp_instruction_ratio": float,     # FP ops / total ops
    "load_store_ratio": float,
    "branch_density": float,
    "estimated_cache_misses": float,   # from CacheSim or TTI
    "vector_instruction_count": int,
    "indirect_access_count": int,      # pointer dereferences
}
```

**Step 3 — Label collection**

Run each kernel on bare-metal AMD hardware (EPYC or Ryzen) with `uProf` or RAPL:
```bash
# Isolated measurement for each kernel
uprof-cl -A power -d 5000 -o /tmp/petal_kernel_001 -- ./kernel_001
python scripts/parse_uprof.py /tmp/petal_kernel_001 >> benchmarks/labels.jsonl
```

**Step 4 — Train**

```python
import xgboost as xgb
import pandas as pd

df = pd.read_json("benchmarks/training_data.jsonl", lines=True)
X = df[FEATURE_COLUMNS]
y = df["energy_joules_per_million_iters"]

model = xgb.XGBRegressor(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    objective="reg:squarederror",
)
model.fit(X, y, eval_set=[(X_val, y_val)], early_stopping_rounds=20)
model.save_model("petal/ml/petal_model.ubj")
```

**Step 5 — ONNX export for NPU inference**

```python
from xgboost import XGBRegressor
import onnxmltools

onnx_model = onnxmltools.convert_xgboost(model, target_opset=12)
onnxmltools.utils.save_model(onnx_model, "petal/ml/petal_model.onnx")
```

On AMD Ryzen AI hardware, the ONNX model runs on the NPU via `onnxruntime` with `VitisAIExecutionProvider`, keeping the CPU free during compilation. On other hardware, it runs on CPU — still fast enough (XGBoost inference is microseconds per block).

**Model retraining cadence**: The model should be retrained whenever a new AMD architecture is targeted (Zen 4 vs Zen 5 have different cache topologies and power characteristics). The training pipeline should be automated and reproducible — `make train-model` produces a new `.ubj` artifact.

---

### Layer 5 — CI integration

This is the feature that makes Petal a team tool, not just a personal one.

**GitHub Actions**:

```yaml
# .github/workflows/petal.yml
name: Energy regression check

on: [push, pull_request]

jobs:
  energy-check:
    runs-on: ubuntu-latest          # synthetic telemetry on standard runners
    # runs-on: [self-hosted, amd]   # RAPL/uProf on bare-metal AMD runner

    steps:
      - uses: actions/checkout@v4

      - name: Install Petal
        run: pip install petal-compiler

      - name: Build and measure
        run: petal mylib/matrix.c --optimise --metadata-out petal_result.json

      - name: Energy regression gate
        run: |
          petal check-regression \
            --result petal_result.json \
            --baseline benchmarks/energy_baseline.json \
            --threshold 5                    # fail if energy regresses > 5%
            --telemetry-required hardware    # fail if telemetry is synthetic
```

**The `petal check-regression` command**:
- Loads the current run's result and the stored baseline
- If telemetry quality is `synthetic` and `--telemetry-required hardware` is set, it exits with a warning (not a failure) and posts a PR comment explaining that hardware telemetry is unavailable on this runner
- If the energy delta exceeds the threshold, it fails the build and posts a PR comment with the specific hotspot that regressed

**PR comment example**:
```
⚡ Petal energy regression detected

matmul/matrix.c · matrix_multiply() at line 47
  Before: 11.1 J  →  After: 16.8 J  (+51.4%)
  Threshold: 5%

Suggested fix: Loop access pattern changed from row-major to column-major.
Run `petal matmul/matrix.c --explain` for details.

Telemetry source: rapl (hardware)
```

**Storing the baseline**:
```bash
# Run once on the main branch, commit the result
petal mylib/matrix.c --optimise --metadata-out benchmarks/energy_baseline.json
git add benchmarks/energy_baseline.json
git commit -m "chore: establish Petal energy baseline"
```

The baseline file is committed to the repo. Future PRs are checked against it. This is the exact same pattern as snapshot tests — no novel concepts for the developer to learn.

---

### Layer 6 — VS Code extension

This is the highest-leverage DX feature because it surfaces energy information where the developer is looking: at their code, while writing it.

**Extension ID**: `petal.energy-linter`
**Activation**: Detects `petal-compiler` on `$PATH` at workspace open. If not found, shows a one-click install prompt.

**Features**:

1. **Energy remarks as diagnostics**
   - Reads the LLVM `-Rpass=petal` output from the last build
   - Shows an amber squiggle under high-energy loops
   - Hover tooltip: "This loop is estimated to cost 2.3 mJ/call. Petal can reduce it by ~40% via loop tiling."
   - Severity: `information` (not `warning` or `error` — developers will disable it if it's too noisy)

2. **CodeLens above expensive loops**
   - `⚡ 2.3 mJ · Optimise with Petal` — click to apply transformation in-place
   - `⚡ 11.1 J total · View energy report` — opens the HTML report in a side panel

3. **Energy budget status bar item**
   - Shows the current file's total estimated energy: `⚡ 11.1 J`
   - Click to open the energy report
   - Turns amber if any loop exceeds its per-function budget, red if the CI gate would fail

4. **No build-time overhead when extension is inactive**
   - The extension is completely passive — it reads artifacts that the build already produced
   - It does NOT run Petal on every save (that would be too slow)
   - It DOES offer a "Run Petal now" command in the command palette

---

### Layer 7 — The web dashboard (team view)

Individual runs are useful. Trends across a team and over time are valuable.

**This is not a priority for V1.** Build it only after the CLI, CI, and VS Code extension are solid.

When you do build it:

**What it shows**:
- Energy consumption per build over time (line chart per repo/branch)
- Which functions are responsible for the most energy across all builds
- Per-developer energy attribution (which PRs introduced regressions)
- Architecture comparison: same code on AMD EPYC vs Ryzen vs Intel Xeon

**How it gets its data**:
- The CI pipeline posts `petal_result.json` to the dashboard API after each build
- Authentication via GitHub OAuth (the same account that owns the repo)
- No separate sign-up — if you can push to the repo, you can see its energy dashboard

**What it does not do**:
- It does not run Petal itself — that happens in CI
- It does not store source code — only metadata and energy metrics
- It does not require any infrastructure changes from the user — one webhook URL in repo settings

---

## What to stop building

The following things in the current codebase are demo infrastructure, not product. They should be removed or replaced:

**Remove**:
- `@@RUN_UPDATE@@` magic string protocol — replace with structlog JSON events
- The SSE streaming server for the web demo — real users use the CLI, not a browser demo
- `regex` as the transformation engine — it must be replaced by the LLVM pass, full stop
- The synthetic energy estimator as the default — it must be the last resort, not the first

**Replace**:
- `server.py` Flask web demo → `petal-server` (serves only the HTML report artifact, does not run the pipeline)
- `analyzer.py` regex hotspot detection → `PetalEnergyPass.cpp` LoopInfo analysis
- `transformer.py` string rewriting → LLVM transformation infrastructure
- `telemetry.py` monolithic collector → `CollectorFactory` with the four-tier fallback chain

**Keep**:
- The policy system (`eco` / `balanced` / `perf`) — this is a good abstraction, keep it
- The `run_metadata.json` output format — extend it, don't replace it
- The HTML energy report — make it data-driven (reads `run_metadata.json`), not hardcoded
- The Flask server — keep it, but scope it to serving the report only

---

## The realistic build sequence

This is the order that produces something usable as fast as possible:

**Week 1–2**: CollectorFactory with RAPL support. This is the trust foundation. Nothing else is worth building until energy numbers are real.

**Week 2–3**: `petal-compiler` pip package with a working CLI. The Python transformer stays but is clearly marked `[legacy]`. The goal is `pip install petal-compiler && petal myfile.c` works on Linux with RAPL.

**Week 3–5**: CMake integration. `find_package(Petal)` and `petal_target()`. This is what opens the door to real projects — nobody is going to adopt a tool they have to invoke manually for every file.

**Week 4–6**: LLVM pass scaffold. Even a no-op pass that builds, loads, and emits a diagnostic proves the plugin architecture. Real transformations follow.

**Week 5–7**: Microbenchmark corpus and model training pipeline. 100 kernels. RAPL labels. Trained XGBoost model. This produces the first version of the energy cost dictionary that is based on real hardware data.

**Week 6–8**: CI integration. `petal check-regression` command. GitHub Actions workflow template. Baseline JSON format. PR comment posting.

**Week 8–10**: VS Code extension. Reads existing LLVM remark output — minimal new infrastructure needed if the LLVM pass is already emitting `-Rpass=petal` diagnostics.

**Week 10+**: Web dashboard, Bazel integration, additional language targets (Rust via LLVM IR, Fortran for HPC).

---

## What success looks like at each stage

**After Week 2**: A developer can `pip install petal-compiler`, run it on a real C file they own, and get an energy reading they have reason to believe (RAPL-backed, not synthetic). This is the minimum viable product. Everything else is a feature.

**After Week 5**: A developer can add four lines to their `CMakeLists.txt` and get energy remarks in their build output with no other changes to their workflow.

**After Week 8**: A team can add a Petal CI check to their GitHub Actions workflow, establish a baseline, and automatically catch energy regressions on PRs — exactly like they catch test failures or lint errors today.

**After Week 10**: A developer opening a C++ file in VS Code sees an amber squiggle on their expensive loop with a one-click fix. They click it, their code gets better, they move on. They didn't have to know what LLVM is.

That last state is the product. Everything before it is infrastructure.