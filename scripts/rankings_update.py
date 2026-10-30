#!/usr/bin/env python3
"""Update data/rankings_cache.json from ESPN Core API (no Cloudflare, no auth).

ESPN has full ATP rankings updated weekly.
Endpoint: sports.core.api.espn.com/v2/sports/tennis/leagues/atp/seasons/{year}/rankings/1
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from git_sync import sync_push  # noqa: E402
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
CACHE_PATH = ROOT / "data" / "rankings_cache.json"
_BASES = {
    "atp": "https://sports.core.api.espn.com/v2/sports/tennis/leagues/atp",
    "wta": "https://sports.core.api.espn.com/v2/sports/tennis/leagues/wta",
}
_BASE = _BASES["atp"]  # kept for backwards compat
_YEAR = datetime.now().year


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def _get(url: str, sess: requests.Session, params: dict | None = None) -> dict | None:
    try:
        r = sess.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("GET %s: %s", url, exc)
        return None


def _latest_rankings_url(sess: requests.Session) -> str | None:
    """Get the URL of the most recent weekly rankings snapshot."""
    data = _get(f"{_BASE}/seasons/{_YEAR}/rankings/1", sess)
    if not data:
        return None
    refs = data.get("rankings", [])
    if not refs:
        return None
    # last item = most recent week
    return refs[-1].get("$ref")


def _athlete_name(ref: str, sess: requests.Session) -> str | None:
    data = _get(ref, sess)
    if not data:
        return None
    return data.get("fullName") or data.get("displayName")


def fetch_rankings(sess: requests.Session) -> dict[str, dict]:
    """Fetch ATP rankings from atptour.com (top 300) via cloudscraper."""
    try:
        import cloudscraper
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("cloudscraper/beautifulsoup4 not installed — falling back to ESPN (150 players)")
        return _fetch_rankings_espn(sess)

    scraper = cloudscraper.create_scraper()
    url = "https://www.atptour.com/en/rankings/singles"
    try:
        r = scraper.get(url, params={"rankRange": "1-300"}, timeout=25)
        r.raise_for_status()
    except Exception as exc:
        logger.warning("atptour.com fetch failed: %s — falling back to ESPN", exc)
        return _fetch_rankings_espn(sess)

    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 2:
        logger.warning("atptour.com table not found — falling back to ESPN")
        return _fetch_rankings_espn(sess)

    rankings: dict[str, dict] = {}
    for row in tables[1].find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        rank_num_text = re.sub(r"[^\d]", "", cells[0].get_text(strip=True))
        if not rank_num_text:
            continue
        rank = int(rank_num_text[:4])
        # Use link text to avoid rank-change prefix (e.g. "-14Tristan Schoolkate")
        link = cells[1].find("a")
        name = link.get_text(strip=True) if link else re.sub(r"^[+\-]?\d*", "", cells[1].get_text(strip=True)).strip()
        pts_text = re.sub(r"[^\d]", "", cells[3].get_text(strip=True))
        points = int(pts_text) if pts_text else 0
        if name:
            rankings[name] = {"rank": rank, "points": points}

    logger.info("Built ATP rankings for %d players (atptour.com)", len(rankings))
    if len(rankings) < 100:
        logger.warning("Too few ATP players (%d) from atptour.com — falling back to ESPN", len(rankings))
        return _fetch_rankings_espn(sess)
    return rankings


def _fetch_rankings_espn(sess: requests.Session) -> dict[str, dict]:
    """ESPN fallback — only returns top 150 ATP."""
    url = _latest_rankings_url(sess)
    if not url:
        raise ValueError("Could not find latest rankings URL")
    logger.info("Fetching ATP rankings from ESPN %s", url)

    data = _get(url, sess, params={"limit": 1000})
    if not data:
        raise ValueError("Empty response from rankings endpoint")

    ranks = data.get("ranks", [])
    rankings: dict[str, dict] = {}
    for entry in ranks:
        rank = entry.get("current")
        points = int(entry.get("points", 0))
        athlete_ref = (entry.get("athlete") or {}).get("$ref", "")
        if not rank or not athlete_ref:
            continue
        m = re.search(r"/athletes/(\d+)", athlete_ref)
        if not m:
            continue
        name = _athlete_name(athlete_ref, sess)
        if not name:
            continue
        rankings[name] = {"rank": rank, "points": points}
        time.sleep(0.05)

    return rankings


def _already_updated_today() -> bool:
    """True if rankings_cache.json's timestamp is already from today (UTC)."""
    if not CACHE_PATH.exists():
        return False
    try:
        cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        cached_date = datetime.fromisoformat(cached["timestamp"]).date()
    except Exception:
        return False
    return cached_date == datetime.now(timezone.utc).date()


def main() -> None:
    if "--force" not in sys.argv and _already_updated_today():
        logger.info("rankings_cache.json already updated today (UTC) — skipping")
        return

    sess = _session()

    # ATP rankings (atptour.com top 300, ESPN top 150 as fallback)
    rankings = fetch_rankings(sess)
    if len(rankings) < 100:
        raise ValueError(f"Too few ATP players ({len(rankings)}) — something went wrong")


    # sanity check
    top5 = sorted([(n, d) for n, d in rankings.items()], key=lambda x: x[1]["rank"])[:5]
    print("\nTop 5 (ATP):")
    for name, data in top5:
        print(f"  {data['rank']:>3}. {name:<25} {data['points']:>6} pts")

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ESPN Core API (ATP + WTA)",
        "player_count": len(rankings),
        "rankings": rankings,
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved to %s", CACHE_PATH)

    if os.environ.get("CI"):
        logger.info("CI mode — skipping git commit (workflow handles it)")
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        subprocess.run(["git", "add", str(CACHE_PATH)], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"data: rankings_cache.json ({ts}) — {len(rankings)} players"],
            cwd=ROOT, check=True,
        )
        sync_push()
        logger.info("Done")
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        logger.error("Git step failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
