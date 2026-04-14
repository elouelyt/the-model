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

## CURRENT FOCUS: Sprint 4 — Deploy to GCP + mateogrisales.com

**Goal:** Go live as fast as possible with the working ranking-based model. A live public demo is more valuable for the portfolio than a local Streamlit app.

**Story 1 — COMPLETE ✓**
- `api/main.py`: FastAPI app, `POST /predict` + `GET /health`, `X-API-Key` auth, Pydantic response models, CORS configurable via env var
- `Dockerfile`: `python:3.12-slim`, built and pushed to Artifact Registry via **Cloud Build** (no local Docker needed)
- Cloud Run deployed **privately** (`--no-allow-unauthenticated`) in `us-central1` — never exposed directly to the internet
- **API Gateway** (`tennis-gateway`) deployed as the public-facing layer using `api-gateway.yaml` (OpenAPI spec)
- `api-gateway-invoker` service account holds `roles/run.invoker` on Cloud Run; gateway authenticates automatically
- `X-API-Key` auth validated by FastAPI — gateway passes it through, does not validate at gateway layer
- **Public gateway URL:** `https://tennis-gateway-agmlnd9p.uc.gateway.dev`
- **Cloud Run URL (private):** `https://tennis-api-er2jgzyldq-uc.a.run.app`

**Story 2 — IN PROGRESS 🔄**
- React app scaffolded in Lovable — clay orange (#E8650A) design, Roland Garros inspired
- `POST /predict` wired with `X-API-Key` header (hardcoded `local-test-key` temporarily for testing)
- CORS preflight (`OPTIONS /predict`) added to `api-gateway.yaml` — gateway config `tennis-api-config-v3` deployed
- Cloud Run `CORS_ORIGINS` set to Lovable preview domain: `https://fae197c3-a5e9-4e2e-b4c6-c77f45c87b38.lovableproject.com`
- **Lovable preview confirmed working** — Monte Carlo Masters matches loading with predictions

**Remaining work (Stories 3–5):**
1. Configure CORS on Cloud Run to allow final frontend origin only (not preview URL)
2. Deploy live at `tennis.mateogrisales.com`
3. Move secrets from plain Cloud Run env vars → GCP Secret Manager (Story 4 hardening)
4. Weekly Claude Code cost review agent (Story 5)

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

## Sprint 5 (Planned) — LangGraph Agent Architecture

**Goal:** Refactor the linear pipeline into a proper coordinator → sub-agent graph. LangGraph provides the routing and fallback infrastructure needed before adding more data sources in Sprint 6.

**Trigger:** Introduce LangGraph when the pipeline stops being linear — i.e., when the coordinator needs to make routing decisions, not just call functions in order.

**Planned work:**
1. Introduce LangGraph as the coordinator layer
2. Refactor sub-agents (odds, rankings, model, explanation) into LangGraph nodes
3. Add retry/fallback logic (e.g., ranking fetch fails → use cached data)
4. Conditional routing based on data availability or confidence thresholds

**Key decision:** Do NOT introduce LangGraph in Sprint 3 or 4. Go live first, refactor second.

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

**IMPORTANT:** Before every commit or push, verify the active GitHub account is `mateotenis98` by running `gh auth status`. Confirm `mateotenis98` shows `Active account: true`. If it doesn't, alert the user and do not commit or push until they run `gh auth switch --user mateotenis98`.