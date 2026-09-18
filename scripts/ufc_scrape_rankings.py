"""Scrape UFC official rankings by division from ufc.com/rankings.

Output: data/ufc_rankings_cache.json
Run locally (requires requests; ufc.com may need cloudscraper).
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import cloudscraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_OUT = Path(__file__).resolve().parents[1] / "data" / "ufc_rankings_cache.json"
_URL = "https://www.ufc.com/rankings"


def main() -> None:
    scraper = cloudscraper.create_scraper()
    try:
        r = scraper.get(_URL, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        logger.error("Failed to fetch UFC rankings: %s", exc)
        return

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")

    rankings: dict[str, dict[str, int]] = {}  # division → {fighter_name: rank}

    # UFC rankings page structure: each division has an <h4> title + table
    divisions = soup.find_all("div", class_=re.compile(r"view-grouping"))
    for div in divisions:
        title_el = div.find(["h4", "h3", "div"], class_=re.compile(r"title|grouping-header"))
        if not title_el:
            continue
        division = title_el.get_text(strip=True)
        if not division:
            continue

        rows = div.select("table tbody tr, .views-row")
        div_rankings: dict[str, int] = {}

        for row in rows:
            rank_el = row.find(class_=re.compile(r"rank|views-field-weight-class-rank"))
            name_el = row.find("a") or row.find(class_=re.compile(r"name|athlete"))
            if not rank_el or not name_el:
                continue
            rank_text = rank_el.get_text(strip=True).replace("C", "0").replace("#", "").strip()
            name = name_el.get_text(strip=True)
            try:
                rank = int(rank_text) if rank_text.isdigit() else 0
                div_rankings[name] = rank
            except ValueError:
                continue

        if div_rankings:
            rankings[division] = div_rankings
            logger.info("Division: %s — %d fighters", division, len(div_rankings))

    if not rankings:
        logger.warning("No rankings parsed — page structure may have changed")

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rankings": rankings,
    }
    _OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved rankings for %d divisions to %s", len(rankings), _OUT)


if __name__ == "__main__":
    main()
