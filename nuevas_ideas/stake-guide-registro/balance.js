// Stake Bet Guide - balance reader. READ-ONLY: it reads the balance number Stake shows in the top bar (e.g. "5.08" in dollars or
// "0.02147217" in BNB) and hands it to the side panel through chrome.storage so it can size the suggested stakes. It adds nothing to the page,
// clicks nothing and makes no network request.
(() => {
  // the unit Stake shows is set in the side panel ("Stake te muestra los importes en"): dollars by default
  const RX = { BNB: /^\d{1,3}[.,]\d{4,8}$/,           // 4-8 decimals: a crypto balance
               USD: /^\$?\s?\d{1,6}[.,]\d{2}$/ };     // dollars: 2 decimals, maybe with "$"
  let currency = "USD";
  let last = null;
  try {
    chrome.storage.local.get("stakeCurrency", (o) => { currency = o && o.stakeCurrency === "BNB" ? "BNB" : "USD"; last = null; publish(); });
    chrome.storage.onChanged.addListener((c) => { if (c.stakeCurrency) { currency = c.stakeCurrency.newValue === "BNB" ? "BNB" : "USD"; last = null; publish(); } });
  } catch (e) { /* extension reloaded */ }

  function read() {
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const t = n.textContent.trim();
      if (!RX[currency].test(t) || !n.parentElement) continue;
      const r = n.parentElement.getBoundingClientRect();
      if (!r.width || r.top < 0 || r.top > 60) continue;      // the top bar only (measured: balance at top 18; the betslip amounts start lower, at 80+)
      const v = parseFloat(t.replace(/[$\s]/g, "").replace(",", "."));
      return Number.isFinite(v) ? v : null;
    }
    return null;
  }

  // A balance does not jump up 20x by itself, so a reading far above the stored one (same unit) is ignored (a lower one is always
  // accepted, which also repairs an earlier bad reading). The unit is stored with it: a BNB reading is never used as dollars.
  function publish() {
    const v = read();
    if (v === null || v === last) return;
    last = v;
    try {
      chrome.storage.local.get("stakeBalance", (o) => {
        const s = o && o.stakeBalance;
        const prev = s && (s.currency || "BNB") === currency ? s.amount : null;
        if (prev > 0 && v > prev * 20) return;
        chrome.storage.local.set({ stakeBalance: { amount: v, currency, at: Date.now() } });
      });
    } catch (e) { /* extension reloaded */ }
  }

  let timer;
  new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(publish, 800); }).observe(document.body, { subtree: true, childList: true, characterData: true });
  setTimeout(publish, 2000);
})();
