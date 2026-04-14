# ATP Odds – Data Schema

> **Status:** Confirmed and extended in Sprint 3. Schema applies to all ATP tournaments (not just Miami Open).

## Source
- **API:** The-Odds-API v4
- **Sport keys:** Dynamic — all active `tennis_atp_*` keys discovered via `/v4/sports/`
- **Market:** `h2h` (head-to-head win/lose odds)
- **Region:** `us`
- **Raw files:** `data/raw/tennis_odds_<timestamp>.json` (local) → `gs://<bucket>/raw/` (GCP)
- **Processed files:** `data/processed/tennis_odds_processed_<timestamp>.csv` (local) → BigQuery (GCP)

## Raw JSON Structure

```
[ event, event, ... ]
  └── event
        ├── id                  (str)  unique event ID
        ├── sport_key           (str)  e.g. "tennis_atp_miami_open"
        ├── sport_title         (str)  e.g. "ATP Miami Open"
        ├── commence_time       (str)  ISO 8601 UTC timestamp
        ├── home_team           (str)  player name
        ├── away_team           (str)  player name
        └── bookmakers          (list)
              └── bookmaker
                    ├── key         (str)   bookmaker identifier
                    ├── title       (str)   bookmaker display name
                    ├── last_update (str)   ISO 8601 UTC timestamp
                    └── markets     (list)
                          └── market (key = "h2h")
                                └── outcomes (list, always 2 for h2h)
                                      └── outcome
                                            ├── name  (str)   player name
                                            └── price (float) decimal odds
```

## Flat Schema (production — BigQuery)

One row per outcome per bookmaker per match (2 outcomes × N bookmakers per event).

| Column | Type | Notes |
|---|---|---|
| `event_id` | STRING | Unique per match |
| `sport_key` | STRING | e.g. `tennis_atp_miami_open` |
| `sport_title` | STRING | e.g. `ATP Miami Open` |
| `home_team` | STRING | Player 1 name |
| `away_team` | STRING | Player 2 name |
| `commence_time` | TIMESTAMP | UTC-aware, parsed from ISO 8601 |
| `bookmaker_key` | STRING | e.g. `draftkings` |
| `bookmaker_title` | STRING | e.g. `DraftKings` |
| `bookmaker_last_update` | TIMESTAMP | UTC-aware |
| `market_key` | STRING | Always `h2h` |
| `market_last_update` | TIMESTAMP | UTC-aware |
| `outcome_name` | STRING | Player name for this outcome |
| `price` | FLOAT | Decimal odds (e.g. 1.42) |
| `ingested_at` | TIMESTAMP | UTC pipeline run timestamp |
| `raw_implied` | FLOAT | `1 / price` — naive implied probability |
| `true_implied` | FLOAT | Vig-removed probability — `raw_implied / sum(raw_implied)` per bookmaker per market |

## Key Notes
- **Prices are decimal odds** (e.g. 1.42 = 1.42x stake), not American odds
- **Vig (overround):** Bookmakers inflate raw implied probs so they sum to >1 (typically 3–6%). `true_implied` normalises this out.
- **3–7 bookmakers per match:** BetRivers, DraftKings, FanDuel, Bovada, LowVig.ag, BetOnline.ag, BetUS
- Bookmakers may suspend lines mid-match — not all bookmakers appear for every event
- `commence_time` reflects scheduled start; odds are available before and during matches
