"""Petal server — thin wrapper for backward compatibility."""

from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main() -> None:
    from backend.server import app
    debug_mode = os.getenv('PETAL_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_mode, port=5000)


if __name__ == "__main__":
    main()
