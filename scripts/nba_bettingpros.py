#!/usr/bin/env python3
"""Fetch NBA player over/under lines from several books through the BettingPros API.

Needs BETTINGPROS_API_KEY in .env. Reads data/nba_stake_cache.json to map games to Stake fixtures and
writes data/nba_bettingpros_cache.json (one row per book / player / stat / line). One request per page of
one market, so a full run is about 30 calls and costs no Firecrawl credits.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STAKE_CACHE = ROOT / "data" / "nba_stake_cache.json"
OUT = ROOT / "data" / "nba_bettingpros_cache.json"
BASE = "https://api.bettingpros.com/v3"
USAGE = ROOT / "data" / "bettingpros_usage.json"
DAILY_BUDGET = int(os.environ.get("BETTINGPROS_DAILY_LIMIT", "45"))  # free plan ~50; keep a margin
MAX_ODDS = 400  # exchanges (Novig, ProphetX) quote placeholders like -99900 when one side has no liquidity
MAX_AGE = timedelta(hours=4)  # ignore lines a book has not refreshed for this long

MARKETS = {  # BettingPros market id -> Stake stat name, most useful first (no threes: not in the source method)
    151: "assists", 157: "rebounds", 156: "points", 338: "points+assists+rebounds",
    337: "assists+rebounds", 336: "points+rebounds", 335: "points+assists",
}
# Reference books only: no DFS apps (PrizePicks, Underdog, Sleeper, Betr...), no prediction markets,
# no soft books that just copy the others. Pinnacle comes from its own API (nba_pinnacle.py).
BOOKS = {"bettingpros": "Consensus",  # BettingPros own average of ALL books (incl. soft and DFS): kept only for comparison
         "fanduel": "FanDuel", "draftkings": "DraftKings", "williamhill": "Caesars",
         "betMGM": "BetMGM", "novig": "Novig", "prophetx": "ProphetX"}
TEAMS = {  # BettingPros abbreviation -> nickname (last word of the Stake team name)
    "ATL": "hawks", "BOS": "celtics", "BKN": "nets", "CHA": "hornets", "CHI": "bulls", "CLE": "cavaliers",
    "DAL": "mavericks", "DEN": "nuggets", "DET": "pistons", "GSW": "warriors", "GS": "warriors",
    "HOU": "rockets", "IND": "pacers", "LAC": "clippers", "LAL": "lakers", "MEM": "grizzlies",
    "MIA": "heat", "MIL": "bucks", "MIN": "timberwolves", "NOR": "pelicans", "NO": "pelicans",
    "NOP": "pelicans", "NYK": "knicks", "NY": "knicks", "OKC": "thunder", "ORL": "magic",
    "PHI": "76ers", "PHO": "suns", "PHX": "suns", "POR": "blazers", "SAC": "kings", "SAS": "spurs",
    "SA": "spurs", "TOR": "raptors", "UTA": "jazz", "UTAH": "jazz", "WAS": "wizards", "WSH": "wizards",
}


def _spend() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    used = json.loads(USAGE.read_text(encoding="utf-8")) if USAGE.exists() else {}
    if used.get("date") != today:
        used = {"date": today, "n": 0}
    if used["n"] >= DAILY_BUDGET:
        raise RuntimeError(f"BettingPros daily budget of {DAILY_BUDGET} requests used")
    used["n"] += 1
    USAGE.write_text(json.dumps(used), encoding="utf-8")


def get(path: str, headers: dict, **params) -> dict:
    _spend()
    for attempt in range(6):
        r = requests.get(f"{BASE}/{path}", headers=headers, params=params, timeout=45)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))  # rate limited: wait longer each time
            continue
        r.raise_for_status()
        time.sleep(0.4)
        return r.json()
    raise RuntimeError(f"BettingPros rate limited on {path}")


def pages(path: str, key: str, headers: dict, **params):
    page = 1
    while True:
        data = get(path, headers, page=page, **params)
        yield from data[key]
        if page >= data["_pagination"]["total_pages"]:
            return
        page += 1


def main() -> None:
    load_dotenv(ROOT / ".env")
    if OUT.exists() and "--force" not in sys.argv:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(OUT.read_text(encoding="utf-8"))["timestamp"])
        if age < timedelta(hours=7):  # one full pass (~37 of the 50 daily requests) serves every later batch of the day
            logger.info("BettingPros cache is %d min old — skipping (use --force to refetch)", age.total_seconds() // 60)
            return
    key = os.environ.get("BETTINGPROS_API_KEY")
    if not key:
        raise SystemExit("BETTINGPROS_API_KEY missing in .env")
    headers = {"x-api-key": key, "User-Agent": "Mozilla/5.0"}
    stake = json.loads(STAKE_CACHE.read_text(encoding="utf-8"))
    game_by_teams = {frozenset(t.split()[-1].lower() for t in g["teams"]): g["fixture"] for g in stake["games"]}

    dates = set()
    for g in stake["games"]:
        d = parsedate_to_datetime(g["start"]).date()
        dates |= {d - timedelta(days=1), d, d + timedelta(days=1)}
    fixture_by_event: dict[int, str] = {}
    for d in sorted(dates):
        for ev in get("events", headers, sport="NBA", date=d.isoformat())["events"]:
            teams = frozenset(TEAMS.get(a, "?") for a in (ev.get("home"), ev.get("visitor")))
            if teams in game_by_teams:
                fixture_by_event[ev["id"]] = game_by_teams[teams]
    if not fixture_by_event:
        logger.warning("No BettingPros events matched the Stake games")
    event_ids = ":".join(str(e) for e in fixture_by_event)
    now = datetime.now(timezone.utc)

    rows, calls, stopped = [], 0, False
    for market_id, stat in MARKETS.items():
        if not event_ids or stopped:
            break
        try:
            gen = list(pages("offers", "offers", headers, sport="NBA", market_id=market_id, event_id=event_ids))
        except RuntimeError as exc:
            logger.warning("%s — stopping with the markets fetched so far", exc)
            stopped = True
            continue
        for offer in gen:
            calls += 1
            fixture = fixture_by_event.get(offer["event_id"])
            part = (offer.get("participants") or [{}])[0]
            if not fixture or not part.get("name"):
                continue
            sel = {s["selection"]: {b["id"]: b for b in s["books"]} for s in offer["selections"]}
            over_books, under_books = sel.get("over", {}), sel.get("under", {})
            for bid, ob in over_books.items():
                ub = under_books.get(bid)
                if not ub:
                    continue
                ol, ul = ob["lines"][0], ub["lines"][0]
                slug = BOOKS_BY_ID.get(bid)
                if slug is None or ol["is_off"] or ul["is_off"] or not ol["active"] or not ul["active"]:
                    continue
                if ol["line"] != ul["line"] or ol["cost"] is None or ul["cost"] is None:
                    continue
                if abs(ol["cost"]) > MAX_ODDS or abs(ul["cost"]) > MAX_ODDS:
                    continue
                updated = datetime.strptime(ol["updated"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if now - updated > MAX_AGE:
                    continue
                rows.append({"book": BOOKS[slug], "fixture": fixture, "player": part["name"], "stat": stat,
                             "line": float(ol["line"]), "over_american": int(ol["cost"]),
                             "under_american": int(ul["cost"]), "updated": ol["updated"]})
        time.sleep(0.3)

    OUT.write_text(json.dumps({"timestamp": now.isoformat(), "source": "BettingPros API",
                               "rows": rows}, ensure_ascii=False), encoding="utf-8")
    by_book: dict[str, int] = {}
    for r in rows:
        by_book[r["book"]] = by_book.get(r["book"], 0) + 1
    logger.info("Saved %d lines from %d calls (%s)", len(rows), calls, by_book)


BOOKS_BY_ID: dict[int, str] = {0: "bettingpros", 10: "fanduel", 12: "draftkings", 13: "williamhill",
                                19: "betMGM", 60: "novig", 38: "prophetx"}  # ids from /v3/books (resolved live if missing)


def load_book_ids() -> None:
    """Resolve the book slugs to the numeric ids the offers endpoint uses."""
    headers = {"x-api-key": os.environ["BETTINGPROS_API_KEY"], "User-Agent": "Mozilla/5.0"}
    for b in pages("books", "books", headers, sport="NBA"):
        if b["slug"] in BOOKS:
            BOOKS_BY_ID[b["id"]] = b["slug"]


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    if len(BOOKS_BY_ID) < len(BOOKS):
        load_book_ids()
    try:
        main()
    except RuntimeError as exc:  # quota / rate limit: keep the previous cache instead of failing the whole run
        logger.warning("%s — keeping the previous BettingPros cache", exc)
