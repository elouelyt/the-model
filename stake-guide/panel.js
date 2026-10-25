// Side panel: downloads data/nba_picks.enc (openssl AES-256-CBC + PBKDF2-SHA256 + gzip), decrypts it here with the
// panel password and lists the bettable combos. Picking a leg stores it as the target and opens that game on Stake.
const DATA_URL = "https://raw.githubusercontent.com/elouelyt/the-model/main/data/nba_picks.enc";
const GAME_URL = (fx) => `https://stake.com/es/sports/basketball/usa/nba/${fx}`;
const STAT_ES = {
  points: "Puntos", rebounds: "Rebotes", assists: "Asistencias", "points+rebounds": "Puntos + Rebotes",
  "points+assists": "Puntos + Asistencias", "assists+rebounds": "Asistencias + Rebotes",
  "points+assists+rebounds": "Puntos + Asistencias + Rebotes",
};
const $ = (id) => document.getElementById(id);
const say = (t, err = false) => { $("msg").textContent = t; $("msg").className = err ? "err" : ""; };
const store = {
  get: (k) => new Promise((r) => chrome.storage.local.get(k, (v) => r(v[k]))),
  set: (k, v) => new Promise((r) => chrome.storage.local.set({ [k]: v }, r)),
  del: (k) => new Promise((r) => chrome.storage.local.remove(k, r)),
};

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
  const target = { player: leg.player, stat: STAT_ES[leg.stat] || leg.stat, line: String(leg.line),
                   side: leg.side === "Over" ? "Sobre" : "Debajo", fixture: leg.fixture, at: Date.now() };
  await store.set("target", target);
  const url = GAME_URL(leg.fixture);
  const tab = await stakeTab();
  const shown = tab ? await chrome.tabs.update(tab.id, { url, active: true }) : await chrome.tabs.create({ url });
  await store.set("stakeTabId", shown.id);
}

async function render(doc) {
  const done = new Set((await store.get("done")) || []);
  const target = await store.get("target");
  const now = Date.now();
  const combos = (doc.combos || []).filter((c) => c.legs.every((l) => l.fixture && Date.parse(l.start) > now));
  $("list").innerHTML = "";
  if (!combos.length) { say("No hay combinadas apostables ahora mismo."); return; }
  say(`Datos de ${new Date(doc.timestamp).toLocaleString("es-ES")}. Cuotas tal como se recomendaron.`);
  combos.forEach((c, i) => {
    const box = document.createElement("div");
    box.className = "combo";
    box.innerHTML = `<div class="head"><span>Combinada ${i + 1} · ${c.families.join(", ")}</span><span>cuota ${c.odds.toFixed(2)}</span></div>`;
    for (const l of c.legs) {
      const k = keyOf(l);
      const b = document.createElement("button");
      b.className = "leg" + (done.has(k) ? " done" : "") + (target && target.player === l.player && target.stat === (STAT_ES[l.stat] || l.stat) ? " on" : "");
      b.innerHTML = `<span><b>${l.player}</b> ${l.side === "Over" ? "Más de" : "Menos de"} ${l.line} ${STAT_ES[l.stat] || l.stat}<small>${l.game} · ${fmtTime(l.start)}</small></span><span class="odds">${l.stake_odds.toFixed(2)}</span>`;
      b.onclick = async () => { await pick(l); done.add(k); await store.set("done", [...done]); render(doc); };
      box.appendChild(b);
    }
    $("list").appendChild(box);
  });
}

async function load() {
  const pw = await store.get("pw");
  $("login").hidden = !!pw;
  if (!pw) { say(""); return; }
  say("Descargando…");
  try {
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error("descarga " + res.status);
    await render(await decrypt(await res.arrayBuffer(), pw));
  } catch (e) {
    say(e.message === "descarga 404" ? "No se encontró el archivo de datos." : "No se pudo descifrar: revisa la contraseña.", true);
    if (e.name === "OperationError") { await store.del("pw"); $("login").hidden = false; }
  }
}

$("go").onclick = async () => { await store.set("pw", $("pw").value); $("pw").value = ""; load(); };
$("pw").onkeydown = (e) => { if (e.key === "Enter") $("go").click(); };
$("refresh").onclick = load;
$("logout").onclick = async () => { await store.del("pw"); load(); };
load();
