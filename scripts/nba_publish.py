#!/usr/bin/env python3
"""Refresh NBA value bets end to end and publish the encrypted nba.html.

Chain: Stake props (CDP, needs Chrome on stake.com) -> FanDuel (Firecrawl) -> EV -> page
-> staticrypt (DASHBOARD_PASSWORD from .env) -> git commit + push of nba.html only.
Raw data stays local; only the encrypted page is published.
"""

import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
SALT = "8669795df810e4666e526fa8a931d9da"  # same as the daily workflow so one login covers both pages
STATICRYPT = "staticrypt@3.5.4"


def run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    logger.info("$ %s", " ".join(c if c != os.environ.get("DASHBOARD_PASSWORD") else "***" for c in cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def main() -> None:
    load_dotenv(ROOT / ".env")
    password = os.environ.get("DASHBOARD_PASSWORD")
    if not password:
        raise SystemExit("DASHBOARD_PASSWORD missing in .env — add it so nba.html can be encrypted.")
    py = sys.executable

    if "--skip-fetch" not in sys.argv:  # rebuild the page from the last data without spending credits
        run(py, "scripts/nba_stake_scraper.py")
        run(py, "scripts/nba_fanduel.py")
    run(py, "scripts/nba_ev.py")
    run(py, "generate_nba.py", "build/nba_src.html")

    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise SystemExit("npx not found — install Node.js to encrypt the page.")
    shutil.rmtree(ROOT / "build" / "enc_nba", ignore_errors=True)
    run(npx, "--yes", STATICRYPT, "build/nba_src.html", "-p", password, "--short", "--salt", SALT,
        "--remember", "30", "--template-title", "Acceso", "--template-instructions", "Panel privado",
        "-d", "build/enc_nba")
    shutil.copy(ROOT / "build" / "enc_nba" / "nba_src.html", ROOT / "nba.html")

    if run("git", "diff", "--quiet", "--", "nba.html", check=False).returncode == 0 and \
            run("git", "ls-files", "--error-unmatch", "nba.html", check=False).returncode == 0:
        logger.info("nba.html unchanged — nothing to publish")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    run("git", "add", "nba.html")
    run("git", "commit", "-m", f"chore: update nba.html {stamp}")
    run("git", "pull", "--rebase", "--autostash", "origin", "main")
    run("git", "push", "origin", "main")
    logger.info("Published nba.html")


if __name__ == "__main__":
    main()
