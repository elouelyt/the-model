// Side panel: downloads the encrypted picks (openssl AES-256-CBC + PBKDF2-SHA256 + gzip), decrypts them here with the panel password and
// lists the bettable combos in three sections: NBA, NFL and Total (mixed NBA+NFL). Picking a leg stores it as the target and opens that
// game on Stake in the SAME tab (the betslip lives in each tab's sessionStorage).
const RAW = "https://raw.githubusercontent.com/elouelyt/the-model/main/data/";
const SECTIONS = {
  nba: { file: "nba_picks.enc", label: "NBA", combos: (d) => d.combos || [] },
  nfl: { file: "nfl_picks.enc", label: "NFL", combos: (d) => d.combos || [] },
  total: { file: "mix_picks.enc", label: "Total", combos: (d) => d.mixed || [], mixed: true },
  // Jev (TypeSafe): same legs, chosen with Jev's probability (scripts: jev/jev_combos.py); one encrypted file for the three scopes
  jevnba: { file: "jev_picks.enc", label: "Jev NBA", combos: (d) => d.nba || [], sport: "nba" },
  jevnfl: { file: "jev_picks.enc", label: "Jev NFL", combos: (d) => d.nfl || [], sport: "nfl" },
  jevtotal: { file: "jev_picks.enc", label: "Jev Total", combos: (d) => d.total || [], mixed: true },
};
const GAME_PATH = { nba: "basketball/usa/nba/", nfl: "american-football/usa/nfl/" };
const gameUrl = (sport, fx) => `https://stake.com/es/sports/${GAME_PATH[sport] || GAME_PATH.nba}${fx}`;
// stat names exactly as Stake shows them in Spanish
const STAT_ES = {
  points: "Puntos", rebounds: "Rebotes", assists: "Asistencias", "points+rebounds": "Puntos + Rebotes",
  "points+assists": "Puntos + Asistencias", "assists+rebounds": "Asistencias + Rebotes",
  "points+assists+rebounds": "Puntos + Asistencias + Rebotes",
  "passing yards": "Yardas por Pases", "passing attempts": "Intentos de pases", "passing completions": "Pases Completados",
  "passing touchdowns": "Pases de Touchdowns", interceptions: "Intercepciones", "rushing yards": "Yardas por acarreo",
  "rushing attempts": "Intentos de acarreo", "receiving yards": "Yardas de recepción", receptions: "Recepciones",
};
const $ = (id) => document.getElementById(id);
const say = (t, err = false) => { $("msg").textContent = t; $("msg").className = err ? "err" : ""; };
const store = {
  get: (k) => new Promise((r) => chrome.storage.local.get(k, (v) => r(v[k]))),
  set: (k, v) => new Promise((r) => chrome.storage.local.set({ [k]: v }, r)),
  del: (k) => new Promise((r) => chrome.storage.local.remove(k, r)),
};
let section = "nba";
const cache = {};

