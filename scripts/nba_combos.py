#!/usr/bin/env python3
"""Build 3-leg combos (the video's "3-man power") from data/nba_picks.json and snapshot the day.

Rules: every leg from a different game and a different player, only games that have not started,
leg win% >= 54%, at least 2 books agreeing, and EV > 0.5%. Across the whole set a leg is used once, a player once and a game at most
GAME_CAP times (less correlation between tickets). Combo odds = product of Stake odds, combo probability = product of fair probabilities,
combo EV = probability * odds - 1. Three families are produced so results can be compared later:
  - probabilidad: highest combined probability (the video's "highest chance of hitting")
  - valor:        highest combo EV
  - mixta:        highest probability among combos with EV >= 20%
Output is merged into nba_picks.json and a
snapshot of picks + combos is saved in data/nba_history/<date>.json for settlement and analysis.
"""

import itertools
import json
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PICKS = ROOT / "data" / "nba_picks.json"
HISTORY = ROOT / "data" / "nba_history"
STAKE_CACHE = ROOT / "data" / "nba_stake_cache.json"
ANALYSIS = ROOT / "data" / "nba_analysis.json"
MIN_LEG_EV = 0.005
MIN_LEG_BOOKS = 2     # at least two reference books must agree on the line
MIN_LEG_PROB = 0.54   # the video's rule: only legs the sharp books give >= 54%
GAME_CAP = 2          # max legs per game across the whole bettable set
TRACKING_GAME_CAP = 3
PER_FAMILY = 3
TRACKING_PER_FAMILY = 5
LEGACY = {  # yesterday's rules, paper only, to see whether its results repeat
    "valor_ev": (lambda c: True, lambda c: c["ev"]),
    "prob_ev": (lambda c: True, lambda c: c["prob"]),
}
SHRINK = 0.015  # paper test "prudente": discount every leg's fair probability by 1.5 points before the rules
PRUDENT = {"prudente": (lambda c: c["ev"] > 0, lambda c: c["prob"])}
UNITS = 0.25  # video: 0.25-0.5 units on 3-man slips
FAMILIES = {
    "probabilidad": (lambda c: True, lambda c: c["prob"]),
    "valor": (lambda c: True, lambda c: c["ev"]),
    "mixta": (lambda c: c["ev"] >= 0.20, lambda c: c["prob"]),
}


def leg_key(p: dict) -> str:
    return f'{p["start"][:16]}|{p["player"]}|{p["stat"]}|{p["side"]}|{p["line"]}'


def build_combos(picks: list[dict], now: datetime | None = None, tracking: bool = False,
                 per_family: int = PER_FAMILY, families: dict | None = None, min_leg_ev: float = MIN_LEG_EV,
                 future_only: bool | None = None, min_leg_prob: float = MIN_LEG_PROB,
                 game_cap: int = GAME_CAP, min_books: int | None = None) -> list[dict]:
    """tracking=False: bettable combos (all games still to start).
    tracking=True: paper combos with at least one leg from a game that already started."""
    now = now or datetime.now(timezone.utc)
    min_books = MIN_LEG_BOOKS if min_books is None else min_books   # module value, so another sport can override it
    limit = now + timedelta(minutes=10)

    def started(p: dict) -> bool:
        return parsedate_to_datetime(p["start"]) <= limit

    only_future = (not tracking) if future_only is None else future_only
    in_play_limit = now - timedelta(hours=2)  # older games are usually over: their results would be known

    def unfinished(p: dict) -> bool:
        return parsedate_to_datetime(p["start"]) > in_play_limit

    legs = [p for p in picks if p["ev"] >= min_leg_ev and p["fair_prob"] >= min_leg_prob
            and p.get("books", 1) >= min_books and (not only_future or not started(p)) and (not tracking or unfinished(p))]
    combos = []
    for trio in itertools.combinations(legs, 3):
        if len({p["game"] for p in trio}) < 3 or len({p["player"] for p in trio}) < 3:
            continue
        if tracking and future_only is None and not any(started(p) for p in trio):
            continue
        odds, prob = 1.0, 1.0
        for p in trio:
            odds *= p["stake_odds"]
            prob *= p["fair_prob"]
        combos.append({"legs": [leg_key(p) for p in trio], "prob": prob, "odds": odds, "ev": prob * odds - 1})

    leg_info = {leg_key(p): p for p in legs}
    used_legs: set[str] = set()
    used_players: set[str] = set()
    game_count: dict[str, int] = {}
    chosen: dict[tuple, dict] = {}
    for name, (keep, score) in (families or FAMILIES).items():
        picked = 0
        for c in sorted((c for c in combos if keep(c)), key=score, reverse=True):
            infos = [leg_info[k] for k in c["legs"]]
            if used_legs & set(c["legs"]) or used_players & {i["player"] for i in infos}:
                continue
            if any(game_count.get(i["game"], 0) + 1 > game_cap for i in infos):
                continue
            used_legs |= set(c["legs"])
            used_players |= {i["player"] for i in infos}
            for i in infos:
                game_count[i["game"]] = game_count.get(i["game"], 0) + 1
            entry = chosen.setdefault(tuple(sorted(c["legs"])), {**c, "families": []})
            entry["families"].append(name)
            picked += 1
            if picked == per_family:
                break

    by_key = {leg_key(p): p for p in picks}
    out = []
    for c in chosen.values():
        c["units"] = UNITS
        c["legs"] = [{"key": k, "player": by_key[k]["player"], "stat": by_key[k]["stat"],
                      "side": by_key[k]["side"], "line": by_key[k]["line"],
                      "stake_odds": by_key[k]["stake_odds"], "fair_prob": by_key[k]["fair_prob"],
                      "ev": by_key[k]["ev"], "game": by_key[k]["game"], "start": by_key[k]["start"],
                      "outcome_id": by_key[k].get("outcome_id"), "event_id": by_key[k].get("event_id"), "fixture": by_key[k].get("fixture"),
                      "cons_prob": by_key[k].get("cons_prob"), "cons_age_h": by_key[k].get("cons_age_h")}
                     for k in c["legs"]]
        c["prob"], c["odds"], c["ev"] = round(c["prob"], 4), round(c["odds"], 2), round(c["ev"], 4)
        c["tracking"] = tracking
        out.append(c)
    return sorted(out, key=lambda c: c["ev"], reverse=True)


