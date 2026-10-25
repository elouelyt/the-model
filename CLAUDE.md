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
- `scripts/nba_bettingpros.py` — API de BettingPros (`api.bettingpros.com/v3`, cabecera `x-api-key` = `BETTINGPROS_API_KEY` en `.env`; clave facilitada por el usuario, nunca en el repo). `/events`, `/markets`, `/books`, `/offers?market_id=&event_id=a:b:c` (20 por página). Mercados: 156 puntos, 157 rebotes, 151 asistencias, 335 P+A, 336 P+R, 337 R+A, 338 PRA. Solo casas de referencia (FanDuel, DraftKings, Caesars, BetMGM, Novig, ProphetX); se excluyen apps DFS (PrizePicks, Underdog, Sleeper, Betr…) y mercados de predicción. Se descartan cuotas de más de ±400 (Novig/ProphetX devuelven -99900 si un lado no tiene liquidez) y líneas sin actualizar en 4 h. FanDuel solo cubre ~42 % de las líneas de Stake; Firecrawl lo complementa. **Cupo de peticiones:** la clave gratuita del usuario permite **50 peticiones/día**, respuestas truncadas (20 por página) y solo uso personal no comercial (ver su panel de BettingPros). Una pasada completa son ~37 peticiones: se gasta una vez al día, en la tanda tardía (`nba_publish.py` solo llama a BettingPros si son las 21:00 o más, o con `--bp`); hay contador diario (`data/bettingpros_usage.json`, tope 45), caché de 20 min y ids de casas fijos. No relanzar en bucle ni probar sin necesidad. El "Consensus" (id 0) es la media de TODAS las casas (incluye blandas y fantasy); se guarda como `cons_prob` solo para comparar su Brier con el de nuestra media de casas de referencia (`consensus_check` en el análisis).
- `scripts/nba_pinnacle.py` — Pinnacle por su API pública de invitado (`guest.api.arcadia.pinnacle.com`, liga 487, funciona desde fuera de EE. UU., sin créditos). FanDuel y DraftKings dan 403 fuera de EE. UU. (por eso FanDuel va por Firecrawl); DraftKings por Firecrawl devuelve hitos (18+, 20+…) en vez de over/under y cuesta ~5 páginas por partido: descartado por ahora. La prob. justa es el promedio de las casas con esa misma línea.
- Pestaña NBA: campo de bankroll + apuesta sugerida (1 u = 1 %; 0,25 u, o 0,5 u si EV ≥ 3 %), botón "Apostada" y track record (beneficio, ROI, aciertos, pendientes). Todo en `localStorage` del navegador (clave `nba_tracker_v1`), con exportar/importar texto para cambiar de dispositivo; no hay servidor. Posible V2: liquidar apuestas solas con box scores.
- **Combinadas fijas:** `freeze_combos()` mantiene en el panel las combinadas ya mostradas hoy mientras sus 3 partidos no hayan empezado (no desaparecen aunque se muevan las cuotas); solo se añaden nuevas que no reutilicen pierna ni jugador. Antes se recalculaban en cada tanda y las apostadas desaparecían.
- Combinadas de 3 (`scripts/nba_combos.py`) — reglas tras el análisis del 24/10 (el EV por sí solo no predijo el acierto; las piernas con Win% ≥ 54 % sí calibraron): piernas con Win% ≥ 54 % y EV > 0,5 %, solo partidos sin empezar, un jugador una sola vez y máx. 2 piernas por partido en todo el conjunto, cada pierna usada una vez. Se guarda un log de cuotas por tanda (`quotes`) para medir CLV, y `stake_opp` (cuota del otro lado) para comparar la probabilidad de Stake sin margen con la de las casas. Fase de prueba: 0,25 u por apuesta hasta acumular 5–7 días. Nunca se generan combinadas de seguimiento cuando ya no quedan partidos por jugar (evita picks a posteriori). Tres familias para comparar: probabilidad, valor y mixta (EV combo ≥ 20 %). 0,25 u por combinada. Cada día se guarda un snapshot local en `data/nba_history/<fecha>.json`; `scripts/nba_settle.py` liquida piernas y combinadas con box scores de ESPN (`site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=`), anula las piernas de quien no juega y escribe `data/nba_analysis.json` (calibración, por mercado/lado/EV/casas, familias, contexto de palizas) que se incluye en la pestaña NBA. El usuario quiere iterar la estrategia a partir de estos resultados.
- **Línea base protegida (NO borrar ni reescribir):** `data/nba_history/2026-10-23.json` (slate del 23/10, ya liquidado: 119 piernas simples, 37,8 % de acierto, 38 combinadas con 2 acertadas) y copias originales en `data/nba_baseline/`. Las reglas se cambiaron el 24/10 (win ≥ 54 %, ≥ 2 casas, jugador único, tope por partido, 0,25 u) y cada día nuevo se compara contra esa base (`days` en `nba_analysis.json`). Un slate pertenece a la fecha en que empiezan sus partidos (las tandas de madrugada cuentan para el día anterior). Copia cifrada de todo el historial en `data/nba_history.enc`. Combinadas de seguimiento extra: reglas antiguas (`valor_ev`, `prob_ev`) y `pura`, solo papel. Las favoritas sin EV (`extra`) se guardan para comparar por win%.
- **Enlaces "Abrir en Stake"** (pestaña NBA): el talón de Stake guarda las selecciones en `sessionStorage['betPrePlacementStore']` como `{id:`${outcomeId}_${over|under}`, type:'swish', outcomeId, stake:0, odds, acceptedOdds, eventId, betType, atBat:false, sportInfo:{...basketball}, analyticsProperties:{isPromotionBet:false}, fetching:false, fixtureStatus:'active'}`. `outcomeId` = `id` de la línea (`lines{id}` de `swishGameCompetitorTeams…markets`) y `eventId` = `fixture.id` (NO `swishGame.id`). Stake admite combinadas ("Apuesta Múltiple") de props de partidos distintos. `nba_stake_scraper.py` guarda `outcome_id`/`event_id` en cada fila; `generate_nba.stake_url()` crea `https://stake.com/es/sports/basketball#oj=<base64url json [{o,e,t,p}]>`; la extensión `stake-extension/` (content script en `document_start`, solo permiso stake.com, sin red, no apuesta nunca) escribe el talón al cargar. Validado en un Chrome real con 3 piernas de 3 partidos. Lección: probar con `Page.addScriptToEvaluateOnNewDocument` y navegar desde OTRA página (un cambio solo de fragmento no recarga). Pruebas: `nba_combos.py --no-snapshot` para no escribir historial.
- **Stake Bet Guide** (`stake-guide/`): extensión nueva (separada de `stake-extension/`) con panel lateral de Chrome (lista las combinadas, descifra `data/nba_picks.enc` desde raw.githubusercontent con la contraseña del panel, WebCrypto: openssl `Salted__`, PBKDF2-SHA256 10000 iter, AES-CBC, gzip) y `guide.js` en stake.com que resalta con la API `CSS.highlights` (sin tocar el DOM; 0 mutaciones medidas) pestaña "Apuestas al Jugador" → jugador (`Nombre (SG)`) → mercado (`Puntos`, `Rebotes`, `Asistencias`, `Puntos + Rebotes`, …) → línea (naranja si no es la buscada, verde la opción de la lista) → `Sobre`/`Debajo` con la cuota. El usuario hace todos los clics y el scroll; la extensión no mueve la página. Probado en un Chrome real simulando `chrome.storage`; no probado cargada como extensión ni con sesión iniciada. Los textos de Stake están en español (`Sobre`/`Debajo`).
- `scripts/nba_ev.py` → `data/nba_picks.json`; `scripts/nba_publish.py` encadena todo, cifra las apuestas en `data/nba_picks.enc` (openssl + `DASHBOARD_PASSWORD`) y hace push; el workflow `panel.yml` reconstruye `panel.html`. Los datos en bruto no se suben nunca.
- `panel.html` (privado, staticrypt) tiene 4 pestañas: Recomendaciones, Rendimiento, NBA, MMA. Lo construye `scripts/build_private.py` (daily.yml con `--from-build`, panel.yml desde `data/site.enc` + `data/nba_picks.enc`). La web completa solo existe en el repo cifrada (`data/site.enc`); `index.html` es un marcador neutro.
- Plan gratuito de Firecrawl: 1.000 créditos/mes; vigilar el gasto (`app.get_credit_usage()`).

