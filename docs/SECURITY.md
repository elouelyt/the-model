# Security Architecture

## API Key on the Frontend (Known Limitation)

The React frontend sends an `X-API-Key` header with every `POST /predict` request.
The key is **hardcoded in the Lovable source code** (`src/pages/Index.tsx`, line 35).

### Why it is hardcoded (not an env var)

Lovable's Secrets UI only supports runtime server-side secrets (e.g. Supabase keys).
It explicitly **rejects** `VITE_` prefixed variable names with the error:
> "VITE_ prefixed variables are build-time browser values and should be defined in .env files."

Lovable does not expose a `.env` file editor or a build-secrets panel on any plan tier.
There is no mechanism to inject `VITE_` vars into a Lovable-hosted build without
modifying source code directly. Hardcoding is therefore the only practical option for
this hosting platform.

### Why hardcoding is acceptable here

`VITE_` prefixed variables in Vite are **embedded into the compiled JavaScript bundle
at build time** regardless of how they are set. An env var and a hardcoded string are
**identical in the output bundle** — both are visible to anyone who opens
DevTools → Sources. There is zero security difference between the two approaches
for a public client-side React application.

The real protection lives on the server side:

| Control | Implementation |
|---|---|
| Strong key | 64-char hex key generated via `openssl rand -hex 32` |
| Server-side validation | FastAPI rejects any request without a valid `X-API-Key` |
| CORS restriction | Cloud Run only accepts requests from the Lovable frontend origin |
| Cost ceiling | Cloud Run capped at 3 max instances — limits blast radius of any abuse |
| Secrets in Secret Manager | `TENNIS_API_KEY`, `THE_ODDS_API_KEY` stored in GCP Secret Manager, not plain env vars |

### Low-value key = low risk

Even if the key is found in DevTools, the attacker can only call `POST /predict`,
which returns read-only tennis match predictions. No user data, no database writes,
no financial transactions. The cost blast radius is bounded by the 3-instance cap
and The-Odds-API's own rate limiting.

### Truly secure alternative (not implemented)

For apps where the API key must never be exposed, the pattern is a **backend proxy**:
- Frontend calls your own backend (no API key needed client-side)
- Backend holds the key server-side and forwards the request
- Adds latency and infrastructure complexity — not justified for a portfolio project

### Key rotation

If the key is ever compromised:
1. Generate a new key: `openssl rand -hex 32`
2. Update in GCP Secret Manager: `echo -n "<new_key>" | gcloud secrets versions add TENNIS_API_KEY --data-file=- --project=tennis-data-487809`
3. Redeploy Cloud Run to pick up the new secret version
4. Update the hardcoded key in Lovable `src/pages/Index.tsx` line 35 and republish

---

## Secrets Management

All server-side secrets are stored in **GCP Secret Manager** and injected into Cloud Run
at runtime via secret references — never as plain environment variables.

| Secret | Secret Manager Name | Used by |
|---|---|---|
| Tennis API key | `TENNIS_API_KEY` | FastAPI `X-API-Key` validation |
| The Odds API key | `THE_ODDS_API_KEY` | Odds ingestion pipeline |
| Gemini API key | `GEMINI_API_KEY` | Reserved — Gemini agent replaced by ATP scraper |

> `GEMINI_API_KEY` is retained in Secret Manager but is currently unused.
> The Gemini ranking agent was replaced by a live `atptour.com` scraper in Sprint 4.
> Remove this secret once Sprint 5 LangGraph refactor confirms it is not needed.
