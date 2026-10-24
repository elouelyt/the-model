# Project: Tennis AI Data Platform
# Role: Senior GCP Data & ML Engineer

## Architecture Rules
- Cloud Provider: Google Cloud Platform (GCP) exclusively.
- Language: Python 3.10+.
- Code Style: PEP 8, strict type hints, and Google-style Docstrings for all functions.
- Security: Never hardcode API keys or GCP credentials. Use `python-dotenv` and `.env` for local dev. All secrets are stored in **GCP Secret Manager** — use `scripts/push_secrets.sh` to upload and `scripts/setup_env.sh` to restore on a new machine.
- Config: Non-sensitive config (`GCP_PROJECT_ID`, `GCP_BUCKET_NAME`) lives in `config.yaml` (tracked in git). Load via `src/config.py`. Only true secrets (API keys, service account JSON) go in `.env` and Secret Manager.

## Repository Structure (Enforce Modularity)
- Do NOT put business logic in `main.py`. 
- Data extraction scripts go in `src/ingestion/`.
- Temporary raw data goes in `data/raw/` (ensure this is in .gitignore).

## Sprint 1 (API to GCS) — COMPLETE ✓
Local execution and GCP Cloud Storage upload are 100% done. The pipeline successfully fetches H2H odds from The-Odds-API and lands raw JSON files in GCS.

## Sprint 2 (ETL & BigQuery) — COMPLETE ✓
Nested JSON flattened with Pandas, schema confirmed via EDA (see `docs/MIAMI_OPEN_SCHEMA.md`), data loaded into BigQuery. One row per match per bookmaker.

## Sprint 3 (End-to-End Prediction MVP) — COMPLETE ✓

**Deliverable:** Local Streamlit demo (`app.py`) — fetches live ATP pre-match odds, retrieves rankings via Gemini Flash, computes ranking-based win probabilities, compares vs bookmaker raw implied, surfaces value bet / marginal / no bet signals.

**Key decisions made:**
- Ranking agent accepts exact player names from the odds API — Gemini returns those exact names back, no fuzzy matching needed
- `filter_upcoming()` in `transform.py` strips in-play matches before any prediction — live odds reflect score state, not pre-match probability
- Results cached in `st.session_state` — re-renders don't re-hit the APIs; user clicks "Run" explicitly

**Local data flow:**
- `data/raw/tennis_odds_<timestamp>.json` — raw API response (mirrors GCS)
- `data/processed/tennis_odds_processed_<timestamp>.csv` — flat transformed data (mirrors BigQuery)

## Sprint 4 — Deploy to GCP + mateogrisales.com — COMPLETE ✓

**Goal:** Go live as fast as possible with the working ranking-based model.

- `api/main.py`: FastAPI app, `POST /predict` + `GET /health`, `X-API-Key` auth, Pydantic response models, CORS configurable via env var
- `Dockerfile`: `python:3.12-slim`, built and pushed to Artifact Registry via **Cloud Build** (no local Docker needed)
- Cloud Run deployed **privately** (`--no-allow-unauthenticated`) in `us-central1` — never exposed directly to the internet
- **API Gateway** (`tennis-gateway`) deployed as the public-facing layer using `api-gateway.yaml` (OpenAPI spec)
- `api-gateway-invoker` service account holds `roles/run.invoker` on Cloud Run; gateway authenticates automatically
- `X-API-Key` auth validated by FastAPI — gateway passes it through, does not validate at gateway layer
- **Public gateway URL:** `https://tennis-gateway-agmlnd9p.uc.gateway.dev`
- **Cloud Run URL (private):** `https://tennis-api-er2jgzyldq-uc.a.run.app`
- React UI live at `https://orange-court-ai.lovable.app` — confirmed working end-to-end
- All secrets moved to GCP Secret Manager, Cloud Run capped at 3 max instances, budget alert wired to email
- DNS configured in GoDaddy pointing `tennis.mateogrisales.com` → Lovable frontend

## Sprint 4b — GitHub Pages Static Site — COMPLETE ✓

**Goal:** Zero-cost public portfolio page that updates daily without any backend or GCP dependency.