async function decrypt(buf, password) {
  const b = new Uint8Array(buf);
  if (String.fromCharCode(...b.slice(0, 8)) !== "Salted__") throw new Error("formato");
  const salt = b.slice(8, 16);
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = new Uint8Array(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations: 10000 }, base, 384));
  const key = await crypto.subtle.importKey("raw", bits.slice(0, 32), "AES-CBC", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({ name: "AES-CBC", iv: bits.slice(32, 48) }, key, b.slice(16));
  const text = await new Response(new Blob([plain]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
  return JSON.parse(text);
}

const fmtTime = (s) => new Date(s).toLocaleString("es-ES", { weekday: "short", hour: "2-digit", minute: "2-digit" });
const keyOf = (l) => `${l.fixture}|${l.player}|${l.stat}|${l.side}|${l.line}`;
const statEs = (s) => STAT_ES[s] || s;
const legSport = (l) => l.sport || SECTIONS[section].sport || section;

const STAKE_URL = /^https:\/\/([^/]*\.)?stake\.com\//;

// Stake keeps the betslip in each tab's sessionStorage, so every leg of a combo must open in the SAME tab:
// a new tab starts with an empty slip. Reuse the tab we used last; else any open Stake tab; else open one.
async function stakeTab() {
  const savedId = await store.get("stakeTabId");
  if (savedId != null) {
    try {
      const t = await chrome.tabs.get(savedId);
      if (t && STAKE_URL.test(t.url || "")) return t;
    } catch (e) { /* tab was closed */ }
  }
  const [any] = await chrome.tabs.query({ url: ["https://stake.com/*", "https://*.stake.com/*"] });
  return any || null;
}

async function pick(leg) {
  const target = { player: leg.player, stat: statEs(leg.stat), line: String(leg.line),
                   side: leg.side === "Over" ? "Sobre" : "Debajo", fixture: leg.fixture, at: Date.now() };
  await store.set("target", target);
  const url = gameUrl(legSport(leg), leg.fixture);
  const tab = await stakeTab();
  const shown = tab ? await chrome.tabs.update(tab.id, { url, active: true }) : await chrome.tabs.create({ url });
  await store.set("stakeTabId", shown.id);
}

// ---- bankroll and suggested stake: balance (BNB) read from Stake's top bar by balance.js, BNB price from Binance's public ticker
const DEFAULTS = { pctCombo: 1.5, pctTennis: 10 };
async function bnbPrice() {
  const c = await store.get("bnbPrice");
  if (c && Date.now() - c.at < 600000) return c.v;
  try {
    const r = await fetch("https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT", { cache: "no-store" });
    const v = parseFloat((await r.json()).price);
    if (v > 0) { await store.set("bnbPrice", { v, at: Date.now() }); return v; }
  } catch (e) { /* offline */ }
  return c ? c.v : null;
}
async function bankroll() {
  const [auto, manual, price, pc, pt] = await Promise.all([store.get("stakeBalance"), store.get("manualBnb"), bnbPrice(), store.get("pctCombo"), store.get("pctTennis")]);
  const bnb = manual > 0 ? manual : auto ? auto.amount : null;
  // stakes are sized on the balance at the first look of the day, so placing one bet does not shrink the amounts of the next ones
  const day = new Date().toLocaleDateString("sv");
  let base = await store.get("dayBase");
  // new base: new day, manual balance changed, balance grew (deposit / win) or fell under half of it (a wrong earlier reading)
  if (bnb && (!base || base.day !== day || manual > 0 && base.manual !== manual || bnb > base.bnb || bnb < base.bnb * 0.5)) { base = { day, bnb, manual: manual > 0 ? manual : 0 }; await store.set("dayBase", base); }
  const baseBnb = base && base.day === day ? base.bnb : bnb;
  return { bnb, price, usd: bnb && price ? bnb * price : null, baseUsd: baseBnb && price ? baseBnb * price : null, src: manual > 0 ? "manual" : auto ? "Stake" : null, at: auto && auto.at,
           pctCombo: pc > 0 ? pc : DEFAULTS.pctCombo, pctTennis: pt > 0 ? pt : DEFAULTS.pctTennis };
}
const usd = (v) => v.toFixed(2).replace(".", ",") + " $";
// stake suggestion: fixed % of the balance, plus the quarter-Kelly stake of the model's probability as a reference
// weight: priority of the combo among the ones shown (1st 1.5x ... last 0.5x of the base %, so the total staked is the same as with a flat %)
function suggest(bank, kind, prob, odds, weight = 1) {
  if (!bank.usd) return "Saldo desconocido: abre Stake con la sesión iniciada o escríbelo en «Tamaño de las apuestas».";
  const pct = +((kind === "tennis" ? bank.pctTennis : bank.pctCombo) * weight).toFixed(2);
  const stake = bank.baseUsd * pct / 100;
  const kelly = prob && odds > 1 ? bank.baseUsd * 0.25 * Math.max(0, (prob * odds - 1) / (odds - 1)) : null;
  const bnb = (stake / bank.price).toFixed(8);       // Stake takes the amount in BNB (up to 8 decimals)
  return `<span class="sugl">Apuesta sugerida · clic para copiar</span><span class="sugv" data-v="${bnb}">${bnb} BNB</span>` +
         `<span class="sugd">≈ ${usd(stake)} · ${pct} % del saldo del día` + (kelly !== null ? ` · Kelly ¼ del modelo: ${usd(kelly)}` : "") + `</span>`;
}
async function showBank() {
  const b = await bankroll();
  const el = $("bank");
  if (!b.bnb) { el.className = "step"; el.textContent = "Saldo: aún no lo he leído. Abre Stake con la sesión iniciada (o escríbelo en «Tamaño de las apuestas»)."; return; }
  el.className = "step ok";
  const age = b.src === "Stake" && b.at ? ` · leído hace ${Math.max(0, Math.round((Date.now() - b.at) / 60000))} min` : "";
  el.textContent = `Saldo: ${b.bnb} BNB ≈ ${b.usd ? usd(b.usd) : "?"} (BNB ${b.price ? b.price.toFixed(2) : "?"} $) · ${b.src}${age}`;
}

async function render(doc) {
  const bank = await bankroll();
  const done = new Set((await store.get("done")) || []);
  const target = await store.get("target");
  const now = Date.now();
  const combos = SECTIONS[section].combos(doc).filter((c) => c.legs.every((l) => l.fixture && Date.parse(l.start) > now));
  $("list").innerHTML = "";
  if (!combos.length) { say(`No hay combinadas ${SECTIONS[section].label} apostables ahora mismo.`); return; }
  say(`Datos de ${new Date(doc.timestamp).toLocaleString("es-ES")}. Cuotas tal como se recomendaron.`);
  // best first: highest prob x odds (edge over the break-even) gets the biggest stake; amounts all come from the same balance
  combos.sort((a, b) => b.prob * b.odds - a.prob * a.odds);
  const weight = (i) => combos.length > 1 ? 1.5 - i / (combos.length - 1) : 1;
  // remember what is suggested for each combo: bets.js attaches it to the bet record when the bet is placed (see priority analysis)
  if (bank.baseUsd && bank.price) {
    const sugg = (await store.get("sugg")) || {};
    combos.forEach((c, i) => {
      const pct = +(bank.pctCombo * weight(i)).toFixed(2);
      sugg[c.legs.map((l) => l.player).sort().join("|")] = { section, rank: i + 1, of: combos.length, weight: +weight(i).toFixed(2), pct,
        bnb: +(bank.baseUsd * pct / 100 / bank.price).toFixed(8), prob: c.prob, odds: c.odds, at: Date.now() };
    });
    const keep = Object.entries(sugg).sort((x, y) => y[1].at - x[1].at).slice(0, 60);
    await store.set("sugg", Object.fromEntries(keep));
  }
  combos.forEach((c, i) => {
    const box = document.createElement("div");
    box.className = "combo";
    box.innerHTML = `<div class="head"><span>Combinada ${i + 1}${combos.length > 1 ? ` (${i + 1}.ª en prioridad)` : ""} · ${c.families.join(", ")}</span><span>cuota ${c.odds.toFixed(2)} · ${(c.prob * 100).toFixed(0)} %</span></div><div class="sug">${suggest(bank, "combo", c.prob, c.odds, weight(i))}</div>`;
    for (const l of c.legs) {
      const k = keyOf(l);
      const b = document.createElement("button");
      b.className = "leg" + (done.has(k) ? " done" : "") + (target && target.player === l.player && target.stat === statEs(l.stat) ? " on" : "");
      const tag = SECTIONS[section].mixed ? `<i class="sp">${legSport(l).toUpperCase()}</i> ` : "";
      b.innerHTML = `<span>${tag}<b>${l.player}</b> ${l.side === "Over" ? "Más de" : "Menos de"} ${l.line} ${statEs(l.stat)}<small>${l.game} · ${fmtTime(l.start)}</small></span><span class="odds">${l.stake_odds.toFixed(2)}</span>`;
      b.onclick = async () => { await pick(l); done.add(k); await store.set("done", [...done]); render(doc); };
      box.appendChild(b);
    }
    $("list").appendChild(box);
  });
}

async function fetchSection(name, pw) {
  const res = await fetch(`${RAW}${SECTIONS[name].file}?t=${Date.now()}`, { cache: "no-store" });
  if (res.status === 404) return null;   // e.g. NFL not published yet
  if (!res.ok) throw new Error("descarga " + res.status);
  return decrypt(await res.arrayBuffer(), pw);
}

// Tennis: the daily single pick of the bot is public (data/predictions/<date>.json, data/track_record.json): no password needed.
const TENNIS_URL = "https://stake.com/es/sports/tennis";
async function getJson(path) {
  const res = await fetch(`${RAW}${path}?t=${Date.now()}`, { cache: "no-store" });
  return res.ok ? res.json() : null;
}
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Opens the match page itself: tennis.js (on the Stake tab) looks the fixture up and answers with its URL. Without an open Stake tab
// (or if it does not answer, e.g. the page was not reloaded after updating the extension) it opens the tennis section instead.
async function openTennis(p) {
  // fair = break-even odds of the model (1 / probability): below it the pick has no edge any more
  await store.set("tennisTarget", { player: p.player, opponent: p.opponent, odds: Number(p.stake_price), fair: 1 / p.model_prob, at: Date.now() });
  await store.del("target");                    // the NBA/NFL highlighter stays idle on tennis pages
  const tab = await stakeTab();
  let url = p.stake_url || null, why = "";            // link published by scripts/tennis_link.py: straight to the match, like NBA/NFL
  const ask =() => Promise.race([chrome.tabs.sendMessage(tab.id, { type: "tennis-link", player: p.player, opponent: p.opponent }), new Promise((r) => setTimeout(() => r({ error: "tiempo agotado" }), 45000))]);
  if (tab && !url) {                                 // no published link yet: look the match up on the Stake tab
    say(`Buscando ${p.player} - ${p.opponent} en Stake…`);
    let ans = null;
    try { ans = await ask(); } catch (e) {
      // the page was opened before the extension was updated: load tennis.js into it now (no F5 needed) and ask again
      try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["tennis.js"] }); ans = await ask(); } catch (e2) { why = String(e2.message || e2); }
    }
    url = ans && ans.url;
    if (!url && ans && ans.error) why = ans.error;
  } else if (!tab && !url) why = "no hay ninguna pestaña de Stake abierta";
  const target = url || TENNIS_URL;
  const shown = tab ? await chrome.tabs.update(tab.id, { url: target, active: true }) : await chrome.tabs.create({ url: target });
  await store.set("stakeTabId", shown.id);
  say(url ? "Partido abierto en Stake." : `No pude llegar al partido (${why || "Stake no lo lista ahora"}): abro la sección de tenis.`, !url);
}

