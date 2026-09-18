"""Scrape UFC fighter stats from ufcstats.com.

Fetches all fighters A-Z: height, reach, DOB, record, sig strike %, TD%, TD def%, sub avg.
Output: data/ufc_fighters_cache.json
Run locally (no VPN needed — ufcstats.com is not behind Cloudflare).
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

_OUT = Path(__file__).resolve().parents[1] / "data" / "ufc_fighters_cache.json"
_BASE = "http://ufcstats.com/statistics/fighters"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; UFC-scraper/1.0)"}


def _inches_to_cm(val: str) -> float | None:
    """Convert '6\' 2"' or '74"' to cm."""
    val = val.strip()
    if not val or val == "--":
        return None
    try:
        if "'" in val:
            parts = val.replace('"', "").split("'")
            feet, inches = int(parts[0].strip()), float(parts[1].strip() or 0)
            return round((feet * 12 + inches) * 2.54, 1)
        if '"' in val:
            return round(float(val.replace('"', "")) * 2.54, 1)
    except Exception:
        pass
    return None


def _parse_pct(val: str) -> float | None:
    val = val.strip().replace("%", "")
    if not val or val == "--":
        return None
    try:
        return round(float(val) / 100, 4)
    except Exception:
        return None


def _parse_dob(val: str) -> str | None:
    val = val.strip()
    if not val or val == "--":
        return None
    try:
        return datetime.strptime(val, "%b %d, %Y").date().isoformat()
    except Exception:
        return None


def _age(dob_iso: str | None) -> float | None:
    if not dob_iso:
        return None
    try:
        born = datetime.fromisoformat(dob_iso)
        return round((datetime.now() - born).days / 365.25, 1)
    except Exception:
        return None


def scrape_page(char: str) -> list[dict]:
    url = f"{_BASE}?char={char}&page=all"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table.b-statistics__table tbody tr")
    fighters = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 10:
            continue
        texts = [c.get_text(strip=True) for c in cells]
        first, last = texts[0], texts[1]
        if not first and not last:
            continue
        name = f"{first} {last}".strip()
        nick = texts[2]
        height_cm = _inches_to_cm(texts[3])
        reach_cm = _inches_to_cm(texts[4])
        stance = texts[5]
        dob = _parse_dob(texts[6])
        sig_str_acc = _parse_pct(texts[7])
        sig_str_def = _parse_pct(texts[8])
        td_acc = _parse_pct(texts[9])
        td_def = _parse_pct(texts[10]) if len(texts) > 10 else None

        # Win/Loss/Draw from first cell link title if available
        link = cells[0].find("a")
        fighter_url = link["href"] if link and link.get("href") else None

        fighters.append({
            "name": name,
            "nickname": nick or None,
            "height_cm": height_cm,
            "reach_cm": reach_cm,
            "stance": stance or None,
            "dob": dob,
            "age": _age(dob),
            "sig_str_acc": sig_str_acc,
            "sig_str_def": sig_str_def,
            "td_acc": td_acc,
            "td_def": td_def,
            "url": fighter_url,
        })
    return fighters


def main() -> None:
    all_fighters: dict[str, dict] = {}
    alphabet = "abcdefghijklmnopqrstuvwxyz"

    for char in alphabet:
        logger.info("Scraping fighters: %s", char.upper())
        batch = scrape_page(char)
        for f in batch:
            all_fighters[f["name"]] = f
        logger.info("  → %d fighters (total: %d)", len(batch), len(all_fighters))
        time.sleep(0.5)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(all_fighters),
        "fighters": all_fighters,
    }
    _OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d fighters to %s", len(all_fighters), _OUT)


if __name__ == "__main__":
    main()
