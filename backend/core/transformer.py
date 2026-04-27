import re
import structlog

logger = structlog.get_logger("transformer")

# Default block size, can be overridden by parameter
DEFAULT_BLOCK_SIZE = 64

# Matches: int main() { — tolerates any whitespace before/after braces
_MAIN_OPEN = re.compile(r'(int\s+main\s*\(\s*\)\s*\{)')

# Matches the canonical 3-level naive loop nest for i/j/k with any whitespace
_NAIVE_LOOP = re.compile(
    r'for\s*\(\s*int\s+i\s*=\s*0\s*;\s*i\s*<\s*N\s*;\s*i\+\+\s*\)\s*\{'
    r'\s*for\s*\(\s*int\s+j\s*=\s*0\s*;\s*j\s*<\s*N\s*;\s*j\+\+\s*\)\s*\{'
    r'\s*for\s*\(\s*int\s+k\s*=\s*0\s*;\s*k\s*<\s*N\s*;\s*k\+\+\s*\)\s*\{'
    r'\s*(?P<body>[^}]+?)\s*\}\s*\}\s*\}',
    re.DOTALL,
)


def _tiled_loops(body: str, block_size: int) -> str:
    # Rewrite the inner body: replace i→ii, j→jj, k→kk
    tiled_body = re.sub(r'\bi\b', 'ii', body)
    tiled_body = re.sub(r'\bj\b', 'jj', tiled_body)
    tiled_body = re.sub(r'\bk\b', 'kk', tiled_body)
    bs = block_size
    return (
        f"for(int i=0; i<N; i+={bs}){{\n"
        f"        for(int j=0; j<N; j+={bs}){{\n"
        f"            for(int k=0; k<N; k+={bs}){{\n"
        f"                for(int ii=i; ii<i+{bs}; ii++){{\n"
        f"                    for(int jj=j; jj<j+{bs}; jj++){{\n"
        f"                        for(int kk=k; kk<k+{bs}; kk++){{\n"
        f"                            {tiled_body.strip()}\n"
        f"                        }}\n"
        f"                    }}\n"
        f"                }}\n"
        f"            }}\n"
        f"        }}\n"
        f"    }}"
    )


def apply_loop_tiling(source_code, block_size: int = DEFAULT_BLOCK_SIZE):
    logger.info("Applying 'Loop Tiling' transformation pass...")

    # Step 1: inject blockSize declaration after int main() {
    if not _MAIN_OPEN.search(source_code):
        logger.warning("Could not locate 'int main()' — transformation skipped.")
        return source_code

    result = _MAIN_OPEN.sub(
        r'\1\n    int blockSize = ' + str(block_size) + '; // Petal Injected Block Size',
        source_code,
        count=1,
    )

    # Step 2: replace the naive loop nest with tiled loops
    m = _NAIVE_LOOP.search(result)
    if not m:
        logger.warning("Nested loop pattern not recognised — transformation skipped.", tip="ensure the source uses the canonical i/j/k loop variables.")
        return result

    tiled = _tiled_loops(m.group('body'), block_size)
    result = result[:m.start()] + tiled + result[m.end():]

    logger.info("Loop tiling applied", block_size=block_size)
    return result
