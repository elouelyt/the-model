#!/usr/bin/env python3
"""MMA tracking: our model's picks against the picks of Jev (TypeSafe), fight by fight, settled with ESPN.

Every run (called from jev/../scripts/mix_publish.update(), or alone: python mma/mma_track.py [--no-jev]):
  1. fights + Stake/bookmaker h2h odds from The-Odds-API (cached 12 h so the monthly quota is not burnt), enriched with our model
     (generate_html._enrich_mma_fights: prob, edge, signal);
  2. OUR pick per fight = the model's best side when its signal is `value_bet` (bettable) or `marginal` (tracking); frozen once chosen;
  3. JEV's pick per fight: `noul` (P that fighter 1 wins) + `choice` (fighter 1 / fighter 2 / no bet), frozen once chosen. It receives
     the same data as the model (stats, ranking, Elo, our probability, the odds) and decides on its own;
  4. settle every fight with the ESPN scoreboards (UFC, PFL, Bellator, LFA, Cage Warriors) and write data/mma_analysis.json:
     profit at 1 u per bet, hit rate, Brier of ours / Jev / market on the same fights.
Snapshots live in data/mma_history/<fight day>.json (local; the publish step encrypts a bundle).
"""

import json
import logging
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "jev"))
import jev_client  # noqa: E402

logger = logging.getLogger(__name__)
HISTORY = ROOT / "data" / "mma_history"
ANALYSIS = ROOT / "data" / "mma_analysis.json"
ODDS_CACHE = ROOT / "data" / "mma_odds_cache.json"
ODDS_TTL_H = 12
HORIZON_DAYS = 8   # odds and cards change: only fights starting within a week are recorded (picks freeze once chosen)
LEAGUES = ("ufc", "pfl", "bellator", "lfa", "cage-warriors")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/mma/{}/scoreboard"

GOAL = ("Tu objetivo es maximizar el beneficio esperado a largo plazo apostando 1 unidad por pelea a la cuota indicada. "
        "Solo se apuesta si de verdad ves ventaja sobre la cuota; si no la ves, elige no apostar.")


def norm(n: str) -> str:
    s = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]+", " ", s).strip()


def same_person(a: str, b: str) -> bool:
    a, b = norm(a).split(), norm(b).split()
    if not a or not b:
        return False
    if a == b:
        return True
    return a[-1] == b[-1] and a[0][0] == b[0][0]


def fight_key(f1: str, f2: str, day: str) -> str:
    return "|".join(sorted((norm(f1), norm(f2)))) + "|" + day


# ── 1. fights and our model ───────────────────────────────────────────────────

def load_fights() -> list[dict]:
    """Upcoming fights enriched with the model (cached 12 h: the odds API quota is monthly)."""
    if ODDS_CACHE.exists():
        c = json.loads(ODDS_CACHE.read_text(encoding="utf-8"))
        if datetime.now(timezone.utc) - datetime.fromisoformat(c["at"]) < timedelta(hours=ODDS_TTL_H):
            return c["fights"]
    import generate_html as gh
    from src.agents.mma_odds_agent import fetch_mma_odds
    from src.agents.mma_stats_agent import fetch_fighter_stats
    from src.agents.mma_ranking_agent import fetch_ufc_rankings
    from src.agents.mma_model_agent import predict_fight, compute_edge
    from src.agents.mma_elo_agent import predict_elo
    raw = fetch_mma_odds()
    if not raw:
        return json.loads(ODDS_CACHE.read_text(encoding="utf-8"))["fights"] if ODDS_CACHE.exists() else []
    enriched = gh._enrich_mma_fights(raw, fetch_fighter_stats, fetch_ufc_rankings, predict_fight, compute_edge, predict_elo)
    keep = ("fighter1", "fighter2", "odds1", "odds2", "commence_time", "event", "bookmaker", "stats1", "stats2", "rank1", "rank2",
            "division1", "division2", "prob1", "prob2", "edge1", "edge2", "best_fighter", "best_odds", "best_prob", "best_edge",
            "signal", "model_used")
    fights = [{k: f.get(k) for k in keep} for f in enriched]
    ODDS_CACHE.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "fights": fights}, ensure_ascii=False, default=str),
                          encoding="utf-8")
    return fights


