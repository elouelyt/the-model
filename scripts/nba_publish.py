#!/usr/bin/env python3
"""Refresh NBA value bets and publish them (encrypted) for the private panel.

Chain: Stake props (CDP, needs Chrome on stake.com) -> BettingPros API (FanDuel, DraftKings, Caesars, BetMGM, Novig, ProphetX) + FanDuel (Firecrawl, complements the missing players) + Pinnacle (direct API) -> picks
-> data/nba_picks.enc (AES with DASHBOARD_PASSWORD) -> git commit + push.
The push triggers the "Rebuild private panel" workflow, which rebuilds panel.html.
Raw picks stay local; the repo only ever sees ciphertext.

  python scripts/nba_publish.py [--skip-fetch]   # --skip-fetch reuses the last scraped data
"""

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from private_crypto import encrypt_file  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
ENC = ROOT / "data" / "nba_picks.enc"


def run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    logger.info("$ %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check)


def main() -> None:
    load_dotenv(ROOT / ".env")
    if not os.environ.get("DASHBOARD_PASSWORD"):
        raise SystemExit("DASHBOARD_PASSWORD missing in .env — needed to encrypt the NBA picks.")
    py = sys.executable

    run(py, "scripts/nba_settle.py", check=False)  # settle yesterday's legs and combos with real box scores
    if "--skip-fetch" not in sys.argv:
        run(py, "scripts/nba_stake_scraper.py")
        run(py, "scripts/nba_fanduel.py")
    # The free BettingPros key allows 50 requests/day and a full pass costs ~37: spend it once, in the late run
    # (closest to tip-off). Earlier runs reuse FanDuel (Firecrawl) + Pinnacle. Force a pass with --bp.
    if "--bp" in sys.argv or datetime.now().hour >= 21:
        run(py, "scripts/nba_bettingpros.py", check=False)
    run(py, "scripts/nba_pinnacle.py")  # free public API, always refreshed
    run(py, "scripts/nba_ev.py")
    run(py, "scripts/nba_combos.py")
    encrypt_file(ROOT / "data" / "nba_picks.json", ENC)

    run("git", "add", "data/nba_picks.enc")
    if run("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        logger.info("No changes to publish")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    run("git", "commit", "-m", f"chore: update NBA picks {stamp}")
    run("git", "pull", "--rebase", "--autostash", "origin", "main")
    run("git", "push", "origin", "main")
    logger.info("Published NBA picks; the panel rebuilds in GitHub Actions (~2 min)")


if __name__ == "__main__":
    main()
