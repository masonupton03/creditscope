/* Side-by-side comparison of several securities over one COMMON window (pure functions; verified against tests/ref_compare.py).
 *
 * Rules
 *   window    ends on the earliest "last date" among the securities; starts at the LATEST of each security's own period start, so
 *             everything is measured over exactly the same dates (only dates on which all of them traded are used)
 *   basis     'total' (dividends reinvested) only if EVERY security (and the benchmark, if given) has a known dividend history;
 *             otherwise 'price' for ALL of them, and the ones lacking dividends are listed. The two are never mixed.
 *   metrics   cumulative return, annualized (windows of 365+ days), volatility (sample stdev x sqrt(252), 20+ returns),
 *             maximum drawdown with dates, beta and correlation versus the benchmark and pairwise correlation (60+ returns)
 */
(function (root) {
  'use strict';
  const F = typeof module !== 'undefined' && module.exports ? require('./finance.js') : root.Finance;
  const LABELS = { total: 'Total return (dividends reinvested)', price: 'Price return (excludes dividends)' };
  const MAX_SECURITIES = 6;

  function compare(list, period, benchmark) {
    const warnings = [];
    if (!list || list.length < 2) return { errors: [{ code: 'TOO_FEW', message: 'Pick at least two securities to compare.' }] };
    const all = benchmark && !list.some(s => s.symbol === benchmark.symbol) ? list.concat([benchmark]) : list;
    const asOf = all.map(s => s.dates[s.dates.length - 1]).reduce((a, b) => (a < b ? a : b));
    let start = null, truncated = false;
    all.forEach(s => {
      const sd = F.startDateFor(period, asOf, s.dates[0]);
      let i = F.lastIndexOnOrBefore(s.dates, sd), d;
      if (i < 0) { d = s.dates[0]; truncated = truncated || period !== 'MAX'; } else d = s.dates[i];
      if (start === null || d > start) start = d;
    });
    const inAll = new Map();                                                       // date -> [index in each series]
    all[0].dates.forEach((d, i) => { if (d >= start && d <= asOf) inAll.set(d, [i]); });
    for (let k = 1; k < all.length; k++) {
      const pos = new Map(all[k].dates.map((d, i) => [d, i]));
      for (const d of Array.from(inAll.keys())) { if (pos.has(d)) inAll.get(d).push(pos.get(d)); else inAll.delete(d); }
    }
    const dates = Array.from(inAll.keys()).sort();
    if (dates.length < 2) return { errors: [{ code: 'NO_OVERLAP', message: 'These securities share fewer than two trading dates in this period.' }] };
    if (truncated) warnings.push({ code: 'TRUNCATED', message: 'At least one security has less history than ' + period + ', so everything is measured from ' + dates[0] + '.' });
    const lacking = all.filter(s => !Array.isArray(s.dividends)).map(s => s.symbol);
    const basis = lacking.length ? 'price' : 'total';
    if (lacking.length) warnings.push({ code: 'PRICE_BASIS', message: 'Dividend history is unknown for ' + lacking.join(', ') + ', so all returns here are price returns (dividends excluded) to keep the comparison fair.' });

    const level = all.map((s, k) => { const L = F.levels(s, basis); return dates.map(d => L[inAll.get(d)[k]]); });
    const seq = dates.map((_, i) => i);
    const rets = level.map(L => F.returnsOver(L, seq));
    const days = F.daysBetween(dates[0], dates[dates.length - 1]);
    const bIdx = benchmark ? all.findIndex(s => s.symbol === benchmark.symbol) : -1;
    const stat = (k) => {
      const L = level[k], r = rets[k], cum = L[L.length - 1] / L[0] - 1;
      let beta = null, corr = null;
      if (bIdx >= 0 && r.length >= F.MIN_BETA_RETURNS) {
        const vb = F.sampleCov(rets[bIdx], rets[bIdx]), c = F.sampleCov(r, rets[bIdx]), sa = F.sampleStd(r), sb = F.sampleStd(rets[bIdx]);
        beta = vb > 0 ? c / vb : null; corr = sa > 0 && sb > 0 ? c / (sa * sb) : null;
      }
      return { symbol: all[k].symbol, name: all[k].name || all[k].symbol, cumulative: cum, annualized: days >= 365 ? Math.pow(1 + cum, 365.25 / days) - 1 : null,
        volatility: r.length >= F.MIN_VOL_RETURNS ? F.sampleStd(r) * Math.sqrt(F.TRADING_DAYS) : null, maxDrawdown: F.maxDrawdown(L, seq, dates), beta, correlationToBenchmark: corr };
    };
    const shown = list.map(s => all.indexOf(s));
    const stats = shown.map(stat);
    let corr = null;
    if (rets[0].length >= F.MIN_BETA_RETURNS) {
      corr = shown.map(a => shown.map(b => {
        const sa = F.sampleStd(rets[a]), sb = F.sampleStd(rets[b]);
        return sa > 0 && sb > 0 ? F.sampleCov(rets[a], rets[b]) / (sa * sb) : null;
      }));
    } else warnings.push({ code: 'FEW_OBSERVATIONS', message: 'Fewer than ' + F.MIN_BETA_RETURNS + ' shared daily returns: beta and correlation are not shown.' });
    if (rets[0].length < F.MIN_VOL_RETURNS) warnings.push({ code: 'FEW_OBSERVATIONS_VOL', message: 'Fewer than ' + F.MIN_VOL_RETURNS + ' shared daily returns: volatility is not shown.' });
    if (benchmark && bIdx < 0) warnings.push({ code: 'NO_BENCHMARK', message: 'No benchmark data, so beta is not shown.' });
    const growth = {}, dd = {};
    shown.forEach((k, j) => { growth[list[j].symbol] = level[k].map(v => v / level[k][0] * 100); dd[list[j].symbol] = drawdown(level[k]); });
    return { errors: [], basis, basisLabel: LABELS[basis], startDate: dates[0], endDate: dates[dates.length - 1], days, nReturns: rets[0].length, benchmark: benchmark ? benchmark.symbol : null,
      stats, correlation: corr, symbols: list.map(s => s.symbol), growth: { dates, series: growth }, drawdown: dd, warnings };
  }
  function drawdown(L) { let peak = -Infinity; return L.map(v => { if (v > peak) peak = v; return (v / peak - 1) * 100; }); }

  const api = { LABELS, MAX_SECURITIES, compare };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.CompareCalc = api;
})(typeof window !== 'undefined' ? window : globalThis);