def available_lines(*caches: Path, max_age_h: float = 3.0) -> set | None:
    """(fixture, player, stat, line) of every line Stake offers right now, from fresh Stake caches; None when a cache is missing or stale
    (then nothing is dropped: we cannot tell)."""
    out: set = set()
    for path in caches:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            age = datetime.now(timezone.utc) - datetime.fromisoformat(doc["timestamp"])
        except (OSError, KeyError, ValueError):
            return None
        if age > timedelta(hours=max_age_h) or len(doc["rows"]) < 100:
            return None
        out |= {(r["fixture"], r["player"], r["stat"], r["line"]) for r in doc["rows"]}
    return out


def freeze_combos(fresh: list[dict], snap: dict, now: datetime | None = None, available: set | None = None) -> list[dict]:
    """Keep the bettable combos already shown today while all their games are still to start, so a combo the
    user may have bet never vanishes because odds moved. A frozen combo IS dropped when Stake no longer offers one of its lines
    (player ruled out, market withdrawn): `available` = lines Stake offers now. Fresh combos are added only if they reuse no frozen leg or player."""
    limit = (now or datetime.now(timezone.utc)) + timedelta(minutes=10)
    kept, seen = [], set()
    for r in snap["runs"]:
        for c in r["combos"]:
            ident = tuple(sorted(l["key"] for l in c["legs"]))
            if c.get("tracking") or ident in seen or any(parsedate_to_datetime(l["start"]) <= limit for l in c["legs"]):
                continue
            if available is not None and any(l.get("fixture") and (l["fixture"], l["player"], l["stat"], l["line"]) not in available
                                             for l in c["legs"]):
                continue   # Stake withdrew one of the legs: the combo cannot be bet any more
            seen.add(ident)
            kept.append(c)
    used_legs = {l["key"] for c in kept for l in c["legs"]}
    used_players = {l["player"] for c in kept for l in c["legs"]}
    added = [c for c in fresh if tuple(sorted(l["key"] for l in c["legs"])) not in seen
             and not used_legs & {l["key"] for l in c["legs"]} and not used_players & {l["player"] for l in c["legs"]}]
    return kept + added


