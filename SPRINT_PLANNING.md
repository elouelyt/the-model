# Tennis AI Platform - Sprint Planning

> **Note:** This is a living document (Agile workflow). Dates, hours, and specific technologies may be adapted as the project evolves.

## Phase 1: GCP Data Pipeline

| Sprint | Primary Objective | Key Tasks | Functional Deliverable | Est. Hours | Dates | Status |
|---|---|---|---|---|---|---|
| **Sprint 1** | Raw Data Ingestion (Data Lake) | 1. Set up GCP project & Service Account. 2. Write Python script to extract The-Odds-API. 3. Save raw JSONs to GCS. | `extract_odds.py`, `requirements.txt`, `.env.example` | 5–7 hrs | Fri Mar 6–Wed Mar 18 | ✅ Done (4h 30m) |
| **Sprint 2** | ETL & Data Warehousing (BigQuery) | 1. Read JSON from GCS. 2. Flatten nested structure with Pandas. 3. Load structured data into BigQuery. | `transform.py`, `etl_gcs_to_bq.py`, confirmed schema in `docs/MIAMI_OPEN_SCHEMA.md` | 8–10 hrs | Fri Mar 20–Mon Mar 23 | ✅ Done (2h 50m) |

---

## Phase 2: Prediction Engine + UI (MVP)

| Sprint | Primary Objective | Key Tasks | Functional Deliverable | Est. Hours | Dates | Status |
|---|---|---|---|---|---|---|
| **Sprint 3** | End-to-End Prediction MVP | ✓ 1. Dynamic ATP sport key discovery via `/v4/sports/`. ✓ 2. `raw_implied` + `true_implied` columns in `transform.py`. ✓ 3. `data/processed/` CSV output for local sandbox. ✓ 4. Build ranking agent (Gemini Flash + web search) — refactored to accept exact player names from odds API, eliminating name-matching ambiguity. ✓ 5. Build ranking-based probability calculator. ✓ 6. Build comparison & recommendation logic. ✓ 7. Filter in-play matches (`filter_upcoming()`) — live odds reflect score, not pre-match probability. ✓ 8. Wire into local Streamlit UI (`app.py`). | Working local demo: pipeline fetches live ATP odds, filters in-play matches, fetches rankings via Gemini, computes probabilities, displays match cards with value bet signals | 10–12 hrs | Mon Mar 23–Wed Mar 25 | ✅ Done (4h 50m) |
| **Sprint 4** | Deploy to GCP + mateogrisales.com | 1. Expose prediction pipeline as GCP Cloud Run API. 2. Build minimal React UI in Lovable. 3. Connect frontend to backend API. 4. Deploy live at mateogrisales.com. | Live public demo at mateogrisales.com with the ranking-based model | 8–10 hrs | TBD | 🔄 In Progress |
| **Sprint 5** | LangGraph Agent Architecture | 1. Introduce LangGraph as coordinator layer. 2. Refactor sub-agents (odds, rankings, model, explanation) into LangGraph nodes. 3. Add retry/fallback logic (e.g. ranking fetch fails → cached data). 4. Conditional routing based on data availability or confidence thresholds. | LangGraph coordinator replacing linear Python orchestration; stateful multi-agent graph | 10–12 hrs | TBD | 📅 Planned |
| **Sprint 6** | Data Enrichment & Model Upgrade | 1. Add historical H2H data (Sackmann dataset → BigQuery). 2. Add surface/conditions features. 3. Add news/sentiment agent. 4. Upgrade ranking model to logistic regression. 5. Add `docs/ML_ENGINEER.md` agent persona. | Enriched predictions, trained baseline model — improvements go live immediately | 12–15 hrs | TBD | 📅 Planned |
| **Sprint 7** | Polish & React UI Upgrade | 1. Improve React UI in Lovable (match selection, visualization, recommendation display). 2. Add authentication/rate limiting to backend. 3. Leverage LangGraph checkpointing for async prediction requests. | Polished public demo at mateogrisales.com | 8–10 hrs | TBD | 📅 Planned |

---

## Sprint 4 — Detail

> **Goal:** Go live as fast as possible. A live public demo is more valuable for the portfolio than a local Streamlit app.
> **Decision:** Cloud Run over Cloud Functions — Gemini Flash API call latency + future LangGraph refactor make Cloud Run the right fit.

### Story 1 — Backend API (Cloud Run + API Gateway)
**AC-What:** A `POST /predict` request to the public API Gateway URL returns a JSON array of pre-match ATP matches with model probability, raw implied probability, and value signal for each player.
**AC-Rule:** Only pre-match matches returned — `filter_upcoming()` must be applied. Cloud Run must remain private — never exposed directly to the internet. Public access is via API Gateway only.
**AC-How-critical:** FastAPI app must return structured JSON (not HTML). Dockerfile must not copy `.env` into the image. Cloud Run requires IAM auth — `api-gateway-invoker` service account is the only invoker. `X-API-Key` auth is validated by FastAPI, not the gateway.

**Key architecture decision:** Cloud Run kept private due to `grisalogic.com` org policy (`iam.allowedPolicyMemberDomains`) blocking `allUsers` IAM binding. API Gateway fronts Cloud Run using service account `api-gateway-invoker` — the standard enterprise pattern for exposing private Cloud Run services.

