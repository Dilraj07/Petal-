import os
import subprocess
import sys


def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(backend_dir, "main.py")
    cmd = [sys.executable, main_py, *sys.argv[1:]]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