async function renderTennis() {
  $("list").innerHTML = "";
  say("Descargando…");
  const day = (back) => new Date(Date.now() - back * 864e5).toISOString().slice(0, 10);
  let pred = null;
  for (const back of [0, 1]) { pred = await getJson(`predictions/${day(back)}.json`); if (pred) break; }
  const tr = await getJson("track_record.json");
  const links = await getJson("tennis_links.json");
  const pick = pred && (pred.parlays || []).map((p) => p.picks || []).find((p) => p.length === 1);
  const link = pick && links && links.links && links.links[pred.date];
  if (pick && link && link.player === pick[0].player) pick[0].stake_url = link.url;
  if (!pick) { say("Hoy no hay pick de tenis publicado todavía."); }
  else {
    const p = pick[0];
    say(`Pick del ${pred.date}. Cuota de Stake al publicarse; compruébala antes de apostar.`);
    const box = document.createElement("div");
    box.className = "combo";
    box.innerHTML = `<div class="head"><span>Tenis · ${esc(p.surface || "").replace("_", " ")} · ${esc(p.signal || "")}</span><span>cuota ${Number(p.stake_price).toFixed(2)} · ${(p.model_prob * 100).toFixed(0)} %</span></div>
      <button class="leg"><span><b>${esc(p.player)}</b> (nº ${esc(p.rank)}) gana a ${esc(p.opponent)} (nº ${esc(p.opponent_rank)})<small>Ventaja ${(p.edge * 100).toFixed(1)} % sobre la cuota · pulsa para abrir el partido en Stake</small></span><span class="odds">${Number(p.stake_price).toFixed(2)}</span></button>
      <div class="sug">${suggest(await bankroll(), "tennis", p.model_prob, Number(p.stake_price))}</div>
      <div class="note" style="margin-top:6px">${esc(p.recommendation)}</div>`;
    box.querySelector("button").onclick = () => openTennis(p);
    $("list").appendChild(box);
  }
  if (tr && tr.months) {
    const rows = [];
    for (const [m, v] of Object.entries(tr.months)) for (const [d, e] of Object.entries(v.days || {})) for (const q of e.parlays || []) rows.push({ date: `${m}-${String(d).padStart(2, "0")}`, ...q });
    rows.sort((a, b) => (a.date < b.date ? 1 : -1));
    const since = day(30);
    const done = rows.filter((r) => r.date >= since && r.won !== null && r.won !== undefined);
    const profit = done.reduce((s, r) => s + (r.won ? r.stake_odds - 1 : -1), 0);
    const hist = document.createElement("div");
    hist.className = "combo";
    hist.innerHTML = `<div class="head"><span>Últimos días</span><span>30 días: ${done.filter((r) => r.won).length}/${done.length} · ${profit >= 0 ? "+" : ""}${profit.toFixed(2)} u</span></div>` +
      rows.slice(0, 7).map((r) => `<div class="head" style="margin:2px 0"><span>${esc(r.date)} · ${esc((r.legs || []).join(", "))}</span><span>${Number(r.stake_odds).toFixed(2)} ${r.won === true ? "✅" : r.won === false ? "❌" : "⏳"}</span></div>`).join("");
    $("list").appendChild(hist);
  }
}

