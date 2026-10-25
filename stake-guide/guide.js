// Stake Bet Guide - page side. READ-ONLY: it reads the visible text of the game page and paints highlights with the
// CSS Custom Highlight API (no element, class or attribute is added or changed, nothing is clicked, no network).
// Steps follow what the user does: tab "Apuestas al Jugador" -> player name -> market + line -> Sobre/Debajo.
// It also tells the side panel (through chrome.storage, never the page) which step it is on and what it cannot find.
(() => {
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  // player names: no accents, no punctuation, no Jr/Sr/II/III/IV ("Aaron Jones Sr." == "Aaron Jones")
  const nameKey = (s) => norm(s).replace(/[^a-z0-9 ]+/g, " ").split(/\s+/).filter((w) => w && !/^(jr|sr|ii|iii|iv|v)$/.test(w)).join(" ");
  const POSITION = /\s*\([A-Z]{1,3}(?:-[A-Z]{1,3})?\)\s*$/;   // NBA (PG, SF, C...) and NFL (QB, WR, TE...) positions
  let target = null;
  let lastReport = "";

  const report = (code, detail) => {
    const sig = code + "|" + detail;
    if (sig === lastReport) return;
    lastReport = sig;
    try { chrome.storage.local.set({ guideState: { code, detail, at: Date.now() } }); } catch (e) { /* extension reloaded */ }
  };

  const texts = (root) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const out = [];
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const t = n.textContent.trim();
      if (t && n.parentElement && n.parentElement.getClientRects().length) out.push(n);
    }
    return out;
  };
  const range = (n) => { const r = new Range(); r.selectNodeContents(n); return r; };
  const paint = (name, nodes) => {
    nodes = nodes.filter(Boolean);
    if (nodes.length) CSS.highlights.set(name, new Highlight(...nodes.map(range)));
    else CSS.highlights.delete(name);
  };

  const sheet = new CSSStyleSheet();
  sheet.replaceSync(
    "::highlight(sbg-y){background:#ffd400;color:#000}::highlight(sbg-g){background:#00c853;color:#000}" +
    "::highlight(sbg-o){background:#ff9100;color:#000}");
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];

  function findPlayer(names, labelText) {
    const want = nameKey(target.player);
    const strip = (n) => nameKey(labelText(n).replace(POSITION, ""));
    const exact = names.find((n) => strip(n) === want);
    if (exact) return { me: exact, similar: [] };
    // fallback: same last word and same first initial, only if it is unambiguous
    const w = want.split(" ");
    const loose = names.filter((n) => { const k = strip(n).split(" "); return k[k.length - 1] === w[w.length - 1] && k[0][0] === w[0][0]; });
    if (loose.length === 1) return { me: loose[0], similar: [] };
    const similar = names.filter((n) => strip(n).split(" ").includes(w[w.length - 1])).map((n) => labelText(n));
    return { me: null, similar };
  }

  function step() {
    ["sbg-y", "sbg-g", "sbg-o"].forEach((k) => CSS.highlights.delete(k));
    if (!target) return;
    if (!location.pathname.includes(target.fixture)) {
      report("wrong_page", "Esta pestaña no está en el partido de la pierna elegida: pulsa la pierna en el panel.");
      return;
    }
    const all = texts(document.body);
    // a player label is "Name (POS)": normally one text node, but Stake may split name and position into sibling spans
    const FULL = /^.{3,40}\s\([A-Z]{1,3}(?:-[A-Z]{1,3})?\)$/;
    const labelOf = (n) => {
      const own = n.textContent.trim();
      if (POSITION.test(own) && own.length < 40) return own;
      const p = n.parentElement && n.parentElement.parentElement;           // <span>Name</span><span>(POS)</span> inside one element
      const txt = p && p.innerText ? p.innerText.replace(/\s+/g, " ").trim() : "";
      return FULL.test(txt) && txt.startsWith(own) && !POSITION.test(own) ? txt : null;
    };
    const labelMap = new Map();
    const names = all.filter((n) => { const l = labelOf(n); if (l) labelMap.set(n, l); return !!l; });
    const labelText = (n) => labelMap.get(n);
    const { me, similar } = findPlayer(names, labelText);
    if (!me) {
      paint("sbg-y", all.filter((n) => n.textContent.trim() === "Apuestas al Jugador"));
      if (!names.length) report("tab", `Pulsa la pestaña «Apuestas al Jugador» (aún no veo la lista de jugadores).`);
      else report("player_missing", `No encuentro a «${target.player}» entre los ${names.length} jugadores de la lista` +
        (similar.length ? `; parecidos: ${similar.slice(0, 3).join(", ")}` : "; puede que Stake no lo liste (¿ya empezó el partido?)."));
      return;
    }
    // the player's card ends where the next player's name starts
    const next = names[names.indexOf(me) + 1];
    const inCard = (n) => (me.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      (!next || (next.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_PRECEDING));
    const stat = all.find((n) => norm(n.textContent) === norm(target.stat) && inCard(n));
    if (!stat) {
      paint("sbg-y", [me]);
      const opened = all.some((n) => /^Sobre$/.test(n.textContent.trim()) && inCard(n));
      report(opened ? "market_missing" : "player",
        opened ? `«${target.player}» no tiene ahora el mercado «${target.stat}» (¿partido ya empezado? en directo Stake cambia los mercados).`
               : `Pulsa el nombre de ${target.player} para desplegarlo.`);
      return;
    }

    let row = stat.parentElement;
    while (row && !(row.innerText.includes("Sobre") && row.innerText.includes("Debajo"))) row = row.parentElement;
    if (!row) { paint("sbg-y", [stat]); report("market_missing", `Veo «${target.stat}» pero no sus botones Sobre/Debajo.`); return; }
    const rowTexts = texts(row);
    const line = rowTexts.find((n) => /^\d+(\.\d+)?$/.test(n.textContent.trim()) && /\.5$/.test(n.textContent.trim()));
    paint("sbg-y", [stat]);
    if (line && line.textContent.trim() !== target.line) {
      paint("sbg-o", [line]);  // wrong line shown: change it
      // the wanted option in the open list: same number, but not the line of another market row
      const rowOf = (n) => {
        let e = n.parentElement;
        while (e && !(e.innerText.includes("Sobre") && e.innerText.includes("Debajo"))) e = e.parentElement;
        return e;
      };
      paint("sbg-g", all.filter((n) => {
        if (n === line || n.textContent.trim() !== target.line) return false;
        const r = rowOf(n);
        return !r || r === row || (r.innerText.match(/Sobre/g) || []).length !== 1;
      }));
      report("line", `Cambia la línea de ${line.textContent.trim()} a ${target.line} (abre el desplegable de la línea).`);
      return;
    }
    const side = rowTexts.find((n) => n.textContent.trim() === target.side);
    paint("sbg-g", [line, side, side && rowTexts[rowTexts.indexOf(side) + 1]]);
    report("ready", `Todo listo: pulsa «${target.side}» (${target.line}).`);
  }

  let timer;
  const later = () => { clearTimeout(timer); timer = setTimeout(step, 150); };
  new MutationObserver(later).observe(document.body, { subtree: true, childList: true });
  const setTarget = (t) => { target = t || null; lastReport = ""; step(); };
  chrome.storage.local.get("target", (v) => setTarget(v.target));
  chrome.storage.onChanged.addListener((c) => { if (c.target) setTarget(c.target.newValue); });
})();
