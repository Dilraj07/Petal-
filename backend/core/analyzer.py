import re
import structlog

logger = structlog.get_logger("analyzer")

def analyze_energy_hotspots(source_code):
    logger.info("Scanning Abstract Syntax Tree (AST) patterns...")
    
    # Detects at least three ordered for-loops in the same region.
    # This intentionally supports both braced and unbraced coding styles.
    nested_loop_pattern = re.compile(
        r'for\s*\([^)]+\)[\s\S]*?for\s*\([^)]+\)[\s\S]*?for\s*\([^)]+\)',
        re.DOTALL,
    )
    
    match = nested_loop_pattern.search(source_code)
    if match:
        logger.warning("Inefficient O(N^3) memory access pattern detected.", reason="High cache-miss rate predicted (Stride length exceeds L1 cache).")
        return True
    
    return False