**Key lesson:** al scrapear con Firecrawl una SPA, el contenido plegado no sale en el markdown: hay que ejecutar JS para desplegarlo; un selector inexistente aborta toda la llamada (`Element not found`), y `executeJavascript` no admite `
` literales (usar `String.fromCharCode(10)`).
**Key lesson:** no inventes alias de equipos: FanDuel usa `los-angeles-clippers`, un alias `la-clippers` rompió el emparejamiento.

## NBA — guía para retomar (estado, reglas de trabajo y pendientes)

**Cómo trabaja el usuario (respetar siempre):**
- Ejecutar los cambios rutinarios sin pedir permiso; parar solo si hay pérdida real de datos o algo irreversible.
- "Hazlo como Derek": copiar su método, no "mejorarlo". Los cambios de reglas se prueban en PARALELO (familias de seguimiento en papel) sin tocar las combinadas apostables.
- No borrar los resultados del día: sirven para comparar con el siguiente. La línea base del 23/10 es intocable.
- Cuando pide ideas: investigar, probar en un Chrome real y DEMOSTRAR (capturas, medidas) antes de proponer. No ofrecer opciones sin probar.
- Ser honesto sobre lo que se sabe y lo que no (p. ej. qué detecta Stake: nadie fuera de Stake lo sabe). No ayudar a ocultar herramientas a Stake (no renombrar marcas para disimular, no simular clics).
- Responde en español, sin rodeos.

