"""Static HTML Dashboard generation for Petal CI results."""

import glob
import json
import os
import sys

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Petal Energy Dashboard</title>
    <!-- Chart.js for dynamic visualization -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #1a1a1f;
            --panel-bg: rgba(26, 26, 31, 0.6);
            --border-color: rgba(255, 255, 255, 0.06);
            --text-primary: #d4d4d8;
            --text-heading: #e4e4e7;
            --text-secondary: #71717a;
            --accent-green: #4ade80;
            --accent-red: #f87171;
            --accent-blue: #3b82f6;
        }

        body {
            font-family: 'Circular Std', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-color);
            color: var(--text-primary);
            margin: 0;
            padding: 2rem;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }

        body::before {
            content: '';
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            background-image:
                linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
            background-size: 80px 80px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        h1 {
            margin: 0;
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-heading);
            letter-spacing: -0.02em;
        }

        .glass-panel {
            background: var(--panel-bg);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .glass-panel:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
            border-color: rgba(255, 255, 255, 0.15);
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
        }

        .stat-card {
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
            margin: 0.5rem 0;
            color: var(--text-heading);
        }

        .stat-label {
            color: var(--text-secondary);
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
        }

        .chart-container {
            position: relative;
            height: 350px;
            width: 100%;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }

        th, td {
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }

        th {
            color: var(--text-secondary);
            font-weight: 600;
            font-size: 0.875rem;
            text-transform: uppercase;
        }

        tr:last-child td {
            border-bottom: none;
        }

        .badge {
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .badge-green { background: rgba(74, 222, 128, 0.1); color: var(--accent-green); border-color: rgba(74, 222, 128, 0.2); }
        .badge-red { background: rgba(248, 113, 113, 0.1); color: var(--accent-red); border-color: rgba(248, 113, 113, 0.2); }
        .badge-blue { background: rgba(59, 130, 246, 0.1); color: var(--accent-blue); border-color: rgba(59, 130, 246, 0.2); }
        
        .pulse {
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: .5; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Petal Energy Intelligence</h1>
            <div style="color: var(--text-secondary); font-size: 0.875rem;">
                Last Updated: <span id="last-updated"></span>
            </div>
        </header>

        <div class="dashboard-grid">
            <div class="glass-panel stat-card">
                <div class="stat-label">Total Runs Analyzed</div>
                <div class="stat-value" id="total-runs">0</div>
            </div>
            <div class="glass-panel stat-card">
                <div class="stat-label">Average Energy Savings</div>
                <div class="stat-value" style="color: var(--accent-green);" id="avg-savings">0%</div>
            </div>
            <div class="glass-panel stat-card">
                <div class="stat-label">System Status</div>
                <div class="stat-value" style="font-size: 1.5rem; display: flex; align-items: center; gap: 0.5rem;">
                    <div style="width: 12px; height: 12px; border-radius: 50%; background-color: var(--accent-green);" class="pulse"></div>
                    Active Enforcing
                </div>
            </div>
        </div>

        <div class="glass-panel">
            <h2 style="margin-top: 0; font-size: 1.25rem;">Energy Consumption Trend</h2>
            <div class="chart-container">
                <canvas id="trendChart"></canvas>
            </div>
        </div>

        <div class="glass-panel">
            <h2 style="margin-top: 0; font-size: 1.25rem; margin-bottom: 1rem;">Recent CI Profiling Runs</h2>
            <div style="overflow-x: auto;">
                <table id="runs-table">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Target File</th>
                            <th>Baseline (J)</th>
                            <th>Optimized (J)</th>
                            <th>Delta</th>
                            <th>Telemetry</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Populated by JS -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Data Injection Point -->
    <script>
        const PETAL_DATA = /*DATA_PLACEHOLDER*/[];

        // Utility formatting
        const fmtJ = (val) => val.toFixed(2);
        const fmtPct = (val) => (val > 0 ? '+' : '') + val.toFixed(1) + '%';
        
        document.getElementById('last-updated').textContent = new Date().toLocaleString();
        document.getElementById('total-runs').textContent = PETAL_DATA.length;

        // Populate Table and Calculate Stats
        const tbody = document.querySelector('#runs-table tbody');
        let totalPct = 0;
        let validPctCount = 0;
        
        // Sort data chronologically
        const sortedData = [...PETAL_DATA].sort((a, b) => new Date(a.timestamp_utc) - new Date(b.timestamp_utc));

        [...sortedData].reverse().slice(0, 50).forEach(run => {
            const tr = document.createElement('tr');
            
            // Safe extraction
            const ts = new Date(run.timestamp_utc).toLocaleString();
            const file = run.source_file ? run.source_file.split('/').pop().split('\\').pop() : 'unknown';
            
            const baseJ = run.baseline?.energy_j || 0;
            const optJ = run.optimised?.energy_j || baseJ;
            const deltaPct = run.comparison?.energy_delta_pct || 0;
            const collector = run.collector?.used || 'unknown';
            
            if (deltaPct < 0) {
                totalPct += deltaPct;
                validPctCount++;
            }

            let deltaHtml = `<span class="badge ${deltaPct > 0 ? 'badge-red' : deltaPct < 0 ? 'badge-green' : 'badge-blue'}">${fmtPct(deltaPct)}</span>`;

            tr.innerHTML = `
                <td style="color: var(--text-secondary);">${ts}</td>
                <td style="font-family: monospace;">${file}</td>
                <td>${fmtJ(baseJ)}</td>
                <td>${fmtJ(optJ)}</td>
                <td>${deltaHtml}</td>
                <td><span class="badge badge-blue">${collector}</span></td>
            `;
            tbody.appendChild(tr);
        });

        if (validPctCount > 0) {
            document.getElementById('avg-savings').textContent = (totalPct / validPctCount).toFixed(1) + '%';
        }

        // Render Chart
        const ctx = document.getElementById('trendChart').getContext('2d');
        
        // Group by file if there's diverse data, or just show timeline
        const labels = sortedData.map(d => new Date(d.timestamp_utc).toLocaleDateString() + ' ' + new Date(d.timestamp_utc).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
        const baseData = sortedData.map(d => d.baseline?.energy_j || 0);
        const optData = sortedData.map(d => d.optimised?.energy_j || (d.baseline?.energy_j || 0));

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Baseline Energy (J)',
                        data: baseData,
                        borderColor: '#94a3b8',
                        backgroundColor: 'rgba(148, 163, 184, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true
                    },
                    {
                        label: 'Optimized Energy (J)',
                        data: optData,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: '#f8fafc' }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(30, 41, 59, 0.9)',
                        titleColor: '#f8fafc',
                        bodyColor: '#f8fafc',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8' },
                        title: { display: true, text: 'Joules (J)', color: '#94a3b8' }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: '#94a3b8', maxTicksLimit: 10 }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        });
    </script>
