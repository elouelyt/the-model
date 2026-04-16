#!/usr/bin/env python3
"""Update data/stake_cache.json from the Stake API.

Run locally with VPN active:
    python scripts/stake_update.py

Flow:
1. Fetch active ATP odds from The Odds API to get current player names
2. Call fetch_stake_odds() with those names (requires VPN / non-blocked IP)
3. Write data/stake_cache.json with timestamp
4. git add + commit + push so GitHub Actions picks it up in the next run
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
CACHE_PATH = ROOT / "data" / "stake_cache.json"


def main() -> None:
    sys.path.insert(0, str(ROOT))

    # ── Step 1: get active player names from The Odds API ─────────────────────
    logger.info("Fetching active ATP odds to collect player names...")
    from src.ingestion.extract_odds import fetch_odds
    from src.processing.transform import flatten_odds, filter_upcoming

    raw = fetch_odds()
    if not raw:
        logger.error("No odds returned from The Odds API — is THE_ODDS_API_KEY set?")
        sys.exit(1)

    df = filter_upcoming(flatten_odds(raw))
    if df.empty:
        logger.error("No upcoming matches found — nothing to cache")
        sys.exit(1)

    players = sorted(df["outcome_name"].unique().tolist())
    logger.info("%d active players: %s", len(players), players)

    # ── Step 2: fetch Stake odds (VPN required) ───────────────────────────────
    logger.info("Fetching Stake odds (VPN required)...")
    from src.agents.stake_agent import fetch_stake_odds

    odds = fetch_stake_odds(players)

    if not odds:
        logger.error(
            "fetch_stake_odds returned empty — check VPN is active and try again"
        )
        sys.exit(1)

    logger.info(
        "Stake odds fetched for %d / %d players: %s",
        len(odds), len(players), odds,
    )

    # ── Step 3: write cache ───────────────────────────────────────────────────
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "player_count": len(odds),
        "odds": odds,
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info("Saved %d entries to %s", len(odds), CACHE_PATH)

    # ── Step 4: git add + commit + push ──────────────────────────────────────
    logger.info("Committing and pushing stake_cache.json...")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        subprocess.run(["git", "add", str(CACHE_PATH)], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m",
             f"data: update stake_cache.json ({ts}) — {len(odds)} players"],
            cwd=ROOT, check=True,
        )
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True)
        logger.info("Done — stake_cache.json live on GitHub")
    except subprocess.CalledProcessError as exc:
        logger.error("Git step failed: %s", exc)
        logger.info(
            "Cache file was written locally. Push manually:\n"
            "  git add data/stake_cache.json && git commit -m 'data: stake cache' && git push"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