**Rutina diaria:**
- Tandas a las 19:00 y 22:00 (hora local) con Chrome de depuración abierto en Stake (`scripts/start_chrome_debug.bat`): `scripts/nba_publish.py` (BettingPros solo en la tardía, cupo 50/día). `--skip-fetch` re-publica sin volver a leer cuotas.
- Mañana a las 10:00 (`nba-resultados`): `scripts/nba_settle.py` y analizar el día contra la línea base del 23/10 (`days`, familias, calibración, CLV, `consensus_check`, y la familia `prudente`). El usuario dice "analiza" para pedirlo.
- Los workflows `panel.yml`/`daily.yml` construyen con el código del REPO, no con el local: hay que hacer commit+push del generador ANTES de lanzar `gh workflow run panel.yml` (error ya cometido). `panel.yml` solo se dispara solo cuando cambia un `.enc`.

**Combinadas (estado actual):**
- Las bettable se mantienen fijas mientras sus partidos no empiecen (`freeze_combos`); se rellena `fixture` en cada pierna (enlace al partido) desde `data/nba_stake_cache.json`.
- No hay regla de cuota mínima (ni por pierna ni por combinada): la rentabilidad se mide con EV = prob. × cuota − 1. Decisión: no añadirla sin datos (en PrizePicks el pago es fijo y por eso el listón es un % mínimo por pierna ≈ 54-55 %; en Stake cada cuota lleva su margen y se multiplica en la combinada).
- **Prueba en paralelo `prudente`** (desde 25/10): mismas reglas pero con `fair_prob − 0.015` por pierna (`SHRINK` en `nba_combos.py`), solo papel (seguimiento). Si una combinada ya la eligen otras reglas, solo se añade la etiqueta `prudente`. Medir tras 5–7 días de resultados si habría mejorado el acierto/ROI frente a las actuales antes de cambiar nada.
- Ideas ya habladas y NO aplicadas: subir Win% mínimo a 56 %, combinadas de 2 o apuestas simples, tope de cuota mínima, mostrar piernas sueltas en el panel lateral cuando la combinada ya empezó.

