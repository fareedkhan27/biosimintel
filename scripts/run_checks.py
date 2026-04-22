from __future__ import annotations

import subprocess
import sys


def run_command(cmd: list[str]) -> int:
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    checks = [
        ["ruff", "check", "."],
        ["mypy", "app"],
        ["pytest", "--cov=app", "--cov-fail-under=80"],
    ]
    exit_code = 0
    for cmd in checks:
        code = run_command(cmd)
        if code != 0:
            exit_code = code
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
