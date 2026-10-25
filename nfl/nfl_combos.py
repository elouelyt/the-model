#!/usr/bin/env python3
"""Choose the NFL combos with EXACTLY the NBA system: this runs scripts/nba_combos.py (its main()) pointed at the NFL files.

Everything is shared, nothing is copied: legs with win >= 54 % and EV > 0.5 %, games not started, one leg per player, max 2 legs
per game, families probabilidad / valor / mixta, the frozen combos (a shown combo stays until its games start), the paper families
(pura, valor_ev, prob_ev, prudente), the per-batch quote log for CLV and the daily snapshot. Any improvement made to the NBA
engine reaches NFL automatically.

The only difference: MIN_BOOKS. NBA needs >= 2 reference books per line; NFL uses 2 too whenever the BettingPros web pass is fresh (Pinnacle +
the other books), and falls back to 1 (Pinnacle alone) if that pass is missing.
Output: nfl/data/nfl_picks.json (+ combos) and the snapshot nfl/data/nfl_history/<date>.json (settled by nfl_settle.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nba_combos as nc  # noqa: E402

BASE = Path(__file__).resolve().parent
def _min_books() -> int:
    """2 (the NBA rule) when a fresh BettingPros pass gives NFL a second reference book, else 1 (Pinnacle only)."""
    import json
    from datetime import datetime, timezone
    f = BASE / "data" / "nfl_bettingpros_cache.json"
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
        fresh = (datetime.now(timezone.utc) - datetime.fromisoformat(doc["timestamp"])).total_seconds() < 6 * 3600
        return 2 if fresh and len(doc["rows"]) >= 30 else 1
    except (OSError, KeyError, ValueError):
        return 1


MIN_BOOKS = _min_books()

nc.PICKS = BASE / "data" / "nfl_picks.json"
nc.HISTORY = BASE / "data" / "nfl_history"
nc.STAKE_CACHE = BASE / "data" / "nfl_stake_cache.json"
nc.ANALYSIS = BASE / "data" / "nfl_analysis.json"
nc.MIN_LEG_BOOKS = MIN_BOOKS

if __name__ == "__main__":
    nc.main()