- `generate_html.py`: runs full pipeline (fetch odds → scrape rankings → compute probabilities) and writes a self-contained dark-themed `index.html`
- `.github/workflows/daily.yml`: GitHub Actions cron at 08:00 UTC — installs minimal deps, runs pipeline, commits `index.html` back to repo
- `requirements-generate.txt`: minimal dep set (requests, pandas, beautifulsoup4, cloudscraper) — no GCP packages needed
- `extract_odds.py`: `google.cloud.storage` import made lazy (moved inside `upload_to_gcs`) so the module loads cleanly without GCP credentials
- **Live URL:** `https://elouelyt.github.io/the-model`
- **Repo:** `https://github.com/elouelyt/the-model`
- Only secret required: `THE_ODDS_API_KEY` as a GitHub Actions secret

**Story 4 cost controls — DONE ✓**
- GCP budget alert scoped to `tennis-data-487809`, email notifications wired to `mateo@grisalogic.com` via Cloud Monitoring channel `14755856984491073698`
- Cloud Run `tennis-api` capped at 3 max instances — hard ceiling against traffic attacks
- `docs/COST_CONTROLS.md` documents all controls and restore commands

**Key lesson from Sprint 1:** Using `_SPORT = "upcoming"` returns all sports, not just tennis.
**Key lesson from Sprint 3:** Never hardcode tournament sport keys — use `/v4/sports/` to discover active `tennis_atp_*` keys dynamically.
**Key lesson from Sprint 3:** Betting advice must compare model prob vs `raw_implied` (1/price), NOT `true_implied`. The vig is already baked into the raw price — that's the real threshold for a value bet.
**Key lesson from Sprint 3:** The Odds API returns ALL matches including in-play (live) ones. Live odds shift dramatically with the score (e.g., a player up 5-1 in the third set gets priced at 95% — reflecting current match state, not pre-match probability). Comparing a static ranking-based model against live odds is meaningless and misleading. Always filter out matches where `commence_time` is in the past before running predictions. Only pre-match odds are valid inputs to the model.
**Key lesson from Sprint 4:** The `grisalogic.com` GCP org enforces `iam.allowedPolicyMemberDomains` — this blocks `allUsers` IAM bindings on Cloud Run. Disabling it globally is bad practice. The senior pattern is to keep Cloud Run private and front it with **API Gateway** using a dedicated `api-gateway-invoker` service account. Never attempt to grant `allUsers` run.invoker — use the gateway pattern instead.
**Key lesson from Sprint 4:** GCP budget alerts are useless if `notificationsRule` is empty — they fire internally but no human is notified. Always attach a Cloud Monitoring notification channel. Also always set `--max-instances` on Cloud Run — the default is unbounded, which is a cost risk under traffic attacks.
**Key lesson from Sprint 4:** `gcloud run services update --update-env-vars` treats commas as list delimiters — passing a comma-separated value like `CORS_ORIGINS=url1,url2` fails with "Bad syntax for dict arg". Fix: prefix the value with `^|^` to switch the delimiter to `|`, e.g. `--update-env-vars "^|^CORS_ORIGINS=url1,url2"`.
**Key lesson from Sprint 4:** Lovable generates a new preview URL for each build — `CORS_ORIGINS` on Cloud Run must be updated every time the Lovable preview domain changes. The permanent fix is locking CORS to the production custom domain (`tennis.mateogrisales.com`) once deployed.
**Key lesson from Sprint 4:** Lovable's Secrets UI rejects `VITE_` prefixed variables — those are build-time browser values and must come from `.env` files or the hosting platform's env var settings (Netlify/Vercel). Lovable Secrets UI is for server-side/runtime secrets only (e.g. Supabase keys). There is no build-secrets panel accessible on any Lovable plan — the UI described in their docs does not exist in the current interface. The only option for `VITE_` vars on Lovable is to hardcode the value directly in source code, which is acceptable when the key is low-value (read-only endpoint, no financial or data-write access) and backend controls (server-side validation, CORS, instance cap) bound the blast radius. See `docs/SECURITY.md` for the full rationale.
**Key lesson from Sprint 4:** For a public React frontend, `VITE_` env vars are embedded in the compiled JS bundle at build time — they are visible in DevTools regardless of how they are set. Real protection must live server-side (strong key validation, CORS, max instances). Documented in `docs/SECURITY.md`.
**Key lesson from Sprint 4:** API Gateway only routes paths defined in the OpenAPI spec — browser CORS preflight (`OPTIONS`) requests must be explicitly defined as a separate method on each path, otherwise the gateway returns 404 and the browser blocks the request.
**Key lesson from Sprint 4:** `gemini-2.5-flash` with Google Search grounding returns 0 content parts (`response.text = None`) — a known SDK incompatibility with the thinking model. Do not use Gemini for real-time rankings at all. Scrape `atptour.com/en/rankings/singles` directly with `requests` + `BeautifulSoup` — full player names are in the profile link slug (`/en/players/carlos-alcaraz/`), points are in `cells[2]`, and only the first occurrence of each player should be stored (breakdown rows later in the table overwrite totals with tournament-specific points).
**Key lesson from Sprint 4b:** `atptour.com` blocks plain `requests` with 403 regardless of headers — the site is protected by Cloudflare/WAF. Use `cloudscraper` (drop-in replacement for `requests`) which handles the Cloudflare challenge automatically.
**Key lesson from Sprint 4b:** GitHub Pages + GitHub Actions cron is the simplest zero-cost pattern for a daily-updated static site — no server, no cloud bills, one secret. `workflow_dispatch` allows manual runs for testing before the cron fires. Lazy-import any cloud SDK at the function level (not module level) so the pipeline runs cleanly in environments without those packages installed.

