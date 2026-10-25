"""Idea 09 - quitar el margen con el metodo de la POTENCIA en vez del proporcional.

Why: on 23-24/10 the Under legs with EV > 1 % and fair prob < 54 % hit 23 % (60 legs) vs 50 % expected. Proportional
no-vig (p = implied / sum of implied) is known to misprice the two sides when the juice is lopsided; the power method
solves k in po^k + pu^k = 1 and uses po^k. Here every leg's fair probability is recomputed from the book quotes stored in
the pick's `fanduel` string ('FD -110/-120 | PIN +100/-120'), averaged over books, and the usual production rules
(win >= 54 %, EV > 0.5 %, >= 2 books, one leg per player, max 2 per game) are applied with the new probability.
Paper only.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import combo_from_legs, load_picks_doc, save_combos  # noqa: E402
import nba_combos  # noqa: E402

IDEA = "09_devig_potencia"
QUOTE = re.compile(r"[A-Za-z]+\s+([+-]\d+)/([+-]\d+)")


def implied(am: int) -> float:
    return 100 / (am + 100) if am > 0 else -am / (-am + 100)


def power_fair(po: float, pu: float) -> float:
    lo, hi = 0.2, 5.0
    for _ in range(60):
        k = (lo + hi) / 2
        if po ** k + pu ** k > 1:
            lo = k
        else:
            hi = k
    return po ** ((lo + hi) / 2)


def fair_over_power(detail: str) -> float | None:
    quotes = QUOTE.findall(detail or "")
    if not quotes:
        return None
    return sum(power_fair(implied(int(o)), implied(int(u))) for o, u in quotes) / len(quotes)


def main() -> None:
    doc = load_picks_doc()
    legs = []
    for p in doc["picks"]:
        po = fair_over_power(p.get("fanduel"))
        if po is None:
            continue
        # the pick may be the Over or the Under; Stake odds of the pick's side are p["stake_odds"]
        prob = po if p["side"] == "Over" else 1 - po
        legs.append({**p, "fair_prob": round(prob, 4), "ev": round(prob * p["stake_odds"] - 1, 4)})
    fams = {"devig_pot": (lambda c: True, lambda c: c["prob"])}
    built = nba_combos.build_combos(legs, tracking=False, per_family=nba_combos.PER_FAMILY, families=fams)
    by_key = {nba_combos.leg_key(p): p for p in legs}
    combos = [combo_from_legs([by_key[k] for k in c["legs"]], ["devig_pot"], c["odds"], c["prob"]) for c in built]
    shift = [l["fair_prob"] - p["fair_prob"] for l, p in zip(legs, [q for q in doc["picks"] if fair_over_power(q.get("fanduel")) is not None])]
    avg = sum(shift) / len(shift) if shift else 0.0
    print(f"[{IDEA}] {len(legs)} legs; mean fair-prob shift vs proportional {avg * 100:+.2f} pts; {len(combos)} combos, {save_combos(IDEA, combos)} new")


if __name__ == "__main__":
    main()
