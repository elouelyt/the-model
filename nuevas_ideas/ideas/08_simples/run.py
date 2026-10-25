"""Idea 08 - apuestas SIMPLES (single legs): the lowest margin and variance. The top legs by EV and by probability,
each one a 1-leg paper bet. Compare its ROI/hit rate with the 3-leg combos. Paper only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import combo_from_legs, eligible_legs, load_picks_doc, save_combos  # noqa: E402

IDEA = "08_simples"


def main() -> None:
    legs = eligible_legs(load_picks_doc()["picks"])
    combos, seen = [], set()
    for fam, key in (("simple_ev", lambda p: p["ev"]), ("simple_prob", lambda p: p["fair_prob"])):
        n = 0
        for p in sorted(legs, key=key, reverse=True):
            if p["player"] in seen:
                continue
            seen.add(p["player"])
            combos.append(combo_from_legs([p], [fam], p["stake_odds"], p["fair_prob"]))
            n += 1
            if n == 5:
                break
    print(f"[{IDEA}] {len(legs)} legs, {len(combos)} single bets, {save_combos(IDEA, combos)} new")


if __name__ == "__main__":
    main()
