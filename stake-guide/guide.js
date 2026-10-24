// Stake Bet Guide - page side. READ-ONLY: it reads the visible text of the game page and paints highlights with the
// CSS Custom Highlight API (no element, class or attribute is added or changed, nothing is clicked, no network).
// Steps follow what the user does: tab "Apuestas al Jugador" -> player name -> market + line -> Sobre/Debajo.
(() => {
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  const POSITION = /\s*\((?:PG|SG|SF|PF|C|G|F|G-F|F-C|F-G|C-F)\)\s*$/i;
  let target = null;

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

  function step() {
    ["sbg-y", "sbg-g", "sbg-o"].forEach((k) => CSS.highlights.delete(k));
    if (!target || !location.pathname.includes(target.fixture)) return;
    const all = texts(document.body);
    const names = all.filter((n) => POSITION.test(n.textContent) && n.textContent.length < 40);
    const me = names.find((n) => norm(n.textContent.replace(POSITION, "")) === norm(target.player));
    if (!me) {
      paint("sbg-y", all.filter((n) => n.textContent.trim() === "Apuestas al Jugador"));
      return;
    }
    // the player's card ends where the next player's name starts
    const next = names[names.indexOf(me) + 1];
    const inCard = (n) => (me.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      (!next || (next.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_PRECEDING));
    const stat = all.find((n) => n.textContent.trim() === target.stat && inCard(n));
    if (!stat) { paint("sbg-y", [me]); return; }

    let row = stat.parentElement;
    while (row && !(row.innerText.includes("Sobre") && row.innerText.includes("Debajo"))) row = row.parentElement;
    if (!row) { paint("sbg-y", [stat]); return; }
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
      return;
    }
    const side = rowTexts.find((n) => n.textContent.trim() === target.side);
    paint("sbg-g", [line, side, side && rowTexts[rowTexts.indexOf(side) + 1]]);
  }

  let timer;
  const later = () => { clearTimeout(timer); timer = setTimeout(step, 150); };
  new MutationObserver(later).observe(document.body, { subtree: true, childList: true });
  const setTarget = (t) => { target = t || null; step(); };
  chrome.storage.local.get("target", (v) => setTarget(v.target));
  chrome.storage.onChanged.addListener((c) => { if (c.target) setTarget(c.target.newValue); });
})();
