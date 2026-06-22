#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys


COMMANDS = [
    [sys.executable, "-m", "py_compile", "server.py", "test_server.py", "scripts/check_readiness.py", "scripts/smoke_mcp_http.py", "scripts/local_beta_flow.py", "scripts/preflight.py"],
    [sys.executable, "test_server.py"],
    [sys.executable, "scripts/check_readiness.py"],
    [sys.executable, "scripts/smoke_mcp_http.py"],
    [sys.executable, "scripts/local_beta_flow.py"],
]


def main() -> None:
    for command in COMMANDS:
        print("+", " ".join(command), flush=True)
        subprocess.run(command, check=True)
    print("preflight ok")


if __name__ == "__main__":
    main()