**Páginas de Stake (estructura medida en un Chrome real, para resaltador/scrapers):**
- Partido: `https://stake.com/es/sports/basketball/usa/nba/<fixture-slug>` (el `slug` viene de `fixtureList`; verificado). Cambiar de pestaña NO cambia la URL (no hay enlace directo a "Apuestas al Jugador"). Los props de jugador NO existen en el DOM hasta pulsar esa pestaña, así que los enlaces `#:~:text=` no funcionan.
- Pestaña **Apuestas al Jugador**: campo "Buscar jugador" (filtra al jugador), lista por equipo con `Nombre (SG)` (posición entre paréntesis); al pulsar un jugador se despliegan filas con: nombre del mercado (`Puntos`, `Rebotes`, `Asistencias`, `Puntos + Rebotes`, `Puntos + Asistencias`, `Asistencias + Rebotes`, `Puntos + Asistencias + Rebotes`, además de triples, robos, bloqueos…), la línea (con desplegable de otras líneas, p. ej. 1.5/2.5/3.5) y botones `Sobre`/`Debajo` con la cuota (coma decimal).
- La API/Web carga sin sesión: el Chrome de depuración no tiene la cuenta iniciada (solo lectura de cuotas; no probado con sesión).
- Probar interacciones con `Input.dispatchMouseEvent` en coordenadas reales; un clic de prueba puede dejar seleccionado un botón en el talón de esa pestaña (deseleccionar).

**Extensiones (dos, separadas):** `stake-extension/` (rellena el talón desde `#oj=`; la más intrusiva) y `stake-guide/` (panel lateral + `guide.js`: solo lee y pinta con `CSS.highlights`, sin tocar el DOM, sin scroll automático; el usuario hace todos los clics). Zip listo en `build/stake-guide.zip` (`build/` no se sube). Ver los README de cada carpeta. Riesgo de detección: no hay garantías; los términos de Stake (cl. 17.3 sobre software que analiza la información mostrada; 4.19–4.22 cierre y anulación/retención de importes a su criterio; 14.4 VPN solo si es para saltar bloqueos por país) están en https://stake.com/es/policies/terms.

**Pendiente / ideas abiertas:**
- Panel lateral solo en texto (sin `guide.js`) como versión de menor riesgo, o un interruptor para activar las marcas.
- Registro de apuestas pegando la ficha de "Mis Apuestas" de Stake (en vez del botón "Apostada").
- Aviso al móvil al publicar cada tanda y 30 min antes del primer partido; chequeo de cuotas justo antes de apostar.
- Investigar por qué la tarea de tenis de las 07:07 deja `data/stake_cache.json` de ayer.
- Contar una sola combinada por conjunto de piernas en las estadísticas por familia (hoy una misma pierna repetida pesa más).
- Extensión de superposición con Win%/EV% dentro de Stake: descartada por riesgo (modifica la página).

**Lecciones de herramientas:**
- En este entorno los `heredoc` con comillas complejas fallan en el shell: crear los archivos con la herramienta de escritura o con scripts Python.
- Probar el generador con `python scripts/nba_combos.py --no-snapshot` (no escribe historial) y el código de una extensión inyectándolo por CDP con `chrome.storage` simulado.

## NFL player props (misma metodología que NBA) — `nfl/` (desde 25/10/2026)

