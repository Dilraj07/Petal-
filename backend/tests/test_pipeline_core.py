import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.analyzer import analyze_energy_hotspots
from core.transformer import apply_loop_tiling


NAIVE_SAMPLE = """#include <stdio.h>
#define N 512
int A[N][N], B[N][N], C[N][N];

int main() {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            for (int k = 0; k < N; k++) {
                C[i][j] += A[i][k] * B[k][j];
            }
        }
    }
    return 0;
}
"""


class TestPipelineCore(unittest.TestCase):
    def test_analyzer_detects_nested_hotspot(self):
        self.assertTrue(analyze_energy_hotspots(NAIVE_SAMPLE))

    def test_analyzer_ignores_non_nested_loop(self):
        source = "int main(){ for(int i=0;i<10;i++){ } return 0; }"
        self.assertFalse(analyze_energy_hotspots(source))

    def test_transformer_applies_loop_tiling_markers(self):
        optimized = apply_loop_tiling(NAIVE_SAMPLE, block_size=64)
        self.assertIn("int blockSize = 64", optimized)
        self.assertIn("for(int i=0; i<N; i+=64)", optimized)
        self.assertIn("for(int ii=i; ii<i+64; ii++)", optimized)
        self.assertIn("C[ii][jj] += A[ii][kk] * B[kk][jj];", optimized)

    def test_transformer_with_custom_block_size(self):
        optimized = apply_loop_tiling(NAIVE_SAMPLE, block_size=32)
        self.assertIn("int blockSize = 32", optimized)
        self.assertIn("for(int i=0; i<N; i+=32)", optimized)


if __name__ == "__main__":
    unittest.main()
