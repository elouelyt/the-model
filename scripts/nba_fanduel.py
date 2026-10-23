#!/usr/bin/env python3
"""Fetch FanDuel NBA player over/under lines with Firecrawl for the games Stake lists.

Needs FIRECRAWL_API_KEY. Reads data/nba_stake_cache.json, writes data/nba_fanduel_cache.json.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from firecrawl import Firecrawl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STAKE_CACHE = ROOT / "data" / "nba_stake_cache.json"
OUT = ROOT / "data" / "nba_fanduel_cache.json"
NAV_URL = "https://sportsbook.fanduel.com/navigation/nba"

MARKETS = {  # FanDuel accordion label -> Stake stat name
    "Player Points": "points",
    "Player Rebounds": "rebounds",
    "Player Assists": "assists",
    "Player Made Threes": "threesmade",
    "Player Pts + Reb": "points+rebounds",
    "Player Pts + Ast": "points+assists",
    "Player Reb + Ast": "assists+rebounds",
    "Player Pts + Reb + Ast": "points+assists+rebounds",
}
TEAM_ALIASES = {"los-angeles-clippers": "la-clippers"}

CLICK_JS = (
    "(() => { const labels = %s; let n = 0;"
    " document.querySelectorAll('div[role=button][aria-expanded=false]').forEach(e => {"
    " if (labels.includes(e.getAttribute('aria-label'))) { e.click(); n++; } }); return n; })()"
) % json.dumps(list(MARKETS))

ROW_RE = re.compile(r"\n([A-Z][^\n]{2,40})\n+O (\d+\.\d)([+-]\d+)\n+U \d+\.\d([+-]\d+)")


def team_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return TEAM_ALIASES.get(slug, slug)


def parse_markets(markdown: str) -> list[dict]:
    """Extract (player, stat, line, over, under) rows from the expanded accordions."""
    rows = []
    for label, stat in MARKETS.items():
        start = markdown.find(f"- {label}\n")
        if start < 0:
            continue
        end = markdown.find("\n- ", start + 5)
        segment = markdown[start: end if end > 0 else len(markdown)]
        for name, line, over, under in ROW_RE.findall(segment):
            rows.append({"player": name.strip(), "stat": stat, "line": float(line),
                         "over_american": int(over), "under_american": int(under)})
    return rows


def main() -> None:
    load_dotenv(ROOT / ".env")
    app = Firecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])
    stake = json.loads(STAKE_CACHE.read_text(encoding="utf-8"))

    nav = app.scrape(NAV_URL, formats=["links"], wait_for=4000, timeout=90000)
    events = [u for u in (nav.links or []) if "/basketball/nba/" in u and "@" in u]
    logger.info("FanDuel lists %d NBA events", len(events))

    out_rows, credits = [], 0
    for game in stake["games"]:
        slugs = [team_slug(t) for t in game["teams"]]
        url = next((u for u in events if all(s in u for s in slugs)), None)
        if not url:
            logger.warning("No FanDuel event for %s", game["teams"])
            continue
        rows: list[dict] = []
        for attempt in range(2):
            try:
                doc = app.scrape(
                    url.split("?")[0] + "?tab=assists",
                    formats=["markdown"],
                    actions=[{"type": "wait", "milliseconds": 8000},
                             {"type": "executeJavascript", "script": CLICK_JS},
                             {"type": "wait", "milliseconds": 3000}],
                    timeout=120000,
                )
                rows = parse_markets(doc.markdown or "")
            except Exception as exc:  # noqa: BLE001
                logger.warning("FanDuel scrape failed for %s: %s", game["teams"], str(exc)[:120])
            if rows:
                break
        logger.info("%s: %d lines", " vs ".join(game["teams"]), len(rows))
        for r in rows:
            out_rows.append({"fixture": game["fixture"], **r})

    OUT.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                               "source": "FanDuel via Firecrawl", "rows": out_rows},
                              ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d FanDuel lines to %s", len(out_rows), OUT)


if __name__ == "__main__":
    main()
