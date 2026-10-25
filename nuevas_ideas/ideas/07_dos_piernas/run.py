"""Idea 07 - combinadas de 2 piernas (less margin than 3 legs, higher hit rate). Production rules for the legs,
two different games and players, each leg used once. Families: highest probability / highest EV. Paper only."""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import combo_from_legs, eligible_legs, load_picks_doc, save_combos  # noqa: E402

IDEA = "07_dos_piernas"


def main() -> None:
    legs = eligible_legs(load_picks_doc()["picks"])
    pairs = []
    for a, b in itertools.combinations(legs, 2):
        if a["game"] == b["game"] or a["player"] == b["player"]:
            continue
        odds = a["stake_odds"] * b["stake_odds"]
        prob = a["fair_prob"] * b["fair_prob"]
        pairs.append((a, b, odds, prob))
    combos, used = [], set()
    for fam, key in (("dos_prob", lambda t: t[3]), ("dos_ev", lambda t: t[3] * t[2])):
        n = 0
        for a, b, odds, prob in sorted(pairs, key=key, reverse=True):
            ids = {(a["player"], a["stat"]), (b["player"], b["stat"])}
            if ids & used:
                continue
            used |= ids
            combos.append(combo_from_legs([a, b], [fam], odds, prob))
            n += 1
            if n == 4:
                break
    print(f"[{IDEA}] {len(legs)} legs, {len(combos)} combos, {save_combos(IDEA, combos)} new")


if __name__ == "__main__":
    main()
