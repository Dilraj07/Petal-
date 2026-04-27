# Petal: Energy-Aware Compilation Pipeline

Petal is a prototype energy-efficient compilation framework designed for C workloads. It focuses on the intersection of static analysis, source-to-source optimization, and physical energy telemetry to minimize the carbon footprint of computationally intensive operations like matrix multiplication.

---

## 1. Project Objective
The primary goal of Petal is to demonstrate how compilers can be made "energy-aware." Instead of optimizing solely for execution speed, Petal optimizes for **energy efficiency** by improving data locality and reducing CPU memory stalls, which are major drivers of power consumption in modern processors.

---

## 2. Core Architecture & Pipeline

The system follows a sequential pipeline from raw source code to a telemetry-backed energy report:

### A. Static Hotspot Analysis (`analyzer.py`)
- **Mechanism**: Scans the source code using regex-based pattern matching (simulating an AST walk).
- **Target**: Detects `O(N³)` nested loop patterns (3+ levels of nesting).
- **Rationale**: Triple-nested loops in matrix operations often result in high cache-miss rates when the stride length exceeds the L1/L2 cache capacity.

### B. Policy-Driven Gating (`policy.py`)
- **Profiles**: `eco`, `balanced`, `perf`.
- **Function**: Determines whether the optimization should proceed based on the user's hardware budget (`--tdp`) and desired efficiency level.
- **Logic**: For example, the `eco` policy might favor optimizations that significantly reduce power even if they don't provide the absolute maximum speedup.

### C. Source-to-Source Transformation (`transformer.py`)
- **Optimization**: **Loop Tiling** (Loop Blocking).
- **Method**: 
    1. Injects a `blockSize` constant (default: 64).
    2. Transforms the standard 3-level `i, j, k` loop nest into a 6-level tiled structure.
- **Benefit**: By processing smaller blocks of data that fit entirely in the CPU cache, it dramatically reduces DRAM access frequency, which is significantly more energy-expensive than cache access.

### D. Telemetry & Energy Estimation (`telemetry.py`)
- **Compilation**: Invokes `gcc` to generate both a naive and an optimized binary.
- **Execution**: Runs the binaries while sampling system metrics.
- **Data Collection**:
    - **Synthetic (Default)**: Estimates energy using `(CPU Load % * TDP * Execution Time)`.
    - **AMD uProf**: Interface for AMD power counters.
    - **Intel RAPL**: Interface for Intel Runtime Average Power Limiting.
- **Comparison**: Generates a delta between the baseline and the "Petal-Optimized" run.

### E. Web Demo & Streaming (`server.py`)
- **Backend**: Flask-based REST API.
- **Streaming**: Uses Server-Sent Events (SSE) to provide live terminal-style feedback to the user.
- **Output**: Returns the optimized source code and structured JSON metadata for visualization.

---

## 3. Technology Stack

| Layer | Tool / Technology |
| :--- | :--- |
| **Core Language** | Python 3.x |
| **Optimization Target** | C (ISO C99+) |
| **Web Framework** | Flask |
| **Middleware** | Flask-Cors (Cross-Origin Resource Sharing) |
| **System Utilities** | `psutil` (Sampling CPU load & process management) |
| **Compiler Interface** | GCC (System-level binary) |
| **Hardware Telemetry** | RAPL (Intel), uProf (AMD) |
| **CLI Argument Parsing** | `argparse` |

---

## 4. Current Limitations & Assumptions
- **Regex Dependency**: The transformation engine currently relies on canonical loop structures (using variables `i`, `j`, `k` and constant `N`).
- **Estimation Accuracy**: In the absence of hardware counters (RAPL/uProf), energy figures are derived from CPU utilization models, which are approximations.
- **Target Workload**: Optimized specifically for square matrix multiplication patterns.

---

## 5. Getting Started

### Installation
```bash
# Clone the repository
git clone https://github.com/Dilraj07/Petal-.git
cd Petal-

# Install Python requirements
pip install -r backend/requirements.txt
```

### Running the CLI
```bash
python backend/main.py data/matrix_mult.c --policy=eco
```

### Launching the Web UI
```bash
python backend/server.py
# Navigate to http://127.0.0.1:5000 in your browser
```