def load_day(day: str) -> dict:
    p = HISTORY / f"{day}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"date": day, "fights": {}}


def save_day(doc: dict) -> None:
    HISTORY.mkdir(parents=True, exist_ok=True)
    (HISTORY / f"{doc['date']}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def record_ours(rec: dict, f: dict, now: str) -> None:
    """Freeze the model's pick: value_bet = bettable, marginal = tracking; a marginal pick is upgraded if it later becomes a value bet."""
    rec["ours"] = {"prob1": f["prob1"], "prob2": f["prob2"], "signal": f["signal"], "model_used": bool(f["model_used"]),
                   "edge1": f["edge1"], "edge2": f["edge2"], "pick": rec.get("ours", {}).get("pick")}
    pick = rec["ours"]["pick"]
    if f["signal"] in ("value_bet", "marginal") and f["model_used"] and (pick is None or (pick["kind"] == "marginal" and f["signal"] == "value_bet")):
        rec["ours"]["pick"] = {"fighter": f["best_fighter"], "odds": f["best_odds"], "prob": f["best_prob"], "edge": f["best_edge"],
                               "kind": "value" if f["signal"] == "value_bet" else "marginal", "at": now}


# ── 3. Jev ─────────────────────────────────────────────────────────────────────

def knowledge() -> str:
    try:
        w = json.loads((ROOT / "data" / "ufc_elo_walkforward_results.json").read_text(encoding="utf-8"))
        cal = "; ".join(f"modelo dice {k} %: ganó {v['actual_win_rate']:.0%} (n={v['n']})" for k, v in w["calibration"].items())
        hist = (f"Backtest histórico de nuestro modelo (walk-forward, {w['n_fights_scored']} peleas): acierto {w['walkforward_accuracy']:.1%}, "
                f"Brier {w['brier_score']}. Calibración: {cal}.")
    except (OSError, ValueError, KeyError):
        hist = "Sin backtest disponible."
    return ("=== CONTEXTO MMA ===\nVas a valorar peleas de MMA (UFC y otras ligas) con la cuota de una casa. Nuestro modelo propio mezcla un Elo, "
            "estadísticas de golpeo/derribos (precisión y defensa), alcance, edad, tasa de finalización y forma reciente. " + hist +
            " Nuestro modelo tiene poca fiabilidad con cuotas largas (>3,5) y en peleas con pocos datos reales; úsalo como una pista más, no como verdad.")


def fighter_line(name: str, stats: dict, rank, division: str, opp_odds: float) -> str:
    bits = [f"{k}={v}" for k, v in (stats or {}).items() if v is not None and not isinstance(v, (dict, list))]
    r = f"ranking {rank} en {division}" if rank else "sin ranking"
    return f"{name} ({r}; " + (", ".join(bits) if bits else "sin estadísticas") + ")"


def describe(f: dict) -> str:
    return (f"{f['event']} · {f['commence_time']} · casa {f['bookmaker']}\n"
            f"F1: {fighter_line(f['fighter1'], f['stats1'], f['rank1'], f['division1'], f['odds2'])} cuota {f['odds1']}\n"
            f"F2: {fighter_line(f['fighter2'], f['stats2'], f['rank2'], f['division2'], f['odds1'])} cuota {f['odds2']}\n"
            f"Nuestro modelo: P(F1)={f['prob1']:.2f} P(F2)={f['prob2']:.2f} señal={f['signal']}")


def record_jev(rec: dict, f: dict, now: str) -> None:
    if rec.get("jev"):                         # frozen: one evaluation per fight
        return
    state = knowledge() + "\n\n=== PELEA ===\n" + describe(f)
    options = {"F1": f"Apostar a {f['fighter1']} a cuota {f['odds1']}", "F2": f"Apostar a {f['fighter2']} a cuota {f['odds2']}",
               "NO": "No apostar en esta pelea"}
    res = jev_client.ask(state, {
        "gana1": {"type": "noul", "instructions": f"¿Ganará {f['fighter1']} (F1) esta pelea? Da la probabilidad real, no copies la cuota."},
        "eleccion": {"type": "choice", "instructions": f"{GOAL} ¿Qué haces en esta pelea?", "criteria": options}})["answers"]
    p1 = round(float(res["gana1"]["noul"]), 4)
    choice = res["eleccion"]["choice"]
    pick = None
    if choice in ("F1", "F2"):
        side = 1 if choice == "F1" else 2
        odds = f["odds1"] if side == 1 else f["odds2"]
        prob = p1 if side == 1 else round(1 - p1, 4)
        pick = {"fighter": f["fighter1"] if side == 1 else f["fighter2"], "odds": odds, "prob": prob, "edge": round(prob - 1 / odds, 4), "at": now}
    rec["jev"] = {"prob1": p1, "pick": pick}


# ── 4. settlement ──────────────────────────────────────────────────────────────

_board: dict[tuple, list] = {}


def scoreboard(league: str, day: str) -> list[dict]:
    if (league, day) not in _board:
        try:
            r = requests.get(ESPN.format(league), params={"dates": day.replace("-", "")}, timeout=30)
            events = r.json().get("events", []) if r.ok else []
        except (requests.RequestException, ValueError):
            events = []
        _board[(league, day)] = [c for e in events for c in e.get("competitions", [])]
    return _board[(league, day)]


def settle_fight(rec: dict, day: str) -> bool:
    """Look the fight up on the ESPN boards of that day (and the one before: UTC vs local date); return True when a result was stored."""
    d0 = datetime.fromisoformat(day)
    for off in (0, -1, 1):
        d = (d0 + timedelta(days=off)).strftime("%Y-%m-%d")
        for league in LEAGUES:
            for c in scoreboard(league, d):
                names = [x["athlete"]["displayName"] for x in c["competitors"]]
                if len(names) != 2:
                    continue
                if (same_person(names[0], rec["fighter1"]) and same_person(names[1], rec["fighter2"])) or \
                   (same_person(names[0], rec["fighter2"]) and same_person(names[1], rec["fighter1"])):
                    if not c["status"]["type"].get("completed"):
                        return False
                    winners = [x["athlete"]["displayName"] for x in c["competitors"] if x.get("winner")]
                    rec["result"] = {"winner": (rec["fighter1"] if winners and same_person(winners[0], rec["fighter1"])
                                                else rec["fighter2"] if winners else "void")}
                    return True
    return False


def settle_all(days: list[str]) -> None:
    now = datetime.now(timezone.utc)
    for day in days:
        doc = load_day(day)
        changed = False
        for rec in doc["fights"].values():
            if "result" in rec or datetime.fromisoformat(rec["commence_time"].replace("Z", "+00:00")) + timedelta(hours=2) > now:
                continue
            changed |= settle_fight(rec, day)
        if changed:
            save_day(doc)


# ── analysis ───────────────────────────────────────────────────────────────────

def bet_stats(bets: list[tuple]) -> dict:
    """bets = [(odds, won)] at 1 u each."""
    n, won = len(bets), sum(1 for _, w in bets if w)
    profit = round(sum(o - 1 if w else -1 for o, w in bets), 2)
    return {"n": n, "won": won, "profit": profit, "roi": round(profit / n, 3) if n else None}


def analyse() -> dict:
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(HISTORY.glob("*.json"))]
    sides = {"ours_value": [], "ours_all": [], "jev": []}
    days: dict[str, dict] = {}
    brier = {"ours": [], "jev": [], "market": []}
    rows = []
    for doc in docs:
        for rec in doc["fights"].values():
            res = rec.get("result")
            winner = res["winner"] if res else None
            settled = bool(res) and winner != "void"
            ours, jev = rec.get("ours") or {}, rec.get("jev") or {}
            row = {"date": doc["date"], "event": rec["event"], "fighter1": rec["fighter1"], "fighter2": rec["fighter2"],
                   "odds1": rec["odds1"], "odds2": rec["odds2"], "commence_time": rec["commence_time"],
                   "ours": {"prob1": ours.get("prob1"), "pick": ours.get("pick"), "signal": ours.get("signal")},
                   "jev": {"prob1": jev.get("prob1"), "pick": jev.get("pick")}, "winner": winner}
            rows.append(row)
            if not settled:
                continue
            y = 1.0 if same_person(winner, rec["fighter1"]) else 0.0
            if ours.get("model_used"):
                brier["ours"].append((ours["prob1"] - y) ** 2)
            if jev.get("prob1") is not None:
                brier["jev"].append((jev["prob1"] - y) ** 2)
            imp1, imp2 = 1 / rec["odds1"], 1 / rec["odds2"]
            brier["market"].append((imp1 / (imp1 + imp2) - y) ** 2)
            d = days.setdefault(doc["date"], {"ours": [], "jev": []})
            for key, pick in (("ours", ours.get("pick")), ("jev", jev.get("pick"))):
                if pick:
                    won = same_person(pick["fighter"], winner)
                    d[key].append((pick["odds"], won))
                    if key == "jev":
                        sides["jev"].append((pick["odds"], won))
                    else:
                        sides["ours_all"].append((pick["odds"], won))
                        if pick["kind"] == "value":
                            sides["ours_value"].append((pick["odds"], won))
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
    return {"updated": datetime.now(timezone.utc).isoformat(),
            "comparison": {"jev": bet_stats(sides["jev"]), "ours_value": bet_stats(sides["ours_value"]), "ours_all": bet_stats(sides["ours_all"]),
                           "days": [{"date": k, "jev": bet_stats(v["jev"]), "ours": bet_stats(v["ours"])} for k, v in sorted(days.items())]},
            "brier": {"n": len(brier["market"]), "ours": mean(brier["ours"]), "jev": mean(brier["jev"]), "market": mean(brier["market"]),
                      "n_ours": len(brier["ours"]), "n_jev": len(brier["jev"])},
            "fights": rows}


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    use_jev = "--no-jev" not in sys.argv
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    docs: dict[str, dict] = {}
    for f in load_fights():
        ct = datetime.fromisoformat(f["commence_time"].replace("Z", "+00:00"))
        if ct <= now_dt or ct > now_dt + timedelta(days=HORIZON_DAYS):
            continue                               # never record a pick once the fight has started, nor weeks ahead
        day = ct.strftime("%Y-%m-%d")
        doc = docs.setdefault(day, load_day(day))
        key = fight_key(f["fighter1"], f["fighter2"], day)
        rec = doc["fights"].setdefault(key, {"fighter1": f["fighter1"], "fighter2": f["fighter2"], "event": f["event"],
                                             "commence_time": f["commence_time"], "bookmaker": f["bookmaker"], "first_seen": now})
        rec.update(odds1=f["odds1"], odds2=f["odds2"], bookmaker=f["bookmaker"])
        record_ours(rec, f, now)
        if use_jev:
            try:
                record_jev(rec, f, now)
            except RuntimeError as exc:
                logger.warning("Jev skipped %s vs %s: %s", f["fighter1"], f["fighter2"], exc)
    for doc in docs.values():
        save_day(doc)
    settle_all(sorted(p.stem for p in HISTORY.glob("*.json")))
    a = analyse()
    ANALYSIS.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    c = a["comparison"]
    logger.info("MMA: %d fights tracked; Jev %s; ours(value) %s; brier %s", len(a["fights"]), c["jev"], c["ours_value"], a["brier"])


if __name__ == "__main__":
    main()
