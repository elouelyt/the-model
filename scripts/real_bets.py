#!/usr/bin/env python3
"""Settle the bets the Stake Bet Guide extension recorded (private repo elouelyt/the-model-bets) with ESPN box scores.

    python scripts/real_bets.py          # pull the repo, settle every bet it can, write nuevas_ideas/data/real_bets.json

Each record is one bet Stake confirmed (see nuevas_ideas/stake-guide-registro/bets.js): legs as Stake shows them (Spanish market names),
the real odds and the real amount. A leg whose player did not play is void and is removed from the combo (odds recalculated), like Stake.
Profit is in units: 1 u per bet (odds - 1 if it wins, -1 if it loses), the same convention as the rest of the Resultados tab.
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "nfl"))

import nba_settle  # noqa: E402
import nfl_settle  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/elouelyt/the-model-bets.git"
CLONE = Path.home() / "the-model-bets"
OUT = ROOT / "nuevas_ideas" / "data" / "real_bets.json"
MADRID = ZoneInfo("Europe/Madrid")

STAT_KEYS = {
    "puntos": "points", "rebotes": "rebounds", "asistencias": "assists", "puntos + rebotes": "points+rebounds",
    "puntos + asistencias": "points+assists", "asistencias + rebotes": "assists+rebounds",
    "puntos + asistencias + rebotes": "points+assists+rebounds",
    "yardas por pases": "passing yards", "intentos de pases": "passing attempts", "pases completados": "passing completions",
    "pases de touchdowns": "passing touchdowns", "intercepciones": "interceptions", "yardas por acarreo": "rushing yards",
    "intentos de acarreo": "rushing attempts", "yardas de recepción": "receiving yards", "recepciones": "receptions",
}
NFL_STATS = {"passing yards", "passing attempts", "passing completions", "passing touchdowns", "interceptions", "rushing yards",
             "rushing attempts", "receiving yards", "receptions"}


def sync() -> bool:
    """Clone or pull the private repo. False when it is not reachable (the cached copy, if any, is used)."""
    try:
        if (CLONE / ".git").exists():
            subprocess.run(["git", "-C", str(CLONE), "pull", "--ff-only", "-q"], check=True, timeout=120)
        else:
            subprocess.run(["git", "clone", "-q", REPO_URL, str(CLONE)], check=True, timeout=120)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not sync %s: %s", REPO_URL, str(exc)[:100])
        return False


def stat_key(es: str) -> str | None:
    return STAT_KEYS.get(" ".join(es.lower().split()))


def find_event(espn, teams: list[str], placed: datetime):
    for delta in (0, 1, 2, 3, -1):
        want = frozenset(nba_settle.nick(t) for t in teams)
        for ev in espn.events((placed + timedelta(days=delta)).strftime("%Y%m%d")):
            names = frozenset(nba_settle.nick(c["team"]["displayName"]) for c in ev["competitions"][0]["competitors"])
            if names == want:
                return ev
    return None


def settle_bet(bet: dict, nba, nfl) -> dict:
    placed = datetime.fromisoformat(bet["placed_at"].replace("Z", "+00:00"))
    legs, pending, unknown = [], False, False
    for leg in bet["legs"]:
        key = stat_key(leg["stat"])
        row = {"player": leg["player"], "stat": leg["stat"], "side": leg["side"], "line": leg["line"], "odds": leg.get("odds"), "status": "pending"}
        if key is None:
            unknown = True
            row["status"] = "unknown"
        else:
            is_nfl = key in NFL_STATS
            espn, mod = (nfl, nfl_settle) if is_nfl else (nba, nba_settle)
            ev = find_event(espn, leg["game"].split(" - "), placed)
            box = espn.box(ev["id"]) if ev else None
            if box:
                res = mod.settle_leg({"player": leg["player"], "stat": key, "side": leg["side"], "line": leg["line"]}, box)
                row.update(status=res["status"], actual=res["actual"])
            else:
                pending = True
        legs.append(row)
    live = [l for l in legs if l["status"] != "void"]
    odds = bet["odds"] or 1.0
    for l in legs:
        if l["status"] == "void" and l["odds"]:
            odds = odds / l["odds"]
    if unknown:
        status = "unknown"
    elif pending and not any(l["status"] == "lost" for l in legs):
        status = "pending"
    elif any(l["status"] == "lost" for l in legs):
        status = "lost"
    elif not live:
        status = "void"
    else:
        status = "won"
    profit = {"won": odds - 1, "lost": -1.0, "void": 0.0}.get(status)
    return {"id": bet["id"], "placed_at": bet["placed_at"], "day": placed.astimezone(MADRID).strftime("%Y-%m-%d"), "kind": bet["kind"],
            "stake_odds": bet["odds"], "odds": round(odds, 2), "amount": bet.get("amount"), "currency": bet.get("currency"),
            "status": status, "profit_u": None if profit is None else round(profit, 2), "legs": legs}


def main() -> list[dict]:
    sync()
    files = sorted((CLONE / "bets").rglob("*.json")) if (CLONE / "bets").exists() else []
    old = {b["id"]: b for b in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() else {}
    nba, nfl = nba_settle.Espn(), nfl_settle.Espn()
    out = []
    seen: list[tuple[str, datetime]] = []       # the extension can record one bet twice (click + receipt): same legs and amount within 3 min
    for f in files:
        bet = json.loads(f.read_text(encoding="utf-8"))
        sig = "|".join(sorted(f'{l["player"]}{l["stat"]}{l["side"]}{l["line"]}' for l in bet["legs"])) + f'|{bet.get("amount")}'
        when = datetime.fromisoformat(bet["placed_at"].replace("Z", "+00:00"))
        if any(s == sig and abs((when - t).total_seconds()) < 180 for s, t in seen):
            continue
        seen.append((sig, when))
        prev = old.get(bet["id"])
        if prev and prev["status"] in ("won", "lost", "void"):
            out.append(prev)
            continue
        out.append(settle_bet(bet, nba, nfl))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    done = sum(b["status"] in ("won", "lost", "void") for b in out)
    logger.info("%d bets recorded, %d settled, %d pending/unknown", len(out), done, len(out) - done)
    return out


if __name__ == "__main__":
    main()