async function load() {
  if (section === "tennis") { $("login").hidden = true; try { await renderTennis(); } catch (e) { say("No se pudo descargar el tenis: " + e.message, true); } return; }
  const pw = await store.get("pw");
  $("login").hidden = !!pw;
  if (!pw) { say(""); return; }
  say("Descargando…");
  try {
    const file = SECTIONS[section].file;
    if (!cache[file]) cache[file] = await fetchSection(section, pw);
    if (!cache[file]) { say("Todavía no hay datos publicados de esta sección."); $("list").innerHTML = ""; return; }
    await render(cache[file]);
  } catch (e) {
    say(e.message === "descarga 404" ? "No se encontró el archivo de datos." : "No se pudo descifrar: revisa la contraseña.", true);
    if (e.name === "OperationError") { await store.del("pw"); $("login").hidden = false; }
  }
}

function selectSection(name) {
  section = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.s === name));
  store.set("section", name);
  load();
}

document.querySelectorAll(".tab").forEach((b) => { b.onclick = () => selectSection(b.dataset.s); });
$("go").onclick = async () => { await store.set("pw", $("pw").value); $("pw").value = ""; load(); };
$("pw").onkeydown = (e) => { if (e.key === "Enter") $("go").click(); };
$("refresh").onclick = () => { Object.keys(cache).forEach((k) => delete cache[k]); load(); };
$("logout").onclick = async () => { await store.del("pw"); Object.keys(cache).forEach((k) => delete cache[k]); load(); };
// what the highlighter on the Stake tab is doing / cannot find (guide.js writes it; the page never sees it)
function showState(st) {
  const el = $("state");
  if (!st) { el.hidden = false; el.className = "step"; el.textContent = "Resaltador: aún sin datos de la pestaña de Stake. Recarga la página de Stake (F5) tras instalar o actualizar la extensión."; return; }
  const secs = Math.round((Date.now() - st.at) / 1000);
  el.hidden = false;
  el.className = "step" + (st.code === "ready" ? " ok" : "");
  el.textContent = st.detail + (secs > 60 ? ` (hace ${Math.round(secs / 60)} min)` : "");
}
chrome.storage.onChanged.addListener((c) => { if (c.guideState) showState(c.guideState.newValue); });
store.get("guideState").then(showState);
$("ver").textContent = "v" + chrome.runtime.getManifest().version;
store.get("section").then((s) => selectSection(SECTIONS[s] || s === "tennis" ? s : "nba"));

