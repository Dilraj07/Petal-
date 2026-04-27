# Petal — Real-World Product Plan (v2)

> **Framing**: A developer using Petal should never have to think about compilers, LLVM, or telemetry. They write code. Petal silently enforces an energy budget. If they break it, a CI check fails — exactly like failing a lint check. That's the product.

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
- Cares about enforcement, privacy, and security
- Wants a dashboard showing energy trends across the team's builds over time, but **will block** any tool that sends proprietary source code or performance profiles to a third-party SaaS.

---

## What to build, in order

### Layer 0 — The trust foundation (Telemetry)

**Problem**: Synthetic energy estimators produce numbers that developers cannot trust. Real hardware telemetry (RAPL, PMCs) requires elevated privileges (`sudo` or `CAP_SYS_RAWIO`), which breaks the "10-minute install" rule.

**What to build**:
A `CollectorFactory` that auto-detects the best available telemetry source:
1. AMD uProf
2. Intel/AMD RAPL
3. `perf stat --event=power/energy-pkg/`
4. Synthetic (TDP fallback)

**Handling Permissions**:
Petal provides a `petal setup-env` command. This runs once (requesting `sudo`) to configure `setcap` on `perf` or add the user to a `power` group. If the user refuses or is on a restricted system, Petal falls back to Synthetic mode but displays a highly visible `[Estimated ±35%]` badge. Every energy reading must explicitly state its source and quality.

---

### Layer 1 — Installation and the CLI

**What they should do**:
```bash
pip install petal-compiler
petal myfile.c --optimise --explain
```

**Transparent Compilation (No Source-to-Source)**:
The legacy demo generated a `_green.c` file. This is **deprecated** for the product. Developers do not want to maintain a separate "green" version of their codebase. Petal acts as a **transparent compiler plugin** (like an `-O3` flag). It outputs an optimized binary and rich diagnostics, not rewritten C code.

---

### Layer 2 — Build system integration

A developer does not compile individual files manually. Petal must fit seamlessly into CMake.

**Separating Compilation from Execution**:
Because CMake targets are often un-executable libraries, we split the workflow:

1. **Optimization (Compile-Time)**:
```cmake
find_package(Petal REQUIRED)
petal_target(my_library POLICY eco) # Injects -fpass-plugin=<petal_pass.so>
```
2. **Telemetry (Test-Time)**:
```cmake
petal_benchmark(TARGET my_executable COMMAND my_executable --run-workload data.bin)
```
This treats energy profiling like running a unit test via `CTest`, giving the developer full control over the execution context.

---

### Layer 3 — The LLVM pass

The Python string rewriter is replaced by a native C++ LLVM Pass (`PetalEnergyPass.so`) operating on LLVM IR before codegen.

**The Energy Remark**:
Because we no longer generate `_green.c`, the critical developer-facing output is the LLVM OptimizationRemark emitted to the build log:
```
myfile.c:14:5: remark: petal: loop tiling applied
  — estimated energy reduction: 38% (18.4J → 11.4J)
  [-Rpass=petal]
```

---

### Layer 4 — Dependency-Free ML (The XGBoost Model)

To predict energy costs within the LLVM pass, we need ML inference. Bundling a heavy framework like `onnxruntime` into a compiler plugin is a cross-platform packaging nightmare.

**The Solution**:
During the model training pipeline, the XGBoost decision trees are compiled directly into static, raw C++ code using tools like `m2cgen` or `treelite`. This generated C++ code is compiled directly into `PetalEnergyPass.so`.
- **Result**: Zero external dependencies. Nanosecond inference. Trivial pip distribution.

---

### Layer 5 — CI integration (Handling Hardware Mismatch)

The feature that makes Petal a team tool is the GitHub Actions CI gate: `petal check-regression`.

**The Hardware Mismatch Problem**:
Energy baselines are hardware-specific. A baseline generated on a developer's AMD Ryzen laptop cannot be compared to a GitHub Actions Azure VM (Intel Xeon) without triggering false positives.

**The Solution**:
`run_metadata.json` embeds a hardware fingerprint (e.g., `lscpu` model). When the CI gate runs, it checks if the current runner matches the baseline's fingerprint.
- If match: Compare directly against the stored baseline.
- If mismatch: Petal automatically checks out the `main` branch, compiles and measures it on the current CI runner, and uses that as a dynamic baseline to compare against the PR branch.

---

### Layer 6 — VS Code extension

**Read-Only Energy Profiler & Linter**:
The extension will **not** offer a "Quick Fix" to rewrite source code (aligning with the transparent compilation decision in Layer 1).
It reads the LLVM `-Rpass=petal` output and surfaces CodeLens/hover diagnostics above loops:
`⚡ 2.3 mJ · Petal tiled this loop during compilation (saved 40%)`

This keeps the extension lightweight and builds trust by explaining what the compiler did under the hood.

---

### Layer 7 — The web dashboard (Local-First Privacy)

A centralized SaaS dashboard processing proprietary source code and function-level profiling data will be blocked by enterprise security teams.

**The Solution**:
There is no SaaS backend. The dashboard is a **Static HTML Generator** built into the CLI.
```bash
petal generate-dashboard --results-dir ./ci-results/
```
This aggregates historical JSON files and outputs a rich, standalone HTML dashboard. Teams publish this to their own GitHub Pages or attach it as a GitHub Actions Summary. 100% data privacy is guaranteed because the data never leaves the customer's infrastructure.