Pipeline paralelo e independiente de NBA (no toca sus scripts): `nfl/nfl_stake_scraper.py` (Stake NFL por CDP, mismos GraphQL con `sport:"american-football", category:"usa", tournament:"nfl"`;
9 mercados: yardas de pase/carrera/recepción, recepciones, acarreos, pases intentados/completados, TD de pase, intercepciones; ~9.000 líneas por tanda incl. alternativas, `balanced` = principal),
`nfl/nfl_pinnacle.py` (API pública de invitado, liga 889; ~510 líneas, 477 con la misma línea que Stake; única casa de referencia por ahora), `nfl/nfl_ev.py` (prob. justa sin margen vs cuota Stake),
`nfl/nfl_combos.py` (reutiliza `nba_combos.build_combos`/`freeze_combos` con `min_books=1`), `nfl/nfl_settle.py` (ESPN `football/nfl`; reutiliza `nba_settle.analyse()` apuntado a `nfl/data/nfl_history`; pierna anulada si el jugador no aparece en ninguna categoría del box score),
`nfl/nfl_publish.py` (cadena completa, cifra `data/nfl_picks.enc` y `data/nfl_history.enc`, commit+push; `--no-push` solo refresca y archiva), `nfl/generate_nfl.py` (carga el código de `generate_nba.py` sustituyendo textos/constantes: la pestaña NFL hereda las mejoras de NBA).
`scripts/build_private.py` añade la pestaña **NFL** (tolerante a errores) y `panel.yml` se dispara también con `data/nfl_picks.enc`. Datos locales en `nfl/data/` (gitignored); archivo permanente por tanda en `nuevas_ideas/archive/nfl_batches`.
Estado 25/10: pestaña publicada en modo prueba (aviso en la pestaña); sin liquidar aún. NFL tiene partidos domingo, lunes y jueves (hora UTC ~17:00, 20:05, 20:25, 00:20 / jueves 00:15).
**Pendiente NFL:** tarea programada (el clasificador bloqueó crear `nfl-daily` y `nfl-datos`; el usuario debe permitirlo o crearla: `python nfl/nfl_publish.py` en 09:30, 16:30 y 20:30 con Chrome de depuración abierto en Stake);
BettingPros NFL (cupo 50/día compartido con NBA) y FanDuel (Firecrawl) como 2.ª/3.ª casa; mercados de TD; nombres en español de los mercados de Stake NFL para `stake-guide/guide.js` (hoy solo NBA) y enlace "Rellenar talón" (la extensión antigua escribe talón de baloncesto; en NFL está desactivado);
universo/calibración de NFL como en `nuevas_ideas/universe.py`; reglas propias (límites por partido, correlación QB-receptor, pesos por mercado) tras 5-7 días de datos.
Lección NBA aplicada: las jugadas con EV muy alto y probabilidad < 54 % (sobre todo Under) fallaron en NBA; en NFL empezar fiándose de las combinadas con piernas de >= 54 %.

## Pestaña "Combinadas" (NBA + NFL), consenso, extensión de 3 secciones y seguimiento NFL (25/10/2026)

- **Combinadas arriba:** en las pestañas NBA y NFL las combinadas apostables salen justo bajo el título; el seguimiento en papel va tras la tabla (`generate_nba.py`, NFL lo hereda).
- **Consenso de BettingPros** visible en la tabla ("Consenso BP", con la antigüedad) y en las piernas de las combinadas (`BP xx %`). Es solo informativo (media de TODAS sus casas, no entra en el EV).
  `nba_ev.py` lo muestra hasta 30 h (`CONS_MAX_AGE_H`) aunque la casa ya no valga como referencia (6 h). BettingPros se consulta UNA vez al día en la primera tanda desde las 17:00 locales
  (`nba_publish.py`, caché de 7 h en `nba_bettingpros.py`); el cupo (45/50 diarias) cubre asistencias, rebotes y puntos, no los mercados combinados (el 25/10: 69 de 151 jugadas). NFL no tiene consenso (sin cupo).
