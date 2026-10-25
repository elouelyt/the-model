#!/usr/bin/env python3
"""Choose the NFL combos with EXACTLY the NBA system: this runs scripts/nba_combos.py (its main()) pointed at the NFL files.

Everything is shared, nothing is copied: legs with win >= 54 % and EV > 0.5 %, games not started, one leg per player, max 2 legs
per game, families probabilidad / valor / mixta, the frozen combos (a shown combo stays until its games start), the paper families
(pura, valor_ev, prob_ev, prudente), the per-batch quote log for CLV and the daily snapshot. Any improvement made to the NBA
engine reaches NFL automatically.

The only difference: MIN_BOOKS. NBA needs >= 2 reference books per line; NFL has a single reference book (Pinnacle, the sharpest one)
until a second one (BettingPros / FanDuel) is added; then set MIN_BOOKS = 2 and the rule is the same as NBA's.
Output: nfl/data/nfl_picks.json (+ combos) and the snapshot nfl/data/nfl_history/<date>.json (settled by nfl_settle.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nba_combos as nc  # noqa: E402

BASE = Path(__file__).resolve().parent
MIN_BOOKS = 1   # -> 2 as soon as NFL has a second reference book (same as NBA)

nc.PICKS = BASE / "data" / "nfl_picks.json"
nc.HISTORY = BASE / "data" / "nfl_history"
nc.STAKE_CACHE = BASE / "data" / "nfl_stake_cache.json"
nc.ANALYSIS = BASE / "data" / "nfl_analysis.json"
nc.MIN_LEG_BOOKS = MIN_BOOKS

if __name__ == "__main__":
    nc.main()
