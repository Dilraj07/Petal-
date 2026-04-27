import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.transformer import apply_loop_tiling


class TestTransformerEdgeCases(unittest.TestCase):
    def test_skips_transformation_when_main_is_missing(self):
        source = "for (int i = 0; i < 10; i++) { }"
        self.assertEqual(apply_loop_tiling(source), source)

    def test_injects_blocksize_even_when_loop_pattern_not_recognized(self):
        source = """#define N 16
int main() {
    for (int x = 0; x < N; x++) { }
    return 0;
}
"""
        transformed = apply_loop_tiling(source)
        self.assertIn("int blockSize = 64", transformed)
        self.assertIn("for (int x = 0; x < N; x++)", transformed)
        self.assertNotIn("for(int i=0; i<N; i+=64)", transformed)

    def test_rewrite_preserves_non_loop_index_identifiers(self):
        source = """#define N 8
int C[N][N], A[N][N], B[N][N];
int main() {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            for (int k = 0; k < N; k++) {
                C[i_index][j] += A[i][k] * B[k][j];
            }
        }
    }
    return 0;
}
"""
        transformed = apply_loop_tiling(source)
        self.assertIn("C[i_index][jj] += A[ii][kk] * B[kk][jj];", transformed)
        self.assertIn("i_index", transformed)
        self.assertNotIn("ii_index", transformed)
        self.assertNotIn("C[i_index][j] += A[i][k] * B[k][j];", transformed)


if __name__ == "__main__":
    unittest.main()
