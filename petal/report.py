"""HTML report generation for Petal optimization results."""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


def generate_html_report(
    filename: str,
    policy: str,
    baseline_energy: float,
    optimized_energy: float,
    baseline_runtime: float,
    optimized_runtime: float,
    baseline_power: float,
    confidence: float,
    transformation: str,
    output_path: str = None,
) -> str:
    """Generate an HTML report for optimization results.
    
    Args:
        filename: Original C source file name
        policy: Optimization policy used (eco, balanced, perf)
        baseline_energy: Baseline energy consumption (J)
        optimized_energy: Optimized energy consumption (J)
        baseline_runtime: Baseline runtime (s)
        optimized_runtime: Optimized runtime (s)
        baseline_power: Average power consumption (W)
        confidence: Detection confidence (0-100)
        transformation: Transformation applied (e.g., "Loop Tiling (64)")
        output_path: Where to save HTML file (default: frontend/report/)
    
    Returns:
        Path to generated HTML file
    """
    if output_path is None:
        output_path = "frontend/report"
    
    Path(output_path).mkdir(parents=True, exist_ok=True)
    
    # Calculate metrics
    energy_saved = baseline_energy - optimized_energy
    energy_savings_pct = (energy_saved / baseline_energy * 100) if baseline_energy > 0 else 0
    time_saved = baseline_runtime - optimized_runtime
    time_savings_pct = (time_saved / baseline_runtime * 100) if baseline_runtime > 0 else 0
    
    # Policy colors
    policy_colors = {
        "eco": "#10B981",
        "balanced": "#3B82F6",
        "perf": "#F59E0B",
    }
    policy_color = policy_colors.get(policy.lower(), "#6366F1")
    
    # HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Petal Optimization Report - {filename}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }}
        
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, {policy_color} 0%, {policy_color}dd 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 1.1em;
            opacity: 0.95;
        }}
        
        .timestamp {{
            font-size: 0.9em;
            opacity: 0.8;
            margin-top: 10px;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .file-info {{
            background: #F3F4F6;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}
        
        .file-info h3 {{
            color: #374151;
            margin-bottom: 10px;
        }}
        
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }}
        
        .info-item {{
            background: white;
            padding: 15px;
            border-left: 4px solid {policy_color};
            border-radius: 4px;
        }}
        
        .info-item label {{
            display: block;
            font-size: 0.85em;
            color: #6B7280;
            margin-bottom: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .info-item value {{
            display: block;
            font-size: 1.3em;
            font-weight: 600;
            color: #111827;
        }}
        
        .metrics {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }}
        
        .metric-card {{
            background: #F9FAFB;
            padding: 25px;
            border-radius: 12px;
            border: 2px solid #E5E7EB;
        }}
        
        .metric-card h3 {{
            color: #374151;
            font-size: 1em;
            margin-bottom: 20px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .metric-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #D1D5DB;
        }}
        
        .metric-row:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}
        
        .metric-label {{
            color: #6B7280;
            font-size: 0.9em;
        }}
        
        .metric-value {{
            font-weight: 600;
            color: #111827;
            font-size: 1.1em;
        }}
        
        .metric-savings {{
            background: linear-gradient(135deg, {policy_color} 0%, {policy_color}dd 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            margin-top: 20px;
        }}
        
        .savings-value {{
            font-size: 2.2em;
            font-weight: 700;
            margin-bottom: 5px;
        }}
        
        .savings-label {{
            font-size: 0.9em;
            opacity: 0.95;
        }}
        
        .confidence-bar {{
            background: #E5E7EB;
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 10px;
        }}
        
        .confidence-fill {{
            background: linear-gradient(90deg, {policy_color} 0%, {policy_color} 100%);
            height: 100%;
            width: {confidence}%;
            transition: width 0.3s ease;
        }}
        
        .chart-container {{
            background: #F9FAFB;
            padding: 25px;
            border-radius: 12px;
            margin-bottom: 30px;
            border: 2px solid #E5E7EB;
        }}
        
        .chart-title {{
            color: #374151;
            font-weight: 600;
            margin-bottom: 20px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .bar-chart {{
            display: flex;
            align-items: flex-end;
            justify-content: center;
            gap: 40px;
            height: 250px;
            margin-bottom: 20px;
        }}
        
        .bar-group {{
            text-align: center;
            flex: 1;
        }}
        
        .bar {{
            height: {min(200, max(10, baseline_energy / 2))}px;
            background: linear-gradient(180deg, #EF4444 0%, #DC2626 100%);
            border-radius: 8px 8px 0 0;
            margin-bottom: 10px;
            min-width: 60px;
        }}
        
        .bar.optimized {{
            height: {min(200, max(10, optimized_energy / 2))}px;
            background: linear-gradient(180deg, {policy_color} 0%, {policy_color} 100%);
        }}
        
        .bar-label {{
            font-size: 0.9em;
            color: #6B7280;
            margin-top: 5px;
        }}
        
        .bar-value {{
            font-weight: 600;
            color: #111827;
            margin-top: 5px;
        }}
        
        .footer {{
            background: #F3F4F6;
            padding: 20px 40px;
            text-align: center;
            color: #6B7280;
            font-size: 0.9em;
            border-top: 1px solid #E5E7EB;
        }}
        
        @media (max-width: 768px) {{
            .metrics {{
                grid-template-columns: 1fr;
            }}
            
            .bar-chart {{
                flex-direction: column;
                height: auto;
            }}
            
            .header h1 {{
                font-size: 1.8em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Petal Energy Optimization Report</h1>
            <p>{filename}</p>
            <div class="timestamp">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        
        <div class="content">
            <div class="file-info">
                <h3>Optimization Details</h3>
                <div class="info-grid">
                    <div class="info-item">
                        <label>Policy</label>
                        <value>{policy.upper()}</value>
                    </div>
                    <div class="info-item">
                        <label>Transformation</label>
                        <value>{transformation}</value>
                    </div>
                    <div class="info-item">
                        <label>Confidence</label>
                        <value>{confidence:.0f}%</value>
                    </div>
                    <div class="info-item">
                        <label>Status</label>
                        <value style="color: #10B981;">✓ APPLIED</value>
                    </div>
                </div>
            </div>
            
            <div class="metrics">
                <div class="metric-card">
                    <h3>Energy Consumption</h3>
                    <div class="metric-row">
                        <span class="metric-label">Baseline</span>
                        <span class="metric-value">{baseline_energy:.2f} J</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Optimized</span>
                        <span class="metric-value">{optimized_energy:.2f} J</span>
                    </div>
                    <div class="metric-savings">
                        <div class="savings-value">↓ {energy_savings_pct:.0f}%</div>
                        <div class="savings-label">{energy_saved:.2f} J saved</div>
                    </div>
                </div>
                
                <div class="metric-card">
                    <h3>Execution Time</h3>
                    <div class="metric-row">
                        <span class="metric-label">Baseline</span>
                        <span class="metric-value">{baseline_runtime:.3f} s</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Optimized</span>
                        <span class="metric-value">{optimized_runtime:.3f} s</span>
                    </div>
                    <div class="metric-savings">
                        <div class="savings-value">↓ {time_savings_pct:.0f}%</div>
                        <div class="savings-label">{time_saved:.3f} s faster</div>
                    </div>
                </div>
            </div>
            
            <div class="chart-container">
                <div class="chart-title">Energy Consumption Comparison</div>
                <div class="bar-chart">
                    <div class="bar-group">
                        <div class="bar"></div>
                        <div class="bar-label">Baseline</div>
                        <div class="bar-value">{baseline_energy:.2f} J</div>
                    </div>
                    <div class="bar-group">
                        <div class="bar optimized"></div>
                        <div class="bar-label">Optimized</div>
                        <div class="bar-value">{optimized_energy:.2f} J</div>
                    </div>
                </div>
                <div class="confidence-bar">
                    <div class="confidence-fill"></div>
                </div>
                <div style="text-align: center; margin-top: 15px; color: #6B7280; font-size: 0.9em;">
                    Detection Confidence: {confidence:.0f}%
                </div>
            </div>
            
            <div class="metric-card">
                <h3>Power Consumption</h3>
                <div class="metric-row">
                    <span class="metric-label">Average Power</span>
                    <span class="metric-value">{baseline_power:.1f} W</span>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>Petal Energy Optimizer | Energy-Aware Compilation Framework</p>
        </div>
    </div>
</body>
</html>
"""
    
    # Write HTML file
    output_file = Path(output_path) / f"{Path(filename).stem}_report.html"
    output_file.write_text(html_content)
    
    return str(output_file)
