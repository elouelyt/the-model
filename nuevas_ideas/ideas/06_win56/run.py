"""Idea 06 - Win% minimo 56 % por pierna (production uses 54 %). More margin over the break-even, fewer combos.
Same rules otherwise (3 legs, EV > 0.5 %, >= 2 books, one leg per player, max 2 per game). Paper only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import combo_from_legs, load_picks_doc, save_combos  # noqa: E402
import nba_combos  # noqa: E402

IDEA = "06_win56"


def main() -> None:
    doc = load_picks_doc()
    fams = {"win56": (lambda c: True, lambda c: c["prob"])}
    built = nba_combos.build_combos(doc["picks"], tracking=False, per_family=nba_combos.PER_FAMILY, families=fams, min_leg_prob=0.56)
    by_key = {nba_combos.leg_key(p): p for p in doc["picks"]}
    combos = [combo_from_legs([by_key[k] for k in c["legs"]], ["win56"], c["odds"], c["prob"]) for c in built]
    print(f"[{IDEA}] {len(combos)} combos, {save_combos(IDEA, combos)} new")


if __name__ == "__main__":
    main()
