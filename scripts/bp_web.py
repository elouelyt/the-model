#!/usr/bin/env python3
"""Read the BettingPros WEBSITE (one page per player) through the debug Chrome and save every book's over/under line, plus BettingPros'
own Consensus column, in the same row format as the other reference-book caches.

Why: the user's BettingPros API key is capped (50 requests/day, 20 offers per page) but the public player pages show ALL books and the
Consensus for every market of a player. This reads what the page renders, like a person would: it does not call the API and uses no key.
Only players that have candidate legs in the current picks file are visited (fair prob >= 52 % and EV > 0), and only until the wanted markets
show up (the page loads 5 markets at a time). A new tab is opened for the job and closed afterwards; the Stake tab is not touched.

    python scripts/bp_web.py nfl [--max N]     # -> nfl/data/nfl_bettingpros_cache.json
    python scripts/bp_web.py nba [--max N]     # -> data/nba_bettingpros_web_cache.json   (read by nba_ev next to the API cache)
Rows: {book, fixture, player, stat, line, over_american, under_american}; book 'Consensus' is BettingPros' average of all its books.
Reference books kept: DraftKings, FanDuel, BetMGM, Caesars, Hard Rock, theScore Bet, Fanatics, Novig, ProphetX (no DFS apps, no prediction markets).
"""

import json
import logging
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
import websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
EXTRACT_JS = (Path(__file__).resolve().parent / "bp_web_extract.js").read_text(encoding="utf-8")
BOOKS_KEPT = {"DraftKings": "DraftKings", "FanDuel": "FanDuel", "BetMGM": "BetMGM", "Caesars": "Caesars", "Hard Rock": "HardRock",
              "theScore Bet": "theScore", "Fanatics": "Fanatics", "Novig": "Novig", "ProphetX": "ProphetX"}
MIN_PROB, MIN_EV = 0.52, 0.0

SPORTS = {
    "nfl": {
        "url": "https://www.bettingpros.com/nfl/odds/player-props/{slug}/",
        # lowercase market label on the page -> Stake stat name
        "labels": {"passing yards over": "passing yards", "passing attempts over": "passing attempts", "pass attempts over": "passing attempts",
                   "passing completions over": "passing completions", "pass completions over": "passing completions",
                   "passing touchdowns over": "passing touchdowns", "interceptions over": "interceptions",
                   "rushing yards over": "rushing yards", "rushing attempts over": "rushing attempts",
                   "receiving yards over": "receiving yards", "receptions over": "receptions"},
        "picks": ROOT / "nfl" / "data" / "nfl_picks.json", "out": ROOT / "nfl" / "data" / "nfl_bettingpros_cache.json",
    },
    "nba": {
        "url": "https://www.bettingpros.com/nba/odds/player-props/{slug}/",
        # the FIRST prefix of each stat is the label BettingPros really shows (used to know when to stop scrolling)
        "labels": {"points over": "points", "rebounds over": "rebounds", "assists over": "assists",
                   "points + assists + rebounds over": "points+assists+rebounds", "points + rebounds + assists over": "points+assists+rebounds",
                   "points + rebounds over": "points+rebounds", "points + assists over": "points+assists",
                   "rebounds + assists over": "assists+rebounds", "assists + rebounds over": "assists+rebounds"},
        "picks": ROOT / "data" / "nba_picks.json", "out": ROOT / "data" / "nba_bettingpros_web_cache.json",
    },
}


