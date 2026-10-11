#!/usr/bin/env python3
"""
Antigravity PostToolUse hook for Vault.
Runs `codegraph sync` whenever files are modified by tools.
"""
import json
import shutil
import subprocess
import sys

def main():
    try:
        # Drain stdin
        sys.stdin.read()
    except Exception:
        pass

    if shutil.which("codegraph"):
        try:
            subprocess.run(
                ["codegraph", "sync"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False
            )
        except Exception:
            pass

    # PostToolUse expects empty JSON dict on stdout
    print(json.dumps({}))

if __name__ == "__main__":
    main()