## Sprint 6 — Data Enrichment & Model Upgrade — COMPLETE ✓

**Surface feature:** `src/agents/surface_agent.py` — ordered substring lookup (80+ ATP tournaments) maps `sport_key` → surface. Badge displayed in match card header. Surface context note appended to recommendations for clay/grass/indoor.

**H2H feature:** `src/agents/h2h_agent.py` — downloads 4 years of Sackmann CSVs at runtime, `lru_cache` prevents re-download within a run, excludes RET/W/O/DEF, fuzzy name matching (cutoff 0.82). Shown as compact bar between match header and player cards.

**Sentiment agent:** `src/agents/sentiment_agent.py` — Google News RSS + keyword scoring (no API key), `ThreadPoolExecutor` parallelizes 28+ players in ~4s. Flag (↑ In form / ⚠ Form concern) shown inline on player card with headline as tooltip.

**Logistic regression model:** `scripts/train_model.py` trains on 18,043 matches (2018–2024), serializes to `models/lr_model.json` (coefficients + scaler params). `src/agents/model_agent.py` applies the model with plain Python — no sklearn at inference time. CV accuracy 63.7% ± 0.5%.

**Key lesson from Sprint 6:** Serialize ML models as JSON (coefficients + scaler params), not as pickle files. JSON is human-readable, version-control friendly, and eliminates sklearn as a runtime dependency. Load and apply with `math.exp` + dot product — no framework needed.
**Key lesson from Sprint 6:** For symmetric binary classification (who wins a match has no inherent home/away), mirror each training example: create two rows per match (home=winner, label=1) and (home=loser, label=0). This prevents the model from learning a spurious home-field advantage.
**Key lesson from Sprint 6:** Log-compress skewed ratio features before training. `log(pts_A / pts_B)` is approximately normally distributed; raw `pts_A / pts_B` has extreme outliers that dominate gradient updates.
**Key lesson from Sprint 6:** `@lru_cache(maxsize=1)` on a zero-argument function is the simplest in-process cache. Downloading Sackmann CSVs once per pipeline run reduces H2H latency from ~4s per call to ~0s after the first match.

## Sprint 5 — LangGraph Agent Architecture — COMPLETE ✓

**Goal:** Refactor the linear pipeline into a proper coordinator → sub-agent graph.

**Deliverable:** `src/pipeline/coordinator.py` — `PipelineState` TypedDict + `StateGraph` with 4 nodes:
- `fetch_odds` → conditional edge (abort if no data / all in-play)
- `fetch_rankings` → conditional edge (retry ×2 on empty result, then fall through)
- `fetch_sentiment` → always runs; errors default to neutral
- `compute_predictions` → assembles final match dicts

