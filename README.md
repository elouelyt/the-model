# the-model

A static prediction engine that runs daily, fetches live pre-match odds, compares them against a ranking-based probability model, and publishes the results as a self-contained HTML page via GitHub Pages.

**Live:** [elouelyt.github.io/the-model](https://elouelyt.github.io/the-model)

---

## How it works

1. A GitHub Actions workflow runs every day at **08:00 UTC**
2. It fetches live pre-match odds from [The-Odds-API](https://the-odds-api.com)
3. It scrapes current player rankings from the official rankings page
4. For each match it computes: model probability · bookmaker implied · edge · value signal
5. Results are written to `index.html` and committed back to the repo
6. GitHub Pages serves the file at the live URL above

In-play matches are automatically filtered out — live odds reflect current match state, not pre-match probability, so they are not valid inputs for the model.

---

## Model

**Formula:** `P(A wins) = points_A / (points_A + points_B)`

A **value bet** is flagged when `model_prob > raw_implied + 0.05` (i.e. the model edge exceeds the bookmaker's vig).

| Signal | Condition |
|---|---|
| VALUE BET | edge > 5% |
| MARGINAL | 0% < edge ≤ 5% |
| NO BET | edge ≤ 0% |

> For informational purposes only — not financial or betting advice.

---

## Local setup

```bash
# 1. Clone
git clone https://github.com/elouelyt/the-model.git
cd the-model

# 2. Install minimal deps
pip install -r requirements-generate.txt

# 3. Set your API key
echo "THE_ODDS_API_KEY=your_key_here" > .env

# 4. Generate index.html locally
python generate_html.py

# 5. Open in browser
open index.html   # or just double-click it
```

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Odds data | The-Odds-API v4 |
| Rankings | Live scrape (cloudscraper + BeautifulSoup) |
| Output | Static HTML — no backend, no database |
| Hosting | GitHub Pages |
| Automation | GitHub Actions (daily cron) |

---

*Developed by Mateo Grisales*