// click on the suggested stake = Ctrl+C of the amount in BNB with a dot ("0.00210800"), ready to paste into Stake's amount box
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* fall back to the old way */ }
  const t = document.createElement("textarea");
  t.value = text; t.style.position = "fixed"; t.style.opacity = "0";
  document.body.appendChild(t); t.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { /* blocked */ }
  t.remove();
  return ok;
}
$("list").addEventListener("click", async (ev) => {
  const box = ev.target.closest(".sug");
  const v = box && box.querySelector(".sugv");
  if (!v || !v.dataset.v) return;
  const label = box.querySelector(".sugl");
  const old = label.textContent;
  label.textContent = (await copyText(v.dataset.v)) ? `¡Copiado! ${v.dataset.v}` : "No se pudo copiar";
  setTimeout(() => { label.textContent = old; }, 1500);
});

// stake sizing settings
Promise.all([store.get("pctCombo"), store.get("pctTennis"), store.get("manualBnb")]).then(([a, b, m]) => {
  $("pctcombo").value = a > 0 ? a : DEFAULTS.pctCombo;
  $("pcttennis").value = b > 0 ? b : DEFAULTS.pctTennis;
  $("manualbnb").value = m > 0 ? m : "";
});
$("sizesave").onclick = async () => {
  await store.set("pctCombo", parseFloat($("pctcombo").value) || DEFAULTS.pctCombo);
  await store.set("pctTennis", parseFloat($("pcttennis").value) || DEFAULTS.pctTennis);
  const m = parseFloat($("manualbnb").value);
  if (m > 0) await store.set("manualBnb", m); else await store.del("manualBnb");
  await showBank();
  load();
};
chrome.storage.onChanged.addListener((c) => { if (c.stakeBalance) { showBank(); load(); } });
showBank();

