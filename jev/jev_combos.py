#!/usr/bin/env python3
"""Jev's own combos (NBA, NFL and NBA+NFL), built next to - never instead of - the ones from our rules, to compare them every day.

Jev (TypeSafe) answers yes/no questions with a probability. So it plays the role of an independent evaluator of every candidate leg:
  1. state = everything we know (settled-results tables for NBA / NFL / mixed, the lessons learned, the open candidate legs with
     Stake odds, the books' fair probability and the line prices of each book);
  2. one `noul` question per leg: "will this leg hit?"  -> Jev's probability;
  3. the same combo engine (scripts/nba_combos.py, 3 legs, different games and players) is run on Jev's probabilities.
Legs keep our probability as `our_prob` so the settlement can also tell who was better calibrated (Brier).
Output: data/jev_picks.json = {timestamp, nba, nfl, total, ...}; the daily snapshot goes to data/jev_history/<date>.json (settled by jev/jev_settle.py).
    python jev/jev_combos.py [--no-snapshot]
"""

import hashlib
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "jev"))
import jev_client  # noqa: E402
import nba_combos as nc  # noqa: E402

logger = logging.getLogger(__name__)
NBA_PICKS = ROOT / "data" / "nba_picks.json"
NFL_PICKS = ROOT / "nfl" / "data" / "nfl_picks.json"
ANALYSES = {"NBA": ROOT / "data" / "nba_analysis.json", "NFL": ROOT / "nfl" / "data" / "nfl_analysis.json",
            "Mezcla": ROOT / "data" / "mix_analysis.json"}
HISTORY = ROOT / "data" / "jev_history"
CACHE = ROOT / "data" / "jev_cache.json"
OUT = ROOT / "data" / "jev_picks.json"
MAX_LEGS = 160          # candidate legs sent per run (best by our fair probability); keeps the state well below the context limit
SCOPES = ("nba", "nfl", "total")

LESSONS = """LECCIONES APRENDIDAS (de 2 semanas de resultados reales):
- La probabilidad justa de las casas de referencia (sin margen) calibra bien en las piernas con 54 % o más; el EV por sí solo NO predijo el acierto.
- Las jugadas con EV muy alto y probabilidad baja (sobre todo Under) fallaron más de lo esperado.
- En NBA las palizas (margen final de 18 o más) quitan minutos a los titulares: los Over de jugadores clave sufren en partidos desiguales; los Under ganan.
- Una combinada de 3 piernas acierta de media muy por debajo de lo que sugiere el producto de probabilidades si las piernas están correlacionadas: piernas de partidos y jugadores distintos.
- Si el jugador no juega, la pierna se anula (no pierde).
- NFL solo tiene Pinnacle como casa de referencia (1 casa); NBA tiene hasta 10.
- Una cuota de Stake con margen: EV = probabilidad × cuota − 1. Solo interesa si la probabilidad real supera 1/cuota."""


def table(rows: list[dict], title: str, cols: tuple = ("name", "n", "hit", "expected", "roi")) -> str:
    if not rows:
        return ""
    lines = [title, " | ".join(cols)]
    lines += [" | ".join(str(r.get(c, "")) for c in cols) for r in rows]
    return "\n".join(lines)


