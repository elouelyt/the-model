"""Idea 04 - filtro de MINUTOS (video NFL: 'snap count >= 40 %' lifted the hit rate from 58 % to 65 %).

NBA analogue: only legs of players whose median minutes last season were >= MIN_MEDIAN (from ESPN game logs,
data/minutes_median.json, refreshed with espn_minutes.py). Same production rules otherwise. Paper only.
Day-1 data (23/10, 99 legs) showed no benefit (29 % vs 42 % the other way round), so this is a pure 7-day test.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import BASE, combo_from_legs, load_picks_doc, save_combos  # noqa: E402
import nba_combos  # noqa: E402

IDEA = "04_minutos"
MIN_MEDIAN = 28.0
MEDIANS = BASE / "data" / "minutes_median.json"


def norm(n: str) -> str:
    s = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]+", " ", s).strip()


def main() -> None:
    med = json.loads(MEDIANS.read_text(encoding="utf-8"))
    doc = load_picks_doc()
    legs = [p for p in doc["picks"] if med.get(norm(p["player"]), 0) >= MIN_MEDIAN]
    fams = {"minutos": (lambda c: True, lambda c: c["prob"])}
    built = nba_combos.build_combos(legs, tracking=False, per_family=nba_combos.PER_FAMILY, families=fams)
    by_key = {nba_combos.leg_key(p): p for p in legs}
    combos = [combo_from_legs([by_key[k] for k in c["legs"]], ["minutos"], c["odds"], c["prob"]) for c in built]
    print(f"[{IDEA}] {len(legs)}/{len(doc['picks'])} legs with median >= {MIN_MEDIAN:g} min -> {len(combos)} combos, "
          f"{save_combos(IDEA, combos)} new")


if __name__ == "__main__":
    main()