class Tab:
    """A throw-away Chrome tab driven over CDP."""

    def __init__(self) -> None:
        info = requests.put("http://localhost:9222/json/new?about:blank", timeout=10).json()
        self.id = info["id"]
        self.ws = websocket.create_connection(info["webSocketDebuggerUrl"], timeout=120)
        self._n = 0
        self.call("Page.bringToFront")
        self.call("Emulation.setFocusEmulationEnabled", {"enabled": True})   # a hidden Chrome does not render / lazy-load otherwise

    def call(self, method: str, params: dict | None = None) -> dict:
        self._n += 1
        self.ws.send(json.dumps({"id": self._n, "method": method, "params": params or {}}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self._n:
                return r

    def eval(self, js: str):
        r = self.call("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
        return r["result"]["result"].get("value")

    def close(self) -> None:
        try:
            self.ws.close()
            requests.get(f"http://localhost:9222/json/close/{self.id}", timeout=10)
        except Exception:  # noqa: BLE001
            pass


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace(".", " ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def targets(sport: str) -> dict[str, dict]:
    """player -> {'fixture': ..., 'stats': {stat, ...}} for legs worth a second opinion."""
    doc = json.loads(SPORTS[sport]["picks"].read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for p in doc.get("picks", []) + doc.get("high_prob", []):
        if p["fair_prob"] >= MIN_PROB and p["ev"] > MIN_EV:
            t = out.setdefault(p["player"], {"fixture": p.get("fixture"), "stats": set(), "p": 0.0})
            t["stats"].add(p["stat"])
            t["p"] = max(t["p"], p["fair_prob"])
    return {k: v for k, v in out.items() if v["fixture"]}


def rows_from_page(page: dict, player: str, fixture: str, labels: dict) -> list[dict]:
    books = page["books"]
    out = []
    for r in page["rows"]:
        label = r["label"].lower()
        stat = next((s for prefix, s in labels.items() if label.startswith(prefix)), None)
        if not stat:
            continue
        for idx, cell in enumerate(r["cells"]):
            if not cell or cell["over"] is None or cell["under"] is None or cell["line"] != cell["under_line"]:
                continue
            if idx == 2:
                book = "Consensus"                       # OPEN / BEST ODDS / CONSENSUS come first, then the books in header order
            elif idx >= 3 and idx - 3 < len(books) and books[idx - 3] in BOOKS_KEPT:
                book = BOOKS_KEPT[books[idx - 3]]
            else:
                continue
            out.append({"book": book, "fixture": fixture, "player": player, "stat": stat, "line": float(cell["line"]),
                        "over_american": int(cell["over"]), "under_american": int(cell["under"])})
    return out


def main(sport: str, limit: int | None = None) -> None:
    cfg = SPORTS[sport]
    want = targets(sport)
    order = sorted(want.items(), key=lambda kv: -kv[1]["p"])[:limit]
    logger.info("%s: %d players with candidate legs", sport.upper(), len(order))
    stat_to_prefixes: dict[str, list[str]] = {}
    for prefix, stat in cfg["labels"].items():
        stat_to_prefixes.setdefault(stat, []).append(prefix)
    tab = Tab()
    rows: list[dict] = []
    ok = miss = 0
    try:
        for player, info in order:
            needed = sorted({stat_to_prefixes[s][0] for s in info["stats"] if s in stat_to_prefixes})
            if not needed:
                continue
            tab.call("Page.navigate", {"url": cfg["url"].format(slug=slugify(player))})
            time.sleep(5)
            try:
                page = json.loads(tab.eval(f"({EXTRACT_JS})({json.dumps(needed)})"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s: failed (%s)", player, str(exc)[:60])
                miss += 1
                continue
            got = rows_from_page(page, player, info["fixture"], cfg["labels"])
            rows += got
            ok += bool(got)
            miss += not got
            logger.info("%-24s %2d lines, %d books", player, len(got), len({r['book'] for r in got}))
    finally:
        tab.close()
    cfg["out"].write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "source": "BettingPros website (player pages, no API)",
                                      "rows": rows}, ensure_ascii=False), encoding="utf-8")
    by_book: dict[str, int] = {}
    for r in rows:
        by_book[r["book"]] = by_book.get(r["book"], 0) + 1
    logger.info("Saved %d lines (%d players ok, %d without data) to %s %s", len(rows), ok, miss, cfg["out"], by_book)


if __name__ == "__main__":
    args = sys.argv[1:]
    lim = int(args[args.index("--max") + 1]) if "--max" in args else None
    main(args[0] if args and not args[0].startswith("--") else "nfl", lim)
