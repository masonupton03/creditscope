/* Consistent ticker navigation between Explorer (prices and risk), Fundamentals (SEC statements) and Compare.
 * A link is shown only when the target page has data for that ticker; otherwise a disabled item explains why.
 * Real prices and SEC statements are different data sets, so availability is checked separately in each one. */
(function (root) {
  'use strict';
  const SYMBOL = /^[A-Z0-9][A-Z0-9.\-]{0,9}$/;
  function build(sym, avail, current) {
    if (!SYMBOL.test(sym)) return [];
    const peer = sym === 'SPY' ? 'QQQ' : 'SPY';
    const items = [
      { key: 'explorer', label: 'Price and risk', href: 'explorer.html#' + sym, enabled: !!avail.price, reason: 'No price history for ' + sym + ' in this data set' },
      { key: 'fundamentals', label: 'Fundamentals', href: 'fundamentals.html#' + sym, enabled: !!avail.fund, reason: 'No SEC financial statements for ' + sym + ' in this data set' + (avail.fund === false && avail.fundSynthetic ? ' (the demonstration set contains only fictional companies)' : '') },
      { key: 'compare', label: 'Compare prices', href: 'compare.html#s=' + sym + ',' + peer + '&p=1Y', enabled: !!avail.price, reason: 'Needs price history for ' + sym }
    ];
    return items.filter(i => i.key !== current);
  }
  function render(el, sym, avail, current) {
    if (!el) return;
    const esc = root.CS ? root.CS.esc : (s => String(s));
    const items = build(sym, avail, current);
    el.innerHTML = items.length ? '<span class="lab">Open ' + esc(sym) + ' in</span>' + items.map(i => i.enabled
      ? '<a href="' + esc(i.href) + '">' + esc(i.label) + '</a>'
      : '<span class="off" role="link" aria-disabled="true" title="' + esc(i.reason) + '" tabindex="0">' + esc(i.label) + '<span class="sr-only"> unavailable: ' + esc(i.reason) + '</span></span>').join('') : '';
    el.hidden = !items.length;
  }
  /** Which tickers each page can show. Failures degrade to "unknown = unavailable"; they never throw. */
  async function availability(personal) {
    const get = async u => { try { const r = await fetch(u); if (!r.ok) { await r.text().catch(() => ''); return null; } return await r.json(); } catch (e) { return null; } };
    const price = personal ? await get('private-data/index.json') : null;
    const priceIdx = price || await get('explorer/sample/index.json');
    let sec = await get('explorer/sec/index.json');
    if (!sec || !sec.entries || !sec.entries.length) sec = await get('explorer/sec-sample/index.json');
    return { priceSet: new Set(((priceIdx && priceIdx.entries) || []).map(e => e.s)), fundSet: new Set(((sec && sec.entries) || []).map(e => e.s)), fundSynthetic: !!(sec && sec.meta && sec.meta.synthetic) };
  }
  const api = { build, render, availability };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.XLinks = api;
})(typeof window !== 'undefined' ? window : globalThis);
