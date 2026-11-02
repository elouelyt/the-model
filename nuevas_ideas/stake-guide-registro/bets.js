// Stake Bet Guide - bet recorder. READ-ONLY: it reads the visible betslip / receipt (selections, odds, amount) and, when Stake confirms a bet
// was placed, hands one record to the extension's background script. It never clicks, types or changes the page and adds no
// elements to it; the only thing it listens to is the user's own click on Stake's "Apostar" button.
(() => {
  const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();
  const num = (s) => { const v = parseFloat(String(s).replace(/\s/g, "").replace(",", ".")); return Number.isFinite(v) ? v : null; };
  const all = (id, root = document) => [...root.querySelectorAll(`[data-testid="${id}"]`)];
  const MARKET = /^(Sobre|Debajo|Over|Under)\s+([\d.,]+)\s+(.+)$/i;
  const NUMBER = /^[\d.,]+$/;
  const PLACE = /^(apostar|realizar apuesta|colocar apuesta|place bet|confirmar apuesta)/i;
  const SUCCESS = /(apuesta|bet)\s+(realizada|colocada|aceptada|exitosa|placed|accepted|successful)|apuesta\s+hecha|bet\s+confirmed/i;
  const FAILURE = /saldo insuficiente|insufficient|cuotas? (han )?cambiado|odds (have )?changed|no se pudo|rechazad|rejected/i;
  const REUSE = /Reutilizar Tal[oó]n|Reuse Bet ?slip/i;
  const DUP_MS = 180000;                            // the same bet (legs + amount) is recorded once per 3 minutes

  // one selection from consecutive text lines: [game, "Sobre 7.5 Puntos", player, odds] in the slip, [game, market, odds, player] in the receipt
  function parseLeg(lines, i) {
    const m = MARKET.exec(lines[i]);
    if (!m) return null;
    let odds = null, player = "";
    for (const l of lines.slice(i + 1, i + 4)) {
      const v = NUMBER.test(l) ? num(l) : null;
      if (v !== null && v > 1 && odds === null) odds = v;
      else if (v === null && !player && !MARKET.test(l) && !/ - /.test(l)) player = l;
    }
    return { game: lines[i - 1] || "", side: /^(sobre|over)$/i.test(m[1]) ? "Over" : "Under", line: num(m[2]), stat: clean(m[3]), player, odds };
  }
  // tennis match winner in the slip: ["Surname, First - Surname, First", "Surname, First", "Ganador", "1,63", ...]
  function parseTennis(lines) {
    const g = lines.findIndex((l) => / - /.test(l));
    if (g < 0 || !/^(Ganador|Winner)$/i.test(lines[g + 2] || "")) return null;
    const flip = (s) => (s.includes(",") ? s.split(",").map(clean).reverse().join(" ") : s);
    const odds = lines.slice(g + 3, g + 5).map((l) => (NUMBER.test(l) ? num(l) : null)).find((v) => v !== null && v > 1);
    return { game: lines[g].split(" - ").map(flip).join(" - "), side: "Gana", line: null, stat: "Ganador", player: flip(lines[g + 1]), odds: odds || null, sport: "tennis" };
  }
  function readLeg(el) {
    const lines = el.innerText.split("\n").map(clean).filter(Boolean);
    const i = lines.findIndex((l) => MARKET.test(l));
    return i < 0 ? parseTennis(lines) : parseLeg(lines, i);
  }

  // Stake can render the same selection twice (re-render, nested test ids): a bet never has the same player/market/side/line twice
  function uniq(legs) {
    const seen = new Set();
    return legs.filter((l) => { const k = `${l.player}|${l.stat}|${l.side}|${l.line}`; if (seen.has(k)) return false; seen.add(k); return true; });
  }

  function amountOf(input) { const v = num(input && input.value); return v && v > 0 ? v : 0; }

  function snapshot() {
    const multi = all("betslip-multi-bet")[0];
    const out = { at: Date.now(), multi: null, singles: [] };
    if (multi) {
      const legs = uniq(all("betslip-bet", multi).map(readLeg).filter(Boolean));
      const odds = num((all("multi-bet-total-odds", multi)[0] || {}).innerText);
      const input = all("input-bet-amount", multi)[0];
      const cur = clean((multi.querySelector(".before-icon") || {}).textContent);
      if (legs.length) out.multi = { legs, odds, amount: amountOf(input), currency: cur };
    }
    for (const b of all("betslip-bet")) {
      if (multi && multi.contains(b)) continue;
      const leg = readLeg(b);
      const input = b.querySelector('[data-testid="input-bet-amount"]') || (b.nextElementSibling && b.nextElementSibling.querySelector('[data-testid="input-bet-amount"]'));
      if (leg) out.singles.push({ leg, amount: amountOf(input) });
    }
    return out;
  }

  const sig = (legs) => legs.map((l) => `${l.player}|${l.stat}|${l.side}|${l.line}`).sort().join(";");
  const recent = new Map();                         // key -> time of the last record (click path and receipt path share it)
  const seenReceipts = new Set();                   // receipts already recorded on this page (several bets in a row show several receipts)

  function report(code, detail) { try { chrome.storage.local.set({ betState: { code, detail, at: Date.now() } }); } catch (e) { /* extension reloaded */ } }

  function emit(kind, legs, odds, amount, currency) {
    const key = kind + "|" + sig(legs) + "|" + amount;
    if (recent.has(key) && Date.now() - recent.get(key) < DUP_MS) return;
    recent.set(key, Date.now());
    const bet = { id: `${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14)}-${Math.random().toString(36).slice(2, 7)}`, placed_at: new Date().toISOString(),
                  kind, odds, amount, currency, legs, page: location.pathname };
    // what the side panel suggested for this combo (tab, priority among the shown ones, suggested stake): lets the comparison check whether
    // the combos ranked first (bigger stake) hit more often. Matched by the set of players; missing when the combo was not picked from the panel.
    const send = (suggested) => { try { chrome.runtime.sendMessage({ type: "bet", bet: suggested ? { ...bet, suggested } : bet }); } catch (e) { /* extension reloaded */ } };
    try {
      chrome.storage.local.get("sugg", (o) => {
        const hit = kind === "multi" && o && o.sugg && o.sugg[legs.map((l) => l.player).sort().join("|")];
        send(hit && Date.now() - hit.at < 36e5 * 36 ? hit : null);
      });
    } catch (e) { send(null); }
    report("saved", `Apuesta registrada: ${kind === "multi" ? "combinada de " + legs.length : "simple"} @ ${odds}.`);
  }

  // after the click: wait for Stake's confirmation (text) or for the slip to empty, but never when an error is shown
  function watch(snap) {
    // one watcher per click, running side by side: a second bet placed while the first is still being confirmed must not be dropped
    // (emit() already ignores the same bet seen twice)
    const t0 = Date.now();
    const finish = (ok) => {
      if (!ok) { report("unconfirmed", "Pulsaste Apostar pero no vi la confirmación de Stake; no la he registrado."); return; }
      if (snap.multi && snap.multi.amount) emit("multi", snap.multi.legs, snap.multi.odds, snap.multi.amount, snap.multi.currency);
      for (const s of snap.singles) if (s.amount) emit("single", [s.leg], s.leg.odds, s.amount, snap.multi ? snap.multi.currency : "");
    };
    const tick = () => {
      const text = document.body.innerText;
      const now = snapshot();
      const slipLeft = (now.multi ? now.multi.legs.length : 0) + now.singles.length;
      const slipBefore = (snap.multi ? snap.multi.legs.length : 0) + snap.singles.length;
      if (REUSE.test(text)) return finish(true);                                    // the receipt ("Reutilizar Talón") is on screen
      if (SUCCESS.test(text) && !(FAILURE.test(text) && slipLeft >= slipBefore)) return finish(true);
      if (slipBefore && slipLeft === 0) return finish(true);                       // Stake emptied the slip after accepting the bet
      if (Date.now() - t0 > 25000) return finish(false);
      setTimeout(tick, 500);
    };
    setTimeout(tick, 800);
  }

  // Stake keeps a receipt on screen after a bet ("Reutilizar Talón" ... "Ver Mis Apuestas"): read it as well, so a combo is recorded even when
  // the click was missed (extension loaded after the page was open, keyboard, ...). One record per receipt shown.
  function scanReceipt() {
    const txt = document.body.innerText;
    if (!REUSE.test(txt)) return;
    const lines = txt.split("\n").map(clean).filter(Boolean);
    const a = lines.findIndex((l) => REUSE.test(l));
    const b = lines.findIndex((l, i) => i > a && /^(Ver Mis Apuestas|View My Bets)/i.test(l));
    const block = lines.slice(a + 1, b > a ? b : a + 80);
    const mi = block.findIndex((l) => /^\d+\s+(Multi|Multiple)/i.test(l));
    if (mi < 0) {                                   // single bet: only the tennis "Ganador" receipt is understood (the click path handles the rest)
      // receipt: ["Surname, First - Surname, First", "Surname, First", "1,63", "Ganador", "Apuesta Total", "0.00035750", "Pago", ...]
      const g = block.findIndex((l) => / - /.test(l));
      const m = g < 0 ? -1 : block.slice(g + 1, g + 6).findIndex((l) => /^(Ganador|Winner)$/i.test(l));
      if (m < 0) return;
      const leg = parseTennis([block[g], block[g + 1], "Ganador", ...block.slice(g + 2, g + 6).filter((l) => NUMBER.test(l))]);
      const k = block.findIndex((l) => /^(Apuesta Total|Total Bet|Total Stake)/i.test(l));
      const amount = k < 0 ? null : num(block.slice(k + 1, k + 3).find((l) => NUMBER.test(l)));
      if (!leg || !leg.odds || !amount) return;
      const rk = sig([leg]) + "|" + amount + "|" + leg.odds;
      if (seenReceipts.has(rk)) return;
      seenReceipts.add(rk);
      emit("single", [leg], leg.odds, amount, "");
      return;
    }
    const odds = num(block.slice(mi + 1, mi + 3).find((l) => NUMBER.test(l)));
    const k = block.findIndex((l) => /^(Apuesta Total|Total Bet|Total Stake)/i.test(l));
    const amount = k < 0 ? null : num(block.slice(k + 1, k + 3).find((l) => NUMBER.test(l)));
    const found = [];
    block.forEach((l, i) => { if (MARKET.test(l)) { const leg = parseLeg(block, i); if (leg) found.push(leg); } });
    const legs = uniq(found);
    if (!legs.length || !amount) return;
    const rk = sig(legs) + "|" + amount + "|" + odds;
    if (seenReceipts.has(rk)) return;
    seenReceipts.add(rk);
    emit("multi", legs, odds, amount, "");
  }
  let rt;
  new MutationObserver(() => { clearTimeout(rt); rt = setTimeout(scanReceipt, 700); }).observe(document.body, { subtree: true, childList: true, characterData: true });
  setTimeout(scanReceipt, 1500);

  document.addEventListener("click", (ev) => {
    const btn = ev.target && ev.target.closest && ev.target.closest("button");
    if (!btn) return;
    const label = clean(btn.innerText);
    if (!PLACE.test(label)) return;
    const snap = snapshot();
    const hasAmount = (snap.multi && snap.multi.amount) || snap.singles.some((s) => s.amount);
    if (!hasAmount) return;
    watch(snap);
  }, true);
})();