- **Pestaña Combinadas** (al lado de MMA): `scripts/mix_combos.py` mezcla piernas NBA (>= 2 casas) y NFL (>= 1) con el motor de `nba_combos.py` (solo combinadas que mezclan ambos deportes, con `freeze_combos`), `scripts/mix_settle.py` liquida cada pierna con su ESPN,
  `scripts/mix_publish.py` cifra `data/mix_picks.enc` y `data/mix_history.enc` (lo llaman `nba_publish.py` y `nfl_publish.py`), `generate_combos.py` (reutiliza `generate_nba.py`) construye la pestaña con tres bloques: Mezcla NBA+NFL, Mejores de NBA, Mejores de NFL; `build_private.py` la añade (tolerante a errores) y `panel.yml` se dispara con `data/mix_picks.enc`.
- **NFL = motor NBA:** `nfl/nfl_combos.py` ejecuta `nba_combos.main()` con las rutas de NFL (solo cambia `MIN_BOOKS = 1` hasta tener 2.ª casa); `nba_combos.py` ganó `STAKE_CACHE`/`ANALYSIS` y `min_books=None` (salida de NBA verificada idéntica).
- **Extensión `stake-guide` 1.2.0:** panel lateral con tres secciones NBA / NFL / Total; enlaces por deporte; `guide.js` acepta posiciones NFL y compara el mercado sin acentos. Nombres de Stake NFL: Yardas por Pases, Pases Completados, Intentos de pases, Pases de Touchdowns, Intercepciones, Yardas por acarreo, Intentos de acarreo, Yardas de recepción, Recepciones.
- **Seguimiento NFL (como NBA):** liquidación y análisis en `nfl/nfl_settle.py`; las ideas en papel 03, 06, 07, 08 y 09 corren también sobre NFL (`IDEAS_SPORT=nfl`, historiales `ideas/*/history_nfl`); `nuevas_ideas/nfl_universe.py` y el archivo `archive/nfl_batches`; `settle_ideas.py` añade calibración NFL y de las combinadas mezcladas a `RESULTADOS.md`.
- **Tareas programadas (resuelto 25/10):** el clasificador de permisos bloqueó crear `nfl-daily` y editar tareas con la herramienta; con permiso explícito del usuario se editaron a mano los `SKILL.md` de `nba-daily-tarde` y `nba-daily` (paso 3: `python nfl/nfl_publish.py` tras la tanda de NBA, en el mismo Chrome) y `nba-resultados` (`nfl_settle.py` + `mix_settle.py`). No hay tarea de NFL propia: NFL y las mezcladas se publican a las 19:04 y 22:09 dentro de las tareas de NBA.

## Nuevas ideas (pruebas en papel) — `nuevas_ideas/`

El usuario pidió (25/10/2026) que **todo cambio nuevo se pruebe en otra carpeta, sin tocar lo que funciona**, con backtesting de 5-7 días,
y que se anote en el índice `nuevas_ideas/NUEVAS_IDEAS.md` (añadir, nunca borrar). Cada idea es `nuevas_ideas/ideas/NN_nombre/run.py` y genera
combinadas de papel con los datos de producción (solo lectura); `nuevas_ideas/settle_ideas.py` las liquida con ESPN (reusa `scripts/nba_settle.py`)
y escribe `nuevas_ideas/RESULTADOS.md`. Tareas programadas nuevas: `nuevas-ideas-tanda` (19:35 y 22:35) y `nuevas-ideas-resultados` (~10:40).
Ideas: 01 `prudente` (en producción como familia de papel), 02 SGM mismo partido con el precio de Stake (consulta `calculateSwishCustomBet`),
03 unders, 04 minutos, 05 sinergias (descartada con datos), 06 win56, 07 dos piernas, 08 simples. Leer `NUEVAS_IDEAS.md` antes de tocar nada de esto.
Los historiales (`ideas/*/history`, `candidates`, `data`) son locales (`.gitignore`).

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