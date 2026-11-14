/* CreditScope Stock Explorer: symbol search and watchlist logic (pure functions, Node-testable).
 *
 * Index entry: { s: 'AAPL', n: 'Apple Inc. Common Stock', t: 'S' | 'E', x: 'Nasdaq', r: 1 }
 *   s ticker, n company or fund name, t S(tock) / E(TF), x exchange, r optional popularity rank (1 = most popular)
 */
(function (root) {
  'use strict';
  /** Lower-case, strip punctuation that varies between sources (BRK.B / BRK-B / BRK B). */
  const squash = s => String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9]/g, '');
  const words = s => String(s == null ? '' : s).toLowerCase().replace(/&/g, ' and ').split(/[^a-z0-9]+/).filter(Boolean);
  // generic words that should not make a match on their own
  const STOP = new Set(['inc', 'corp', 'co', 'ltd', 'plc', 'the', 'of', 'and', 'etf', 'fund', 'trust', 'common', 'stock', 'class', 'shares', 'ordinary']);

  function buildIndex(entries) {
    return entries.map((e, i) => ({ e, i, tk: squash(e.s), nm: words(e.n), nmFlat: words(e.n).join(' ') }));
  }

  function score(item, q, qWords) {
    const tk = item.tk;
    if (tk === q) return 1000;
    if (tk.startsWith(q)) return 900 - Math.min(tk.length - q.length, 50);
    if (item.nmFlat.startsWith(qWords.join(' '))) return 700;
    // every query word is a prefix of some name word
    if (qWords.length && qWords.every(w => item.nm.some(nw => nw.startsWith(w)))) {
      const significant = qWords.some(w => !STOP.has(w));
      return significant ? 600 : 100;
    }
    if (qWords.length && q.length >= 3 && item.nmFlat.includes(qWords.join(' '))) return 400;   // mid-word matches only for 3+ characters
    if (q.length >= 2 && tk.includes(q)) return 300;
    return 0;
  }

  /** Best matches first. Ties: lower popularity rank, then ticker. Returns the original entries. */
  function search(index, query, limit) {
    limit = limit || 8;
    const q = squash(query); const qWords = words(query);
    if (!q) return [];
    const scored = [];
    index.forEach(item => { const s = score(item, q, qWords); if (s > 0) scored.push([s, item]); });
    scored.sort((a, b) => b[0] - a[0] || (a[1].e.r || 1e9) - (b[1].e.r || 1e9) || (a[1].e.s < b[1].e.s ? -1 : 1));
    return scored.slice(0, limit).map(x => x[1].e);
  }

  /* ---------- watchlist ---------- */
  const TICKER = /^[A-Z0-9][A-Z0-9.\-]{0,9}$/;
  const MAX_WATCH = 100;
  /** Accept whatever was stored; return a clean, de-duplicated list of valid tickers. */
  function cleanList(raw) {
    let list = raw;
    if (typeof raw === 'string') { try { list = JSON.parse(raw); } catch (e) { list = []; } }
    if (!Array.isArray(list)) return [];
    const seen = new Set(); const out = [];
    list.forEach(t => { const s = typeof t === 'string' ? t.trim().toUpperCase() : ''; if (TICKER.test(s) && !seen.has(s)) { seen.add(s); out.push(s); } });
    return out.slice(0, MAX_WATCH);
  }
  const watch = {
    KEY: 'creditscope.watchlist',
    MAX: MAX_WATCH,
    clean: cleanList,
    add: (list, t) => cleanList(list.concat(String(t).toUpperCase())),
    remove: (list, t) => cleanList(list.filter(x => x !== String(t).toUpperCase())),
    has: (list, t) => list.indexOf(String(t).toUpperCase()) >= 0,
    /** storage: anything with getItem/setItem (localStorage, or a fake in tests). Never throws. */
    load(storage) { try { return cleanList(storage.getItem(watch.KEY)); } catch (e) { return []; } },
    save(storage, list) { try { storage.setItem(watch.KEY, JSON.stringify(cleanList(list))); return true; } catch (e) { return false; } }
  };

  const api = { squash, buildIndex, search, watch };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.ExplorerSearch = api;
})(typeof window !== 'undefined' ? window : globalThis);