`generate_html.py.run_pipeline()` is now a one-liner delegation to the coordinator.

**Key decision:** Do NOT introduce LangGraph in Sprint 3 or 4. Go live first, refactor second. ✓

**Key lesson from Sprint 5:** LangGraph `StateGraph` self-loops (conditional edge pointing back to the same node) are a clean retry pattern — increment a counter in state and route back until the counter threshold is reached. No external retry library needed.
**Key lesson from Sprint 5:** TypedDict state with `total=False` lets nodes add keys incrementally without needing to initialise all fields upfront. Use it as the graph's single shared context object.
**Key lesson from Sprint 5:** Keep node functions side-effect-free and returning `{**state, "new_key": value}` — this makes the graph trivially testable by calling nodes directly with mock state dicts.

## Panel privado (track record) — COMPLETE ✓

`generate_dashboard.py` lee `data/track_record.json` y genera un panel (1 unidad fija por parlay, cuota de Stake): beneficio, ROI, aciertos, curva acumulada, resultado por mes y acierto por rango de cuota. El workflow diario lo cifra con `staticrypt` (secret `DASHBOARD_PASSWORD`) y publica `panel.html` (pestañas Recomendaciones + Rendimiento, via `scripts/build_panel.py`). `generate_html.py` deja la web completa en `build/site.html` (gitignored) y `index.html` es solo una página neutra: la web completa nunca se publica sin cifrar. Si el secret no existe, el paso se salta: nunca se publica sin cifrar.

**Key lesson:** `staticrypt` pide confirmación interactiva si la contraseña tiene menos de 14 caracteres y se cuelga en CI — usar siempre `--short`. Fijar `--salt` para que "recordar contraseña" no caduque cada día.

## NBA player props (value finder) — IN PROGRESS

Método del vídeo de Derek (comparación de líneas): cuota justa de FanDuel sin margen vs cuota de Stake, misma línea; regla copiada de su feed (capturas de Derek): se listan todos los lados con EV positivo (≥0,3 %), ordenados por EV% de mayor a menor, mostrando Win% (prob. justa de FanDuel sin margen) y EV% = Win% × cuota Stake − 1, misma línea en ambas casas. El 54,34 % era solo el equilibrio del boleto de PrizePicks, NO un corte para Stake. El usuario quiere copiar su método, no "mejorarlo".
- `scripts/nba_stake_scraper.py` — Stake vía CDP (`slugFixture → swishGameCompetitorTeams → players → markets(statTypes:[player])`, endpoint `/_api/v1/graphql`). Necesita Chrome abierto en stake.com.
- `scripts/nba_fanduel.py` — FanDuel vía **Firecrawl** (`FIRECRAWL_API_KEY`), solo los partidos que Stake lista. Hay que desplegar los acordeones (`div[role=button][aria-expanded=false]` por `aria-label`) con una acción `executeJavascript`.
- `scripts/nba_pinnacle.py` — Pinnacle por su API pública de invitado (`guest.api.arcadia.pinnacle.com`, liga 487, funciona desde fuera de EE. UU., sin créditos). FanDuel y DraftKings dan 403 fuera de EE. UU. (por eso FanDuel va por Firecrawl); DraftKings por Firecrawl devuelve hitos (18+, 20+…) en vez de over/under y cuesta ~5 páginas por partido: descartado por ahora. La prob. justa es el promedio de las casas con esa misma línea.
- Pestaña NBA: campo de bankroll + apuesta sugerida (1 u = 1 %; 0,25 u, o 0,5 u si EV ≥ 3 %), botón "Apostada" y track record (beneficio, ROI, aciertos, pendientes). Todo en `localStorage` del navegador (clave `nba_tracker_v1`), con exportar/importar texto para cambiar de dispositivo; no hay servidor. Posible V2: liquidar apuestas solas con box scores.
- Combinadas de 3 (`scripts/nba_combos.py`) — reglas tras el análisis del 24/10 (el EV por sí solo no predijo el acierto; las piernas con Win% ≥ 54 % sí calibraron): piernas con Win% ≥ 54 % y EV > 0,5 %, solo partidos sin empezar, un jugador una sola vez y máx. 2 piernas por partido en todo el conjunto, cada pierna usada una vez. Se guarda un log de cuotas por tanda (`quotes`) para medir CLV, y `stake_opp` (cuota del otro lado) para comparar la probabilidad de Stake sin margen con la de las casas. Fase de prueba: 0,25 u por apuesta hasta acumular 5–7 días. Nunca se generan combinadas de seguimiento cuando ya no quedan partidos por jugar (evita picks a posteriori). Tres familias para comparar: probabilidad, valor y mixta (EV combo ≥ 20 %). 0,25 u por combinada. Cada día se guarda un snapshot local en `data/nba_history/<fecha>.json`; `scripts/nba_settle.py` liquida piernas y combinadas con box scores de ESPN (`site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=`), anula las piernas de quien no juega y escribe `data/nba_analysis.json` (calibración, por mercado/lado/EV/casas, familias, contexto de palizas) que se incluye en la pestaña NBA. El usuario quiere iterar la estrategia a partir de estos resultados.
- `scripts/nba_ev.py` → `data/nba_picks.json`; `scripts/nba_publish.py` encadena todo, cifra las apuestas en `data/nba_picks.enc` (openssl + `DASHBOARD_PASSWORD`) y hace push; el workflow `panel.yml` reconstruye `panel.html`. Los datos en bruto no se suben nunca.
- `panel.html` (privado, staticrypt) tiene 4 pestañas: Recomendaciones, Rendimiento, NBA, MMA. Lo construye `scripts/build_private.py` (daily.yml con `--from-build`, panel.yml desde `data/site.enc` + `data/nba_picks.enc`). La web completa solo existe en el repo cifrada (`data/site.enc`); `index.html` es un marcador neutro.
- Plan gratuito de Firecrawl: 1.000 créditos/mes; vigilar el gasto (`app.get_credit_usage()`).

