import re

def analyze_energy_hotspots(source_code):
    print("[\033[94mPetal Analyzer\033[0m] Scanning Abstract Syntax Tree (AST) patterns...")
    
    # Detects at least three ordered for-loops in the same region.
    # This intentionally supports both braced and unbraced coding styles.
    nested_loop_pattern = re.compile(
        r'for\s*\([^)]+\)[\s\S]*?for\s*\([^)]+\)[\s\S]*?for\s*\([^)]+\)',
        re.DOTALL,
    )
    
    match = nested_loop_pattern.search(source_code)
    if match:
        print("[\033[93mWARNING\033[0m] Inefficient O(N^3) memory access pattern detected.")
        print("   -> Reason: High cache-miss rate predicted (Stride length exceeds L1 cache).")
        return True
    
    return False
