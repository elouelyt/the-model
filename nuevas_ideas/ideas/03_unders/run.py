"""Idea 03 - solo UNDERS (video 'NBA playoffs unders': ~53.7 % of PrizePicks props went under, rebounds / R+A / FGA >= 56 %).

Same rules as the production combos (win >= 54 %, EV > 0.5 %, >= 2 books, games not started, one leg per player,
max 2 legs per game), but only Under legs. Paper only: it never touches the bettable combos.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import combo_from_legs, load_picks_doc, save_combos  # noqa: E402
import nba_combos  # noqa: E402

IDEA = "03_unders"


def main() -> None:
    doc = load_picks_doc()
    unders = [p for p in doc["picks"] if p["side"] == "Under"]
    fams = {"unders": (lambda c: True, lambda c: c["prob"])}
    built = nba_combos.build_combos(unders, tracking=False, per_family=nba_combos.PER_FAMILY, families=fams)
    combos = [combo_from_legs(c["legs"], ["unders"], c["odds"], c["prob"]) for c in built]   # build_combos already returns the leg dicts
    print(f"[{IDEA}] {len(unders)} under legs -> {len(combos)} combos, {save_combos(IDEA, combos)} new")


if __name__ == "__main__":
    main()