def knowledge() -> str:
    """Everything the settlement scripts know so far, as compact text tables."""
    parts = [LESSONS]
    for name, path in ANALYSES.items():
        if not path.exists():
            continue
        a = json.loads(path.read_text(encoding="utf-8"))
        parts.append(f"=== RESULTADOS LIQUIDADOS {name}: {a['legs_settled']} piernas, {a['combos_settled']} combinadas ===")
        parts.append("(hit = acierto real, expected = probabilidad justa media que dábamos, roi = beneficio medio por 1 unidad a cuota de Stake)")
        parts.append(table(a.get("calibration", []), "Calibración por probabilidad justa:"))
        parts.append(table(a.get("by_stat", []), "Por mercado:"))
        parts.append(table(a.get("by_side", []), "Por lado:"))
        parts.append(table(a.get("by_ev", []), "Por tramo de EV:"))
        parts.append(table(a.get("by_books", []), "Por número de casas:"))
        parts.append(table(a.get("combo_families", []), "Familias de combinadas:", ("name", "n", "hits", "expected_hit", "roi")))
        ctx = a.get("context")
        if ctx:
            parts.append(f"Palizas (margen >= {ctx['blowout_threshold']}): Over {ctx['over_blowout']} / Under {ctx['under_blowout']} acierto "
                         f"(n={ctx['n_blowout']}); partidos igualados: Over {ctx['over_close']} / Under {ctx['under_close']} (n={ctx['n_close']}).")
        legs = a.get("legs", [])
        grp: dict[tuple, list] = {}
        for l in legs:
            grp.setdefault((l["stat"], l["side"], "54+" if l["win"] >= 0.54 else "<54"), []).append(l)
        rows = [{"name": f"{s}/{sd}/{b}", "n": len(v), "hit": round(sum(x["ok"] for x in v) / len(v), 3),
                 "expected": round(sum(x["win"] for x in v) / len(v), 3)} for (s, sd, b), v in sorted(grp.items()) if len(v) >= 8]
        parts.append(table(rows, "Mercado/lado/tramo de probabilidad (>= 8 piernas):", ("name", "n", "hit", "expected")))
    return "\n\n".join(p for p in parts if p)


def candidates(now: datetime) -> list[dict]:
    """Open legs of both sports (not started), best fair probability first."""
    limit = now + timedelta(minutes=10)
    pool: list[dict] = []
    for sport, path in (("nba", NBA_PICKS), ("nfl", NFL_PICKS)):
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        seen = set()
        for p in doc.get("picks", []) + doc.get("high_prob", []):
            k = nc.leg_key(p)
            if k in seen or parsedate_to_datetime(p["start"]) <= limit:
                continue
            seen.add(k)
            pool.append({**p, "sport": sport})
    pool.sort(key=lambda p: -p["fair_prob"])
    return pool[:MAX_LEGS]


def describe(i: int, p: dict) -> str:
    start = parsedate_to_datetime(p["start"]).strftime("%d/%m %H:%MZ")
    return (f'L{i:03d} | {p["sport"].upper()} | {p["player"]} ({p.get("team", "")}) | {p["stat"]} {p["side"]} {p["line"]} | '
            f'cuota Stake {p["stake_odds"]} (otro lado {p.get("stake_opp")}) | prob. justa casas {p["fair_prob"]:.3f} en {p.get("books", 1)} casa(s) | '
            f'consenso BP {p.get("cons_prob")} | {p["game"]} {start} | líneas: {p.get("fanduel", "")}')


def evaluate(pool: list[dict], day: str) -> dict[str, float]:
    """Jev's probability for each leg key (cached per day and odds, so a re-run does not change a leg's number)."""
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    cache = {k: v for k, v in cache.items() if v["day"] == day}
    sig = lambda p: f'{nc.leg_key(p)}|{p["stake_odds"]}'  # noqa: E731
    todo = [p for p in pool if sig(p) not in cache]
    if todo:
        ids = {f"L{i:03d}": p for i, p in enumerate(todo, 1)}
        state = (knowledge() + "\n\n=== PIERNAS ABIERTAS (partidos sin empezar) ===\n" +
                 "\n".join(describe(i, p) for i, p in enumerate(todo, 1)))
        questions = {lid: {"type": "noul", "instructions":
                           f"Con todo el historial y las lecciones del estado, ¿acertará la pierna {lid} (la fila {lid} de PIERNAS ABIERTAS)? "
                           "Responde con la probabilidad real de que se cumpla (no te limites a copiar la probabilidad de las casas: "
                           "ajústala según lo que dicen los resultados históricos de ese mercado, lado y tramo)."}
                     for lid in ids}
        probs, usage = jev_client.probabilities(state, questions)
        logger.info("Jev: %d legs evaluated, %s input tokens", len(probs), usage.get("input_tokens"))
        for lid, p in ids.items():
            if lid in probs:
                cache[sig(p)] = {"day": day, "prob": round(probs[lid], 4)}
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {nc.leg_key(p): cache[sig(p)]["prob"] for p in pool if sig(p) in cache}


