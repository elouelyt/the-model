// Side panel: downloads the encrypted picks (openssl AES-256-CBC + PBKDF2-SHA256 + gzip), decrypts them here with the panel password and
// lists the bettable combos in three sections: NBA, NFL and Total (mixed NBA+NFL). Picking a leg stores it as the target and opens that
// game on Stake in the SAME tab (the betslip lives in each tab's sessionStorage).
const RAW = "https://raw.githubusercontent.com/elouelyt/the-model/main/data/";
const SECTIONS = {
  nba: { file: "nba_picks.enc", label: "NBA", combos: (d) => d.combos || [] },
  nfl: { file: "nfl_picks.enc", label: "NFL", combos: (d) => d.combos || [] },
  total: { file: "mix_picks.enc", label: "Total", combos: (d) => d.mixed || [] },
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
const legSport = (l) => l.sport || section;

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

async function render(doc) {
  const done = new Set((await store.get("done")) || []);
  const target = await store.get("target");
  const now = Date.now();
  const combos = SECTIONS[section].combos(doc).filter((c) => c.legs.every((l) => l.fixture && Date.parse(l.start) > now));
  $("list").innerHTML = "";
  if (!combos.length) { say(`No hay combinadas ${SECTIONS[section].label} apostables ahora mismo.`); return; }
  say(`Datos de ${new Date(doc.timestamp).toLocaleString("es-ES")}. Cuotas tal como se recomendaron.`);
  combos.forEach((c, i) => {
    const box = document.createElement("div");
    box.className = "combo";
    box.innerHTML = `<div class="head"><span>Combinada ${i + 1} · ${c.families.join(", ")}</span><span>cuota ${c.odds.toFixed(2)} · ${(c.prob * 100).toFixed(0)} %</span></div>`;
    for (const l of c.legs) {
      const k = keyOf(l);
      const b = document.createElement("button");
      b.className = "leg" + (done.has(k) ? " done" : "") + (target && target.player === l.player && target.stat === statEs(l.stat) ? " on" : "");
      const tag = section === "total" ? `<i class="sp">${legSport(l).toUpperCase()}</i> ` : "";
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

async function load() {
  const pw = await store.get("pw");
  $("login").hidden = !!pw;
  if (!pw) { say(""); return; }
  say("Descargando…");
  try {
    if (!cache[section]) cache[section] = await fetchSection(section, pw);
    if (!cache[section]) { say("Todavía no hay datos publicados de esta sección."); $("list").innerHTML = ""; return; }
    await render(cache[section]);
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
  if (!st || Date.now() - st.at > 120000) { el.hidden = true; return; }
  el.hidden = false;
  el.className = "step" + (st.code === "ready" ? " ok" : "");
  el.textContent = st.detail;
}
chrome.storage.onChanged.addListener((c) => { if (c.guideState) showState(c.guideState.newValue); });
store.get("guideState").then(showState);
store.get("section").then((s) => selectSection(SECTIONS[s] ? s : "nba"));