// bet recorder: token + what bets.js / background.js did (queue, sent, last error)
function showBets() {
  Promise.all([store.get("betState"), store.get("betStats"), store.get("betQueue"), store.get("ghToken")]).then(([st, stats, queue, tok]) => {
    const el = $("betstate");
    const parts = [];
    if (!tok) parts.push("Falta el token: no se envía nada todavía.");
    if (st) parts.push(st.detail + ` (hace ${Math.max(0, Math.round((Date.now() - st.at) / 60000))} min)`);
    parts.push(`Enviadas: ${(stats && stats.sent) || 0} · pendientes: ${(queue || []).length}` + (stats && stats.error ? ` · ${stats.error}` : ""));
    el.hidden = false;
    el.className = "step" + (tok && !(stats && stats.error) ? " ok" : "");
    el.textContent = parts.join(" ");
  });
}
$("tokgo").onclick = async () => { await store.set("ghToken", $("tok").value.trim()); $("tok").value = ""; chrome.runtime.sendMessage({ type: "flush" }); setTimeout(showBets, 1500); };
$("tokflush").onclick = () => { chrome.runtime.sendMessage({ type: "flush" }); setTimeout(showBets, 1500); };
chrome.storage.onChanged.addListener((c) => { if (c.betState || c.betStats || c.betQueue || c.ghToken) showBets(); });
showBets();