**Key lesson:** al scrapear con Firecrawl una SPA, el contenido plegado no sale en el markdown: hay que ejecutar JS para desplegarlo; un selector inexistente aborta toda la llamada (`Element not found`), y `executeJavascript` no admite `
` literales (usar `String.fromCharCode(10)`).
**Key lesson:** no inventes alias de equipos: FanDuel usa `los-angeles-clippers`, un alias `la-clippers` rompió el emparejamiento.

## Sprint 6+ (Planned) — Data Enrichment & Model Upgrade

**Goal:** Improve prediction quality with richer data sources. Improvements go live immediately since the app is already deployed.

**Planned work:**
1. Add historical H2H data (Sackmann dataset → BigQuery)
2. Add surface/conditions features
3. Add news/sentiment agent
4. Upgrade ranking model to logistic regression
5. Add `docs/ML_ENGINEER.md` agent persona

## Sprint Session Protocol
At the start of ANY session where the user mentions a sprint, story, or task (e.g. "let's work on Sprint 4", "continue", "what's next"):
1. Read `SPRINT_PLANNING.md` immediately — before asking questions or writing code
2. Report back: current sprint, what's completed ✅, what's in progress 🔄, and the recommended next task
3. Propose the next subtask and ask for confirmation before starting
4. When a subtask is completed, update the checkbox in `SPRINT_PLANNING.md` before moving on

When working on sprint planning, story sizing, or backlog decisions, read `docs/PRODUCT_OWNER.md` first.

## Multi-Agent Routing
When working on ETL, data cleaning, or BigQuery tasks, ALWAYS read `docs/DATA_ENGINEER.md` first to adopt the Data Engineer persona and constraints.

## Git Workflow
Before finishing a task, ask for permission to stage changes and create a conventional commit (e.g., `feat: integrate GCS upload`).

**Doc update protocol:** Always update relevant `.md` files **before** committing — docs and code go in the same commit. Files to consider after every task: `CLAUDE.md` (key lessons, sprint status), `SPRINT_PLANNING.md` (checkboxes), `README.md` (current status section), and any `docs/` file relevant to the work done.

**IMPORTANT:** Before every commit or push, verify the active GitHub account is `elouelyt` by running `gh auth status`. Confirm `elouelyt` shows `Active account: true`. If it doesn't, alert the user and do not commit or push until they run `gh auth switch --user elouelyt`.