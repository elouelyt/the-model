// Stake Bet Guide - balance reader. READ-ONLY: it reads the balance number Stake shows in the top bar (e.g. "0.02147217", the coin the user
// selected: BNB) and hands it to the side panel through chrome.storage so it can size the suggested stakes. It adds nothing to the page,
// clicks nothing and makes no network request.
(() => {
  const RX = /^\d{1,3}[.,]\d{4,8}$/;                // 4-8 decimals: a crypto balance (the USD view has 2 decimals and is ignored)
  let last = null;

  function read() {
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const t = n.textContent.trim();
      if (!RX.test(t) || !n.parentElement) continue;
      const r = n.parentElement.getBoundingClientRect();
      if (!r.width || r.top < 0 || r.top > 60) continue;      // the top bar only (measured: balance at top 18; the betslip amounts start lower, at 80+)
      const v = parseFloat(t.replace(",", "."));
      return Number.isFinite(v) ? v : null;
    }
    return null;
  }

  // Stake can be switched to dollars: the USD figure (e.g. 21.7) would be read as BNB, ~700x too big. A balance does not jump up 20x by
  // itself, so a reading far above the stored one is ignored (a lower one is always accepted, which also repairs an earlier bad reading).
  function publish() {
    const v = read();
    if (v === null || v === last) return;
    last = v;
    try {
      chrome.storage.local.get("stakeBalance", (o) => {
        const prev = o && o.stakeBalance && o.stakeBalance.amount;
        if (prev > 0 && v > prev * 20) return;
        chrome.storage.local.set({ stakeBalance: { amount: v, at: Date.now() } });
      });
    } catch (e) { /* extension reloaded */ }
  }

  let timer;
  new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(publish, 800); }).observe(document.body, { subtree: true, childList: true, characterData: true });
  setTimeout(publish, 2000);
})();
