"""Shared helpers for the 'nuevas_ideas' paper tests.

Nothing here changes the production pipeline: it only READS data/nba_picks.json, data/nba_stake_cache.json and the
reference-book caches, and writes under nuevas_ideas/ideas/<idea>/history/<date>.json (same schema as
data/nba_history, so the existing ESPN settlement code can settle it).
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

SPORT = os.environ.get("IDEAS_SPORT", "nba")   # 'nba' (default) or 'nfl': the same paper ideas run on either sport
PICKS = ROOT / "data" / "nba_picks.json" if SPORT == "nba" else ROOT / "nfl" / "data" / "nfl_picks.json"
STAKE_CACHE = ROOT / "data" / "nba_stake_cache.json" if SPORT == "nba" else ROOT / "nfl" / "data" / "nfl_stake_cache.json"
HIST_DIR = "history" if SPORT == "nba" else "history_nfl"
MIN_BOOKS = 2 if SPORT == "nba" else 1          # NFL has one reference book (Pinnacle) for now


def day_key() -> str:
    """Slate date: runs after midnight still belong to the evening before (same rule as nba_combos)."""
    return (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")


def leg_key(p: dict) -> str:
    return f'{p["start"][:16]}|{p["player"]}|{p["stat"]}|{p["side"]}|{p["line"]}'


def combo_id(c: dict) -> tuple:
    return tuple(sorted(l["key"] for l in c["legs"]))


def history_path(idea: str, day: str | None = None) -> Path:
    d = BASE / "ideas" / idea / HIST_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{day or day_key()}.json"


def save_combos(idea: str, combos: list[dict]) -> int:
    """Append only the combos not seen today for this idea (first sighting wins, like the production snapshot)."""
    path = history_path(idea)
    snap = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"date": day_key(), "runs": []}
    known = {combo_id(c) for r in snap["runs"] for c in r["combos"]}
    new = [c for c in combos if combo_id(c) not in known]
    snap["runs"].append({"at": datetime.now(timezone.utc).isoformat(), "picks": [], "combos": new})
    path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return len(new)


def load_picks_doc() -> dict:
    return json.loads(PICKS.read_text(encoding="utf-8"))


def combo_from_legs(legs: list[dict], families: list[str], odds: float, prob: float, extra: dict | None = None) -> dict:
    """Paper combo in the production schema. `odds` is the price the idea would have been paid."""
    out = {
        "legs": [{"key": leg_key(l), "player": l["player"], "stat": l["stat"], "side": l["side"], "line": l["line"],
                  "stake_odds": l["stake_odds"], "fair_prob": l["fair_prob"], "ev": l.get("ev"),
                  "game": l["game"], "start": l["start"], "fixture": l.get("fixture")} for l in legs],
        "families": families, "odds": round(odds, 3), "prob": round(prob, 4), "ev": round(prob * odds - 1, 4),
        "units": 0.25, "tracking": True,
    }
    out.update(extra or {})
    return out


# --- Stake page access (the debug Chrome on port 9222, no login needed for prices) -----------------------------------

class StakePage:
    """Runs long async JavaScript inside a stake.com tab and polls for the result (no websocket timeouts)."""

    def __init__(self) -> None:
        import websocket
        tabs = [t for t in requests.get("http://localhost:9222/json", timeout=10).json() if t["type"] == "page"]
        tab = next((t for t in tabs if "stake.com" in t["url"]), None)
        if tab is None:
            raise SystemExit("No stake.com tab in the debug Chrome (run scripts/start_chrome_debug.bat)")
        self.ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=60)
        self._id = 0
        self.call("Page.bringToFront")
        self.call("Emulation.setFocusEmulationEnabled", {"enabled": True})
        if "stake.com" not in (self.eval("location.origin") or ""):
            self.call("Page.navigate", {"url": "https://stake.com/es/sports/basketball"})
            time.sleep(8)

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self._id:
                return r

    def eval(self, js: str, await_promise: bool = True):
        r = self.call("Runtime.evaluate", {"expression": js, "awaitPromise": await_promise, "returnByValue": True})
        return r["result"]["result"].get("value")

    def sgm_prices(self, queries: list[list[list[str]]], pause_ms: int = 110, timeout: int = 900) -> list[dict | None]:
        """queries: [[ [outcomeId, 'over'|'under'], ... ], ...] -> [{odds, invalid}] using the site's own price query."""
        js = r"""
        (async (queries, pause) => {
          const Q = `query C($lines: [CalculateSwishCustomBetLinesInput!]!) { calculateSwishCustomBet(lines: $lines) { invalidCombinations odds } }`;
          const out = {r: [], done: false}; window.__sgm = out;
          for (const q of queries) {
            try {
              const res = await fetch('/_api/v1/graphql', {method: 'POST', headers: {'content-type': 'application/json'},
                body: JSON.stringify({query: Q, variables: {lines: q.map(l => ({outcomeId: l[0], lineType: l[1]}))}})});
              const j = await res.json();
              const d = j.data && j.data.calculateSwishCustomBet;
              out.r.push(d ? {odds: d.odds, invalid: (d.invalidCombinations || []).length > 0} : null);
            } catch (e) { out.r.push(null); }
            await new Promise(r => setTimeout(r, pause));
          }
          out.done = true; return 1;
        })"""
        self.call("Runtime.evaluate", {"expression": f"({js})({json.dumps(queries)},{pause_ms})", "awaitPromise": False})
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(5)
            st = self.eval("window.__sgm ? [window.__sgm.r.length, window.__sgm.done] : null")
            if st and st[1]:
                break
        return self.eval("window.__sgm.r")


def eligible_legs(picks: list[dict], min_prob: float = 0.54, min_ev: float = 0.005, min_books: int | None = None) -> list[dict]:
    """Legs under the production rules (win >= min_prob, EV > min_ev, >= 2 books) for games that have not started."""
    from email.utils import parsedate_to_datetime
    min_books = MIN_BOOKS if min_books is None else min_books
    limit = datetime.now(timezone.utc) + timedelta(minutes=10)
    return [p for p in picks if p["fair_prob"] >= min_prob and p["ev"] >= min_ev and p.get("books", 1) >= min_books
            and parsedate_to_datetime(p["start"]) > limit]


import nba_combos as _nc  # noqa: E402  (same module object the ideas import: the NFL run relaxes its books rule)
_nc.MIN_LEG_BOOKS = MIN_BOOKS
