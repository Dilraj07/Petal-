# Petal
**An Energy-Aware, Hardware-in-the-Loop Compiler Plugin for C/C++**

---

## Overview

Modern compilers optimize for execution speed or binary size, but they are entirely blind to the **physical energy consumption** of the silicon. As the industry scales toward massive AI data centers and edge IoT deployments, this "energy blind spot" results in massive, unnecessary power draw.

**Petal** bridges the gap between software engineers and hardware efficiency. It is an intelligent compilation pipeline that **profiles code using real-time AMD hardware telemetry**, **predicts energy costs via machine learning**, and **automatically transforms power-hungry LLVM Intermediate Representation (IR) into low-power equivalents**.

---

## The Architecture

Petal operates on a closed-loop **"Shift-Left" power optimization pipeline**, catching energy bloat at compile-time.

```mermaid
flowchart LR
    %% Styles
    classDef actorPanel fill:#f8fafc,stroke:#cbd5e1,stroke-width:2px,rx:10px,ry:10px;
    classDef systemPanel fill:#f0fdf4,stroke:#bbf7d0,stroke-width:2px,rx:10px,ry:10px;
    classDef nodeItem fill:none,stroke:none,font-weight:bold,color:#1e293b;
    classDef outputBox fill:#e2e8f0,stroke:#64748b,stroke-width:2px,color:#1e293b,font-weight:bold,rx:5px,ry:5px;

    subgraph Dev [Developer Environment]
        direction TB
        D1[1. Inputs Source Code]:::nodeItem
        D2[2. Configures Build Flags]:::nodeItem
        D3[3. Reviews Energy Remarks]:::nodeItem
        D4[4. Deploys Binary]:::nodeItem
    end

    subgraph Petal [Petal System]
        direction TB
        P_A[A. Injects IR Tracking Markers]:::nodeItem
        P_B[B. Collects AMD uProf Telemetry]:::nodeItem
        P_C[C. Predicts Energy via XGBoost]:::nodeItem
        P_D[D. Rewrites Inefficient Instructions]:::nodeItem
        
        P_A --> P_B
        P_B --> P_C
        P_C --> P_D
    end
    
    Final[Final Optimized Binary]:::outputBox

    D1 ===> P_A
    D2 ===> Petal
    P_D ===> D3
    P_D ==> Final
    Final ==> D4

    class Dev actorPanel
    class Petal systemPanel
```

---

## Key Features

- **Hardware-in-the-Loop Telemetry:** Uses physical silicon feedback via AMD uProf (and Linux RAPL) rather than theoretical heuristics to measure true electrical cost.

- **Predictive ML Engine:** An XGBoost model, accelerated locally on the AMD Ryzen AI NPU, maps power spikes to specific LLVM IR blocks to create an "Energy Cost Dictionary."

- **Custom LLVM Green Pass:** Automatically swaps inefficient instruction sequences (e.g., cache-thrashing loops) with mathematically equivalent, cache-friendly structures.

- **LLVM Energy Remarks:** Educates developers by flagging specific lines of C/C++ source code that draw disproportionate wattage.

- **Automated ESG Compliance:** Generates a visual HTML dashboard proving the exact Joules saved per execution, seamlessly integrating into modern CI/CD pipelines.

---

## Technology Stack

| Layer | Technologies |
|---|---|
| **Compiler Infrastructure** | LLVM 22+, Clang (C/C++), ClangIR |
| **Machine Learning** | Python, XGBoost |
| **Hardware Telemetry** | AMD uProf CLI, Linux `perf` |
| **Reporting** | HTML5, Tailwind CSS, Chart.js |

---

## Repository Structure

```
petal-hackathon/
│
├── petal_build.py          # Core Python CLI wrapper & ML simulation engine
├── README.md               # Project documentation
│
├── src/                    
│   ├── target_naive.c      # Standard, high-power C algorithm (Baseline)
│   └── target_petal.c      # Cache-friendly, low-power C algorithm (Target)
│
└── report/                 
    ├── index.html          # Dynamic Tailwind/Chart.js energy dashboard
    └── petal_out           # Final compiled executable
```

---

## Quick Start (Demo MVP)

This repository contains the **Minimum Viable Product (MVP)** designed to demonstrate the Petal pipeline and visualization dashboard.

### 1. Prerequisites

Ensure you have **Python 3.x** and **GCC** installed on your system.

### 2. Standard Compilation (Baseline)

To compile a file normally without energy optimizations, run:

```bash
python petal_build.py src/target_naive.c --optimize=speed
```

This will utilize the standard GCC pipeline and output an unoptimized binary.

### 3. Petal Energy Compilation

To invoke the Petal hardware-aware pipeline, use the `energy` flag:

```bash
python petal_build.py src/target_naive.c --optimize=energy
```

**What happens under the hood:**

1. The CLI initializes the LLVM frontend and generates IR.
2. It simulates a telemetry pass against AMD uProf metrics.
3. It queries the local ML model to identify inefficient loop nesting.
4. It applies the `PetalEnergyOptimizationPass` to lower the power footprint.
5. It generates a detailed HTML report.

### 4. View Results

Navigate to the `report/` directory and open `index.html` in any modern web browser to view the side-by-side analysis of **Execution Time (Seconds)** vs. **Energy Consumed (Joules)**.