def main() -> None:
    doc = json.loads(PICKS.read_text(encoding="utf-8"))
    combos = build_combos(doc["picks"])
    day = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d")  # slate date: 01:00 runs belong to the evening before
    snap_path = HISTORY / f"{day}.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {"date": day, "runs": []}
    combos = freeze_combos(combos, snap, available=available_lines(STAKE_CACHE))
    stake_cache = STAKE_CACHE
    fixtures = {" vs ".join(g["teams"]): g["fixture"] for g in json.loads(stake_cache.read_text(encoding="utf-8"))["games"]} if stake_cache.exists() else {}
    for c in combos + [c for r in snap["runs"] for c in r["combos"]]:  # combos saved before legs carried their game page
        for l in c["legs"]:
            if not l.get("fixture"):
                l["fixture"] = fixtures.get(l["game"])
    doc["combos"] = combos
    analysis_path = ANALYSIS
    if analysis_path.exists():
        doc["analysis"] = json.loads(analysis_path.read_text(encoding="utf-8"))

    if "--no-snapshot" in sys.argv:  # tests: do not write into the history
        print(f"{len(combos)} bettable combos (no snapshot)")
        return
    HISTORY.mkdir(parents=True, exist_ok=True)

    # paper combos: today's pool (every leg recommended today, first sighting) incl. games already started
    pool = {leg_key(p): p for r in snap["runs"] for p in r["picks"]}
    pool.update({leg_key(p): p for p in doc["picks"]})
    tracking = []
    if doc["picks"]:  # never build paper combos after the day's games are over (no post-hoc picks)
        tracking = build_combos(list(pool.values()), tracking=True, per_family=TRACKING_PER_FAMILY,
                                game_cap=TRACKING_GAME_CAP)
    # paper family "pura": highest fair probability regardless of EV (Stake odds usually below fair)
    pure = [] if not doc["picks"] else build_combos(doc.get("high_prob", []), tracking=True, per_family=TRACKING_PER_FAMILY, min_leg_ev=-1.0,
                        families={"pura": (lambda c: True, lambda c: c["prob"])}, future_only=True,
                        min_leg_prob=0.0, game_cap=TRACKING_GAME_CAP)
    tracking += pure
    # legacy rules (no win% filter, one book is enough) on upcoming games, paper only
    legacy = [] if not doc["picks"] else build_combos(
        doc["picks"], tracking=True, per_family=TRACKING_PER_FAMILY, families=LEGACY, future_only=True,
        min_leg_prob=0.0, min_books=1, game_cap=TRACKING_GAME_CAP)
    tracking += legacy
    # paper test "prudente" (does not change the bettable combos): same rules, legs with fair_prob - SHRINK
    shrunk = [{**p, "fair_prob": round(p["fair_prob"] - SHRINK, 4), "ev": round((p["fair_prob"] - SHRINK) * p["stake_odds"] - 1, 4)}
              for p in doc["picks"]]
    prudent = [] if not doc["picks"] else build_combos(
        shrunk, tracking=True, per_family=TRACKING_PER_FAMILY, families=PRUDENT, future_only=True,
        game_cap=TRACKING_GAME_CAP)
    by_legs = {tuple(sorted(l["key"] for l in c["legs"])): c for c in combos + tracking}
    for c in prudent:  # a combo the other rules already picked just gets the extra family label
        same = by_legs.get(tuple(sorted(l["key"] for l in c["legs"])))
        if same is not None:
            same["families"].append("prudente")
        else:
            tracking.append(c)
    doc["combos_tracking"] = tracking
    PICKS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    # keep every leg/combo ever recommended that day (first sighting wins), settled later
    known_legs = {leg_key(p) for r in snap["runs"] for p in r["picks"]}
    known_combos = {tuple(sorted(l["key"] for l in c["legs"])) for r in snap["runs"] for c in r["combos"]}
    extras = [{**p, "extra": True} for p in doc.get("high_prob", [])
              if leg_key(p) not in {leg_key(q) for q in doc["picks"]}]
    new_picks = [p for p in doc["picks"] + extras if leg_key(p) not in known_legs]
    stored = {tuple(sorted(l["key"] for l in c["legs"])): c for r in snap["runs"] for c in r["combos"]}
    for c in combos + tracking:  # a combo recorded earlier under other rules can also belong to "prudente" now
        old = stored.get(tuple(sorted(l["key"] for l in c["legs"])))
        if old is not None:
            old["families"] = sorted(set(old["families"]) | set(c["families"]))
    new_combos = [c for c in combos + tracking if tuple(sorted(l["key"] for l in c["legs"])) not in known_combos]
    quotes = {leg_key(p): [p["stake_odds"], p.get("stake_opp"), p["fair_prob"]] for p in doc["picks"]}
    snap["runs"].append({"at": doc["timestamp"], "picks": new_picks, "combos": new_combos, "quotes": quotes})
    snap_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")

    print(f"{len(combos)} bettable combos + {len(tracking)} tracking combos (new today: {len(new_combos)}), snapshot {snap_path.name}")
    for c in combos + tracking:
        print(f"{'(seg.) ' if c['tracking'] else ''}[{'+'.join(c['families'])}] odds {c['odds']:.2f} prob {c['prob']:.1%} EV {c['ev']:+.0%}")
        for l in c["legs"]:
            print(f"    {l['player']} {l['side']} {l['line']} {l['stat']} @{l['stake_odds']} ({l['fair_prob']:.0%}) - {l['game']}")


if __name__ == "__main__":
    main()
