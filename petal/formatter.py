"""Rich formatting helpers for Petal CLI output."""

import sys
from typing import Any, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────
# Color & Style Codes (works on Windows, Mac, Linux)
# ─────────────────────────────────────────────────────────────────────────

class Color:
    """ANSI color codes (compatible with all platforms)."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Foreground colors
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    
    # Extended colors
    SUCCESS = GREEN
    ERROR = RED
    WARNING = YELLOW
    INFO = BLUE
    ACCENT = CYAN


def supports_unicode() -> bool:
    """Check if terminal supports unicode."""
    try:
        return (
            sys.stdout.encoding.lower() in ('utf-8', 'utf8') or
            sys.platform == 'win32'  # Windows Terminal supports unicode
        )
    except Exception as e:
        return False


# ─────────────────────────────────────────────────────────────────────────
# Formatting Functions
# ─────────────────────────────────────────────────────────────────────────

def fmt_energy(joules: float) -> str:
    """Format energy value with appropriate unit."""
    if joules < 0.001:
        return f"{joules * 1_000_000:.1f} µJ"
    if joules < 1.0:
        return f"{joules * 1_000:.1f} mJ"
    return f"{joules:.2f} J"


def fmt_time(seconds: float) -> str:
    """Format time value with appropriate unit."""
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f} µs"
    if seconds < 1.0:
        return f"{seconds * 1_000:.1f} ms"
    return f"{seconds:.3f} s"


def fmt_power(watts: float) -> str:
    """Format power value with appropriate unit."""
    if watts < 1.0:
        return f"{watts * 1_000:.1f} mW"
    return f"{watts:.1f} W"


def color(text: str, c: str) -> str:
    """Apply color to text."""
    return f"{c}{text}{Color.RESET}"


def bold(text: str) -> str:
    """Make text bold."""
    return f"{Color.BOLD}{text}{Color.RESET}"


def dim(text: str) -> str:
    """Make text dim/gray."""
    return f"{Color.DIM}{text}{Color.RESET}"


def success(text: str) -> str:
    """Format text as success (green)."""
    return color(text, Color.SUCCESS)


def error(text: str) -> str:
    """Format text as error (red)."""
    return color(text, Color.ERROR)


def warning(text: str) -> str:
    """Format text as warning (yellow)."""
    return color(text, Color.WARNING)


def info(text: str) -> str:
    """Format text as info (blue)."""
    return color(text, Color.INFO)


def accent(text: str) -> str:
    """Format text as accent (cyan)."""
    return color(text, Color.ACCENT)


# ─────────────────────────────────────────────────────────────────────────
# Box Drawing
# ─────────────────────────────────────────────────────────────────────────

def print_header(text: str, width: int = 70) -> None:
    """Print a bold header with ASCII art for Petal."""
    ascii_art = f"""{Color.GREEN}
  _____  ______ _______       _      
 |  __ \\|  ____|__   __|/\\   | |     
 | |__) | |__     | |  /  \\  | |     
 |  ___/|  __|    | | / /\\ \\ | |     
 | |    | |____   | |/ ____ \\| |____ 
 |_|    |______|  |_/_/    \\_\\______|
{Color.RESET}"""
    print(ascii_art)
    print(f"     {Color.CYAN}{bold(text)}{Color.RESET}\n")


def print_section(title: str, content: list[str], width: int = 70) -> None:
    """Print a section with title and content."""
    if supports_unicode():
        print(f"{Color.CYAN}╭─ {title} {('─' * (width - len(title) - 6))}{Color.RESET}")
        for line in content:
            print(f"{Color.CYAN}│{Color.RESET} {line}")
        print(f"{Color.CYAN}╰{'─' * (width - 2)}{Color.RESET}\n")
    else:
        print(f"\n{bold(title)}")
        print('-' * width)
        for line in content:
            print(f"  {line}")
        print()


def print_table(headers: list[str], rows: list[list[str]], width: int = 70) -> None:
    """Print a simple ASCII table."""
    if not headers or not rows:
        return
    
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))
    
    # Print header
    sep = "─" * 3
    header_line = " │ ".join(
        f"{h:^{col_widths[i]}}" for i, h in enumerate(headers)
    )
    if supports_unicode():
        print(f" {header_line} ")
        divider = " ┼ ".join("─" * w for w in col_widths)
        print(f" {divider} ")
    else:
        print(f" {header_line} ")
        divider = " | ".join("-" * w for w in col_widths)
        print(f" {divider} ")
    
    # Print rows
    for row in rows:
        row_line = " │ ".join(
            f"{cell:^{col_widths[i]}}" for i, cell in enumerate(row)
        )
        print(f" {row_line} ")


def print_comparison(baseline: float, optimized: float, label: str = "Energy", unit: str = "J") -> None:
    """Print before/after comparison with visual bar."""
    if baseline <= 0:
        return
    
    delta = baseline - optimized
    delta_pct = (delta / baseline) * 100 if baseline > 0 else 0
    
    # Determine colors
    if delta_pct > 0:
        delta_color = success
        delta_arrow = "↓"
    else:
        delta_color = error
        delta_arrow = "↑"
    
    baseline_fmt = f"{baseline:.2f}"
    optimized_fmt = f"{optimized:.2f}"
    delta_fmt = delta_color(f"{abs(delta):.2f}")
    
    print(f"{label} Comparison:")
    print(f"  Baseline:  {baseline_fmt:>10} {unit}")
    print(f"  Optimized: {optimized_fmt:>10} {unit}")
    print(f"  {delta_arrow} Saved:    {delta_fmt:>10} {unit}  ({delta_color(f'{abs(delta_pct):.1f}%')})")


def print_savings_badge(energy_delta_pct: float, runtime_delta_pct: float) -> None:
    """Print eye-catching savings badge."""
    if energy_delta_pct <= 0:
        print(warning("⚠ No energy savings (optimization not beneficial)"))
        return
    
    badge = f"{energy_delta_pct:.0f}% ENERGY SAVED"
    print(f"\n{success(bold(badge))}")
    
    if runtime_delta_pct > 0:
        print(f"  Bonus: {success(f'{runtime_delta_pct:.0f}% faster')} execution")


def print_spinner_frame(frame: int) -> str:
    """Get spinner frame for progress indication."""
    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    return spinner[frame % len(spinner)]


def quality_tag(collector_info: dict) -> str:
    """Format data quality indicator."""
    name = collector_info.get("used", "unknown")
    confidence = collector_info.get("confidence", "low")
    
    if confidence == "high":
        return info(f"[source: {name} - hardware telemetry]")
    else:
        return warning(f"[source: {name} - estimated ±35%]")


def checklist_item(text: str, checked: bool = True) -> str:
    """Format a checklist item."""
    mark = success("[✓]") if checked else error("[✗]")
    return f"{mark} {text}"
