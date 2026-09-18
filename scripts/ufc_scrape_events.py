"""Scrape UFC historical fight results from ufcstats.com for model training.

Fetches all completed events → all fights → winner, loser, method, round.
Output: data/ufc_fights_history.json
Run once locally to build training dataset.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_OUT = Path(__file__).resolve().parents[1] / "data" / "ufc_fights_history.json"
_BASE = "http://ufcstats.com"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; UFC-scraper/1.0)"}


def _get(url: str, retries: int = 3) -> requests.Response | None:
    for i in range(retries):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=20)
            r.raise_for_status()
            return r
        except Exception as exc:
            logger.warning("GET %s attempt %d failed: %s", url, i + 1, exc)
            time.sleep(2 ** i)
    return None


def fetch_event_urls() -> list[tuple[str, str]]:
    """Return list of (event_name, event_url) for all completed events."""
    r = _get(f"{_BASE}/statistics/events/completed?page=all")
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table.b-statistics__table tbody tr")
    events = []
    for row in rows:
        link = row.find("a")
        if link and link.get("href"):
            events.append((link.get_text(strip=True), link["href"]))
    logger.info("Found %d completed events", len(events))
    return events


def fetch_fights_from_event(event_url: str) -> list[dict]:
    """Return fights list from one event page."""
    r = _get(event_url)
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table.b-fight-details__table tbody tr")
    fights = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 8:
            continue
        texts = [c.get_text(" ", strip=True) for c in cells]

        # fighters are in cells[1] as two <p> elements
        fighter_ps = cells[1].find_all("p")
        if len(fighter_ps) < 2:
            continue
        f1 = fighter_ps[0].get_text(strip=True)
        f2 = fighter_ps[1].get_text(strip=True)

        # winner badge: first fighter listed wins (ufcstats always puts winner first)
        # unless "NC" or "Draw"
        method_cell = cells[7] if len(cells) > 7 else None
        method_ps = method_cell.find_all("p") if method_cell else []
        method = method_ps[0].get_text(strip=True) if method_ps else ""
        method_detail = method_ps[1].get_text(strip=True) if len(method_ps) > 1 else ""

        # outcome
        outcome_ps = cells[0].find_all("p") if cells else []
        outcome = outcome_ps[0].get_text(strip=True) if outcome_ps else ""

        if outcome in ("NC", "D") or "draw" in method.lower() or "nc" in method.lower():
            continue  # skip no-contests and draws

        round_cell = cells[8] if len(cells) > 8 else None
        rnd = round_cell.get_text(strip=True) if round_cell else ""
        time_cell = cells[9] if len(cells) > 9 else None
        fight_time = time_cell.get_text(strip=True) if time_cell else ""

        weight_ps = cells[6].find_all("p") if len(cells) > 6 else []
        weight_class = weight_ps[0].get_text(strip=True) if weight_ps else ""

        fights.append({
            "winner": f1,
            "loser": f2,
            "method": method,
            "method_detail": method_detail,
            "round": rnd,
            "time": fight_time,
            "weight_class": weight_class,
        })
    return fights


def main() -> None:
    events = fetch_event_urls()
    all_fights = []

    for i, (event_name, event_url) in enumerate(events):
        fights = fetch_fights_from_event(event_url)
        for f in fights:
            f["event"] = event_name
        all_fights.extend(fights)
        if (i + 1) % 20 == 0:
            logger.info("Processed %d/%d events — %d fights total", i + 1, len(events), len(all_fights))
        time.sleep(0.3)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(all_fights),
        "fights": all_fights,
    }
    _OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d fights to %s", len(all_fights), _OUT)


if __name__ == "__main__":
    main()
