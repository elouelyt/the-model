#!/usr/bin/env python3
"""Refresh data/results.json (scripts/results_data.py) and encrypt it as data/results.enc for the 'Resultados' tab.

update() returns the file to `git add` (called from mix_publish.update, i.e. every NBA/NFL batch).
Run alone after the morning settlement to publish yesterday's results:  python scripts/results_publish.py --push
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import results_data  # noqa: E402
from private_crypto import encrypt_file  # noqa: E402


def update() -> list[str]:
    results_data.main()
    encrypt_file(ROOT / "data" / "results.json", ROOT / "data" / "results.enc")
    return ["data/results.enc"]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    files = update()
    if "--push" in sys.argv:
        subprocess.run(["git", "add", *files], cwd=ROOT, check=True)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
            subprocess.run(["git", "commit", "-m", "chore: update results tab"], cwd=ROOT, check=True)
            subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=ROOT, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True)
    print(files)