def jev_pool(pool: list[dict], probs: dict[str, float]) -> list[dict]:
    """Same legs, but with Jev's probability as the leg probability (our own kept as our_prob)."""
    out = []
    for p in pool:
        jp = probs.get(nc.leg_key(p))
        if jp is None:
            continue
        out.append({**p, "our_prob": p["fair_prob"], "fair_prob": jp, "ev": round(jp * p["stake_odds"] - 1, 4)})
    return out


def scope_combos(pool: list[dict], scope: str) -> list[dict]:
    legs = [p for p in pool if scope == "total" or p["sport"] == scope]
    sport_of = {nc.leg_key(p): p["sport"] for p in legs}

    def mixed(c: dict) -> bool:
        return len({sport_of[k] for k in c["legs"]}) > 1

    fams = {f"{scope}:{name}": ((lambda c, keep=keep: mixed(c) and keep(c)) if scope == "total" else keep, score)
            for name, (keep, score) in nc.FAMILIES.items()}
    combos = nc.build_combos(legs, families=fams, min_books=1)
    by_key = {nc.leg_key(p): p for p in legs}
    for c in combos:
        c["scope"] = scope
        for l in c["legs"]:
            src = by_key[l["key"]]
            l.update({"sport": src["sport"], "our_prob": src["our_prob"], "team": src.get("team"), "books": src.get("books", 1)})
    return combos


def main() -> None:
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    now = datetime.now(timezone.utc)
    day = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")
    pool = candidates(now)
    if not pool:
        print("Jev: no open legs")
        return
    probs = evaluate(pool, day)
    jp = jev_pool(pool, probs)

    HISTORY.mkdir(parents=True, exist_ok=True)
    snap_path = HISTORY / f"{day}.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {"date": day, "runs": []}
    available = nc.available_lines(ROOT / "data" / "nba_stake_cache.json", ROOT / "nfl" / "data" / "nfl_stake_cache.json")
    result: dict[str, list] = {}
    snap_for = lambda scope: {"runs": [{"combos": [c for c in r["combos"] if c.get("scope") == scope]} for r in snap["runs"]]}  # noqa: E731
    for scope in SCOPES:
        fresh = scope_combos(jp, scope)
        result[scope] = nc.freeze_combos(fresh, snap_for(scope), available=available)
        for c in result[scope]:
            c["scope"] = scope
    if "--no-snapshot" in sys.argv:
        print({s: len(v) for s, v in result.items()})
        return

    known_combos = {(c["scope"], tuple(sorted(l["key"] for l in c["legs"]))) for r in snap["runs"] for c in r["combos"]}
    new_combos = [c for s in SCOPES for c in result[s] if (s, tuple(sorted(l["key"] for l in c["legs"]))) not in known_combos]
    known_legs = {nc.leg_key(p) for r in snap["runs"] for p in r["picks"]}
    new_picks = [p for p in jp if nc.leg_key(p) not in known_legs]   # every leg Jev judged: used to measure its calibration vs ours
    snap["runs"].append({"at": now.isoformat(), "picks": new_picks, "combos": new_combos, "quotes": {}})
    snap_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")

    doc = {"timestamp": now.isoformat(), **result, "legs_evaluated": len(jp),
           "context_hash": hashlib.sha1(knowledge().encode()).hexdigest()[:8]}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Jev: {len(jp)} legs judged; combos " + ", ".join(f"{s} {len(result[s])}" for s in SCOPES) + f" ({len(new_combos)} new)")
    for s in SCOPES:
        for c in result[s]:
            print(f"[{'+'.join(c['families'])}] odds {c['odds']:.2f} Jev {c['prob']:.1%} EV {c['ev']:+.0%}")
            for l in c["legs"]:
                print(f"    {l['sport'].upper()} {l['player']} {l['side']} {l['line']} {l['stat']} @{l['stake_odds']} (Jev {l['fair_prob']:.0%} / casas {l['our_prob']:.0%})")


if __name__ == "__main__":
    main()
