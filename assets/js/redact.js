/* Redaction helpers for the portfolio "hide everything" view (pure functions, unit-tested in tests/js/redact.test.js).
 * The view replaces each ticker with a neutral label ("Holding A") and removes company names; text that may mention a ticker or a
 * name (warnings, error messages) is passed through clean() before it reaches the page. */
(function (root) {
  'use strict';
  const letters = i => { let s = ''; i += 1; while (i > 0) { const r = (i - 1) % 26; s = String.fromCharCode(65 + r) + s; i = Math.floor((i - 1) / 26); } return s; };
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  /** Stable aliases in the order given (callers pass the largest holding first). */
  function aliasMap(symbols) {
    const map = {}; let n = 0;
    symbols.forEach(s => { if (!(s in map)) map[s] = 'Holding ' + letters(n++); });
    return map;
  }
  /** Replace tickers and company names in free text. Longest first so BRK.B is not left as BRK. */
  function clean(text, aliases, names) {
    let out = String(text == null ? '' : text);
    (names || []).filter(n => n && n.length > 2).sort((a, b) => b.length - a.length).forEach(n => { out = out.replace(new RegExp(esc(n), 'gi'), 'a security'); });
    Object.keys(aliases || {}).sort((a, b) => b.length - a.length).forEach(sym => {
      out = out.replace(new RegExp('(^|[^A-Za-z0-9.\\-])(' + esc(sym) + ')(?![A-Za-z0-9\\-])', 'g'), (m, pre) => pre + aliases[sym]);
    });
    return out;
  }
  const api = { aliasMap, clean, letters };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Redact = api;
})(typeof window !== 'undefined' ? window : globalThis);
