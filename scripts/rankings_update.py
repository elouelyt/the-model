#!/usr/bin/env python3
"""Update data/rankings_cache.json by scraping the ATP Tour rankings page.

Run locally once per week (rankings update every Monday):
    python scripts/rankings_update.py

Flow:
1. Scrape atptour.com/en/rankings/singles (top 500) with cloudscraper
2. Write data/rankings_cache.json with timestamp
3. git add + commit + push so GitHub Actions picks it up
"""

import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import cloudscraper
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
CACHE_PATH = ROOT / "data" / "rankings_cache.json"

_ATP_URL = "https://www.atptour.com/en/rankings/singles?rankRange=1-500"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}


def scrape_rankings() -> dict[str, dict]:
    """Scrape ATP rankings page and return name → {rank, points} dict."""
    logger.info("Fetching ATP rankings from %s …", _ATP_URL)
    s = cloudscraper.create_scraper()
    resp = s.get(_ATP_URL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tbody tr")

    if not rows:
        raise ValueError("Could not find rankings table — page structure may have changed")

    rankings: dict[str, dict] = {}
    rank_counter = 0

    for row in rows:
        cells = row.select("td")
        if len(cells) < 3:
            continue

        rank_text = re.sub(r"[^\d]", "", cells[0].get_text(strip=True))
        if not rank_text:
            rank_counter += 1
            rank = rank_counter
        else:
            rank = int(rank_text)
            rank_counter = rank

        player_link = row.select_one('a[href*="/en/players/"]')
        if not player_link:
            continue
        href = player_link.get("href", "")
        slug_match = re.search(r"/en/players/([^/]+)/", href)
        if not slug_match:
            continue
        full_name = slug_match.group(1).replace("-", " ").title()

        points_text = re.sub(r"[^\d]", "", cells[2].get_text(strip=True))
        if not points_text:
            continue
        points = int(points_text)

        if full_name not in rankings:
            rankings[full_name] = {"rank": rank, "points": points}

    if not rankings:
        raise ValueError("No players parsed from ATP page — page structure may have changed")

    logger.info("Scraped %d players from ATP rankings", len(rankings))
    return rankings


def main() -> None:
    rankings = scrape_rankings()

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "player_count": len(rankings),
        "rankings": rankings,
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d players to %s", len(rankings), CACHE_PATH)

    # Print top 10 as sanity check
    top10 = sorted(rankings.items(), key=lambda x: x[1]["rank"])[:10]
    print("\nTop 10 ATP:")
    for name, data in top10:
        print(f"  {data['rank']:>3}. {name:<25} {data['points']:>6} pts")

    # git add + commit + push
    logger.info("Committing and pushing rankings_cache.json …")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        subprocess.run(["git", "add", str(CACHE_PATH)], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m",
             f"data: update rankings_cache.json ({ts}) — {len(rankings)} players"],
            cwd=ROOT, check=True,
        )
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True)
        logger.info("Done — rankings_cache.json live on GitHub")
    except subprocess.CalledProcessError as exc:
        logger.error("Git step failed: %s", exc)
        logger.info(
            "Cache was written locally. Push manually:\n"
            "  git add data/rankings_cache.json && git commit -m 'data: rankings cache' && git push"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