- [x] Wrap pipeline logic into a FastAPI app (`api/main.py`) with a `POST /predict` endpoint
- [x] Write `Dockerfile` and validate image builds and runs locally
- [x] Build and push image to GCP Artifact Registry via Cloud Build (no local Docker needed)
- [x] Deploy Cloud Run service (private, `--no-allow-unauthenticated`, `us-central1`)
- [x] Create `api-gateway-invoker` service account with `roles/run.invoker` on the Cloud Run service
- [x] Deploy GCP API Gateway (`tennis-gateway`) with OpenAPI spec (`api-gateway.yaml`) as public-facing layer
- [x] Smoke test full chain: API Gateway → Cloud Run → prediction pipeline
- **Public gateway URL:** `https://tennis-gateway-agmlnd9p.uc.gateway.dev`
- **Cloud Run URL (private):** `https://tennis-api-er2jgzyldq-uc.a.run.app`

### Story 2 — Frontend (Lovable)
**AC-What:** A visitor to the frontend URL sees a list of current ATP pre-match matches, each with both players, their value signal (value bet / marginal / no bet), model probability, and bookmaker implied probability.
**AC-Rule:** UI must handle the case where no pre-match matches are available (show a friendly empty state, not a crash).
**AC-How-critical:** API call must include the API key in the request header — do not expose it in client-side JS as a plain string; use an environment variable in Lovable.

- [x] Design minimal UI layout: match cards, value signal badge, odds table
- [x] Scaffold React app in Lovable — clay orange (#E8650A), Roland Garros inspired, tennis ball spinner
- [x] Wire `POST /predict` API call with loading and error states
- [x] Fix CORS preflight — add `OPTIONS /predict` to `api-gateway.yaml`, deploy `tennis-api-config-v3`
- [x] Fix ranking agent — remove Google Search grounding (gemini-2.5-flash SDK incompatibility), model training data sufficient
- [x] Confirm end-to-end working in Lovable preview — Monte Carlo Masters predictions loading
- [x] Fix stale rankings — replace Gemini agent with live `atptour.com` scraper (Alcaraz now correctly #1)

### Story 3 — Integration & Go Live
**AC-What:** Visiting `tennis.mateogrisales.com` loads the React app and successfully fetches and displays live predictions.
**AC-Rule:** CORS must only allow the production frontend origin — not a wildcard `*`.
**AC-How-critical:** API key auth must be validated server-side on Cloud Run before the pipeline executes — a request without a valid key must return 401.

- [x] Configure CORS on Cloud Run to allow frontend origin — `CORS_ORIGINS` set to `https://orange-court-ai.lovable.app,https://tennis.mateogrisales.com`
- [x] Add API key auth to Cloud Run endpoint (not open to the public) — validated by FastAPI `_require_api_key` dependency
- [x] Point subdomain (`tennis.mateogrisales.com`) to Lovable frontend — DNS configured in GoDaddy, propagation pending (up to 72h)
- [ ] End-to-end smoke test on production URL — pending DNS propagation

### Story 4 — Hardening (Definition of Done)
**AC-What:** The deployed app is observable — errors in the prediction pipeline appear in Cloud Logging, cost overruns trigger email alerts before they grow, and the README documents the live URL and how to redeploy.
**AC-Rule:** No secrets in plain env vars anywhere in the deployed stack. No unbounded Cloud Run scaling. Budget alerts must actually reach a human via email.
**AC-How-critical:** Cloud Logging must capture unhandled exceptions from the FastAPI app, not just HTTP access logs. Budget `notificationsRule` must not be empty.

- [x] Move `TENNIS_API_KEY` and `THE_ODDS_API_KEY` and `GEMINI_API_KEY` from plain Cloud Run env vars to GCP Secret Manager — wire via Cloud Run secret references
- [ ] Verify Cloud Logging captures errors from the prediction pipeline
- [ ] Update `README.md` with live URL and deployment instructions
- [x] Fix GCP budget alert: scope to `tennis-data-487809` only + attach email notification channel so alerts actually fire
- [x] Cap Cloud Run max instances to 3 — hard ceiling against traffic attacks
- [x] Add `docs/COST_CONTROLS.md` documenting all cost protection measures

### Story 5 — Weekly Cost Review Agent
**AC-What:** A scheduled Claude Code agent runs weekly, checks current GCP spend and Cloud Run metrics, and flags anomalies with suggested fixes.
**AC-Rule:** Agent must use `gcloud` to pull live data — not rely on memory or cached state.
**AC-How-critical:** Agent output must be actionable — not just "costs are high" but specific resources and commands to fix.

- [ ] Configure scheduled Claude Code agent (weekly cadence)
- [ ] Agent checks: current spend vs budget, Cloud Run request counts, error rates, active instances
- [ ] Agent reports anomalies and suggests specific `gcloud` remediation commands

---

## Future Backlog (Post-MVP)
- Upgrade ML model to XGBoost / ensemble
- Add weather/altitude/conditions data source
- Add UTR ratings (requires paid API access)
- Pre-compute nightly predictions and cache in BigQuery
- Model performance tracking and retraining pipeline
- Vertex AI integration for model hosting
- **Cost kill switch:** Budget alert → Pub/Sub topic → Cloud Function → set Cloud Run `max-instances=0` automatically when spend threshold is crossed. Currently not worth the complexity — `X-API-Key` auth + 3 instance cap + email alerts are sufficient for portfolio traffic.
