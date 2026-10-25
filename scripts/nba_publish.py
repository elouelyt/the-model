#!/usr/bin/env python3
"""Refresh NBA value bets and publish them (encrypted) for the private panel.

Chain: Stake props (CDP, needs Chrome on stake.com) -> BettingPros API (FanDuel, DraftKings, Caesars, BetMGM, Novig, ProphetX) + FanDuel (Firecrawl, complements the missing players) + Pinnacle (direct API) -> picks
-> data/nba_picks.enc (AES with DASHBOARD_PASSWORD) -> git commit + push.
The push triggers the "Rebuild private panel" workflow, which rebuilds panel.html.
Raw picks stay local; the repo only ever sees ciphertext.

  python scripts/nba_publish.py [--skip-fetch]   # --skip-fetch reuses the last scraped data
"""

import json
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
    # The free BettingPros key allows 50 requests/day and a full pass costs ~37: spend it once a day, in the first batch from
    # 17:00 (nba_bettingpros.py then skips while its cache is < 7 h old). Morning runs use FanDuel (Firecrawl) + Pinnacle. Force with --bp.
    if "--bp" in sys.argv or datetime.now().hour >= 17:   # first afternoon batch; the 7 h cache then serves the later ones
        run(py, "scripts/nba_bettingpros.py", check=False)
    run(py, "scripts/nba_pinnacle.py")  # free public API, always refreshed
    run(py, "scripts/nba_ev.py")
    # consensus + all books from the BettingPros WEBSITE (player pages, no API cap) for the players with candidate legs, then EV again
    run(py, "scripts/bp_web.py", "nba", "--max", "45", check=False)
    run(py, "scripts/nba_ev.py")
    run(py, "scripts/nba_combos.py")
    encrypt_file(ROOT / "data" / "nba_picks.json", ENC)
    bundle = {p.name: json.loads(p.read_text(encoding="utf-8"))
              for folder in ("nba_history", "nba_baseline") for p in sorted((ROOT / "data" / folder).glob("*.json"))}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "nba_history_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    encrypt_file(ROOT / "build" / "nba_history_bundle.json", ROOT / "data" / "nba_history.enc")  # encrypted backup

    mix_files: list[str] = []
    try:  # mixed NBA+NFL combos for the 'Combinadas' tab
        sys.path.insert(0, str(ROOT / "scripts"))
        import mix_publish
        mix_files = mix_publish.update()
    except Exception as exc:  # noqa: BLE001
        logger.warning("mix combos skipped: %s", exc)
    run("git", "add", "data/nba_picks.enc", "data/nba_history.enc", *mix_files)
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