</body>
</html>
"""

def generate_dashboard(results_dir: str, out_file: str) -> int:
    """Read petal_result*.json files and generate a standalone HTML dashboard."""
    if not os.path.isdir(results_dir):
        print(f"Error: Results directory not found: {results_dir}", file=sys.stderr)
        return 1

    json_files = glob.glob(os.path.join(results_dir, "*.json"))
    
    data_list = []
    for jf in json_files:
        try:
            with open(jf, "r") as f:
                data = json.load(f)
                # Only include valid Petal runs
                if data.get("tool") == "petal":
                    data_list.append(data)
        except Exception as e:
            print(f"Warning: Failed to parse {jf}: {e}", file=sys.stderr)

    if not data_list:
        print(f"Warning: No valid Petal JSON results found in {results_dir}.")
        print("Run `petal <file> --optimise --metadata-out <path>` to generate data.")
    
    # Inject JSON array directly into the script block
    js_data = json.dumps(data_list)
    html_content = _HTML_TEMPLATE.replace("/*DATA_PLACEHOLDER*/[]", js_data)

    out_dir = os.path.dirname(os.path.abspath(out_file))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✓ Dashboard successfully generated at: {os.path.abspath(out_file)}")
    print(f"  Processed {len(data_list)} telemetry reports.")
    return 0
