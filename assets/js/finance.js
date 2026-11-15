/* CreditScope financial calculations for the Stock Explorer.
 *
 * Pure functions (no DOM, no network) so the same code runs in the browser and in Node tests, and is
 * verified against an independent Python implementation (tests/ref_finance.py).
 *
 * Series format
 *   { dates: ['YYYY-MM-DD', ...] ascending trading dates,
 *     close: [...]    split-adjusted closing prices, NOT adjusted for dividends,
 *     volume: [...] | null   shares traded (unadjusted), null entries are skipped,
 *     dividends: [['YYYY-MM-DD', cashPerShare], ...] | null }
 *   dividends === null means "dividend history unknown"; [] means "known, none paid".
 *
 * Return bases (never mixed)
 *   price  Price return = change in the split-adjusted close. Excludes dividends.
 *   total  Total return = dividends reinvested on the ex-dividend date at that day's close.
 *          Chain: TRI[i] = TRI[i-1] * (close[i] + dividend[i]) / close[i-1]. Taxes and fees ignored.
 *          Only available when the security's dividend history is known.
 */
(function (root) {
  'use strict';
  const PERIODS = ['1M', '3M', '6M', 'YTD', '1Y', '3Y', '5Y', 'MAX'];
  const TRADING_DAYS = 252;       // annualisation factor for daily data
  const MIN_VOL_RETURNS = 20;     // fewer daily returns than this: volatility is not reported
  const MIN_BETA_RETURNS = 60;    // fewer overlapping returns than this: beta/correlation not reported
  const EPS = 1e-12;              // relative tolerance: levels closer than this are ties (floating-point noise)
  const LABELS = {
    total: 'Total return (dividends reinvested)',
    price: 'Price return (excludes dividends)'
  };

  /* ---------- dates (calendar arithmetic on ISO strings, no timezones) ---------- */
  const toMs = s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10));
  const daysBetween = (a, b) => Math.round((toMs(b) - toMs(a)) / 86400000);
  const pad = n => (n < 10 ? '0' : '') + n;
  const daysInMonth = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();      // m is 1-12
  function shiftMonths(iso, months) {
    const total = +iso.slice(0, 4) * 12 + (+iso.slice(5, 7) - 1) - months;
    const y = Math.floor(total / 12); const m = (total % 12) + 1;
    const d = Math.min(+iso.slice(8, 10), daysInMonth(y, m));
    return y + '-' + pad(m) + '-' + pad(d);
  }
  /** Calendar date a period starts on (the start price is the last close on or before it). */
  function startDateFor(period, asOf, firstDate) {
    if (period === 'MAX') return firstDate;
    if (period === 'YTD') return (+asOf.slice(0, 4) - 1) + '-12-31';
    const m = /^(\d+)([MY])$/.exec(period);
    if (!m) throw new Error('unknown period ' + period);
    return shiftMonths(asOf, +m[1] * (m[2] === 'Y' ? 12 : 1));
  }
  function lastIndexOnOrBefore(dates, d) {            // -1 if every date is later than d
    let lo = 0, hi = dates.length - 1, ans = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (dates[mid] <= d) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
    return ans;
  }
  function firstIndexOnOrAfter(dates, d) {            // dates.length if none
    let lo = 0, hi = dates.length - 1, ans = dates.length;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (dates[mid] >= d) { ans = mid; hi = mid - 1; } else lo = mid + 1; }
    return ans;
  }

  /* ---------- statistics ---------- */
  const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
  function sampleStd(a) {
    if (a.length < 2) return null;
    const m = mean(a); let ss = 0;
    for (let i = 0; i < a.length; i++) ss += (a[i] - m) * (a[i] - m);
    return Math.sqrt(ss / (a.length - 1));
  }
  function sampleCov(a, b) {
    const ma = mean(a), mb = mean(b); let s = 0;
    for (let i = 0; i < a.length; i++) s += (a[i] - ma) * (b[i] - mb);
    return s / (a.length - 1);
  }

  /* ---------- index levels ---------- */
  /** Dividends keyed by the trading-day index they are credited to (first trading day on/after the ex-date). */
  function dividendsByIndex(series) {
    const out = new Map();
    if (!Array.isArray(series.dividends)) return out;
    const dates = series.dates;
    series.dividends.forEach(([d, amount]) => {
      if (d <= dates[0] || d > dates[dates.length - 1]) return;       // before the first close or after the last
      const i = firstIndexOnOrAfter(dates, d);
      out.set(i, (out.get(i) || 0) + amount);
    });
    return out;
  }
  /** Level series: 'price' = the close itself; 'total' = total-return index starting at 1. */
  function levels(series, basis) {
    const close = series.close;
    if (basis === 'price') return close.slice();
    const divs = dividendsByIndex(series);
    const tri = [1];
    for (let i = 1; i < close.length; i++) tri.push(tri[i - 1] * (close[i] + (divs.get(i) || 0)) / close[i - 1]);
    return tri;
  }
  const returnsOver = (L, idxs) => { const r = []; for (let k = 1; k < idxs.length; k++) r.push(L[idxs[k]] / L[idxs[k - 1]] - 1); return r; };

  /** Largest peak-to-trough fall of a level series over idxs, with peak, trough and recovery dates.
   *  Ties (within EPS) go to the earliest peak and the earliest trough; recovery means getting back to the peak level. */
  function maxDrawdown(L, idxs, dates) {
    let peakVal = L[idxs[0]], peakK = 0, worst = 0, wPeakK = 0, wTroughK = 0;
    for (let k = 0; k < idxs.length; k++) {
      const v = L[idxs[k]];
      if (v > peakVal * (1 + EPS)) { peakVal = v; peakK = k; }
      const dd = v / peakVal - 1;
      if (dd < worst - EPS) { worst = dd; wPeakK = peakK; wTroughK = k; }
    }
    if (worst === 0) return { depth: 0, peakDate: null, troughDate: null, recoveryDate: null };
    const target = L[idxs[wPeakK]] * (1 - EPS);
    let rec = null;
    for (let k = wTroughK + 1; k < idxs.length; k++) { if (L[idxs[k]] >= target) { rec = dates[idxs[k]]; break; } }
    return { depth: worst, peakDate: dates[idxs[wPeakK]], troughDate: dates[idxs[wTroughK]], recoveryDate: rec };
  }

  /** The drawdown ("underwater") curve in percent for charting. */
  function drawdownSeries(L, idxs) {
    let peak = -Infinity; const out = [];
    idxs.forEach(i => { if (L[i] > peak) peak = L[i]; out.push((L[i] / peak - 1) * 100); });
    return out;
  }

  /* ---------- one security over one period ---------- */
  function windowFor(series, period) {
    const dates = series.dates; const n = dates.length;
    const asOf = dates[n - 1];
    const sd = startDateFor(period, asOf, dates[0]);
    let i0 = lastIndexOnOrBefore(dates, sd); let truncated = false;
    if (i0 < 0) { i0 = 0; truncated = period !== 'MAX'; }
    return { i0, i1: n - 1, truncated, startDate: dates[i0], endDate: asOf };
  }

  function summarize(series, period, benchmark) {
    const dates = series.dates; const warnings = [];
    const hasDiv = Array.isArray(series.dividends);
    const w = windowFor(series, period);
    const base = { period, startDate: w.startDate, endDate: w.endDate, truncated: w.truncated, basis: hasDiv ? 'total' : 'price', basisLabel: LABELS[hasDiv ? 'total' : 'price'], warnings };
    if (w.i1 <= w.i0) { warnings.push('FEW_OBSERVATIONS'); return base; }
    if (!hasDiv) warnings.push('NO_DIVIDEND_DATA');
    if (w.truncated) warnings.push('TRUNCATED');
    const idxs = []; for (let i = w.i0; i <= w.i1; i++) idxs.push(i);
    const priceL = levels(series, 'price');
    const totalL = hasDiv ? levels(series, 'total') : null;
    const L = totalL || priceL;
    const cum = L[w.i1] / L[w.i0] - 1;
    const days = daysBetween(dates[w.i0], dates[w.i1]);
    const rets = returnsOver(L, idxs);
    const sd = rets.length >= MIN_VOL_RETURNS ? sampleStd(rets) : null;
    if (sd === null) warnings.push('FEW_OBSERVATIONS');
    const out = Object.assign(base, {
      days, nReturns: rets.length,
      cumulativeReturn: cum,
      priceReturn: priceL[w.i1] / priceL[w.i0] - 1,
      totalReturn: totalL ? totalL[w.i1] / totalL[w.i0] - 1 : null,
      annualizedReturn: days >= 365 ? Math.pow(1 + cum, 365.25 / days) - 1 : null,
      volatility: sd === null ? null : sd * Math.sqrt(TRADING_DAYS),
      maxDrawdown: maxDrawdown(L, idxs, dates)
    });
    // volume (shares, unadjusted) over the window, null entries skipped
    if (Array.isArray(series.volume)) {
      const vs = []; const dv = [];
      idxs.forEach(i => { const v = series.volume[i]; if (v != null) { vs.push(v); dv.push(v * series.close[i]); } });
      out.volume = vs.length ? { avg: mean(vs), avgDollar: mean(dv), latest: series.volume[w.i1] } : null;
    } else out.volume = null;
    // dividends credited inside the window and the trailing-12-month yield
    if (hasDiv) {
      const divs = dividendsByIndex(series); let cash = 0, count = 0, ttm = 0;
      const ttmStart = shiftMonths(dates[w.i1], 12);
      divs.forEach((amt, i) => {
        if (i > w.i0 && i <= w.i1) { cash += amt; count++; }
        if (dates[i] > ttmStart) ttm += amt;
      });
      out.dividends = { cash, count, yieldTTM: ttm / series.close[w.i1] };
    } else out.dividends = null;
    if (benchmark) out.compare = compare(series, benchmark, period);
    return out;
  }

  /* ---------- security vs benchmark on common trading dates ---------- */
  function compare(A, B, period) {
    const w = (a, asOf) => {
      const sd = startDateFor(period, asOf, a.dates[0]);
      const i = lastIndexOnOrBefore(a.dates, sd);
      return i < 0 ? { date: a.dates[0], truncated: period !== 'MAX' } : { date: a.dates[i], truncated: false };
    };
    const lastA = A.dates[A.dates.length - 1], lastB = B.dates[B.dates.length - 1];
    const asOf = lastA < lastB ? lastA : lastB;
    const wa = w(A, asOf), wb = w(B, asOf);
    const s = wa.date > wb.date ? wa.date : wb.date;
    const inB = new Map(); B.dates.forEach((d, i) => inB.set(d, i));
    const ia = [], ib = [], dates = [];
    A.dates.forEach((d, i) => { if (d >= s && d <= asOf && inB.has(d)) { ia.push(i); ib.push(inB.get(d)); dates.push(d); } });
    const warnings = [];
    if (wa.truncated || wb.truncated) warnings.push('TRUNCATED');
    if (dates.length < 2) return { basis: 'price', warnings: warnings.concat('FEW_OBSERVATIONS'), nReturns: 0 };
    const bothTotal = Array.isArray(A.dividends) && Array.isArray(B.dividends);
    const basis = bothTotal ? 'total' : 'price';
    if (!bothTotal) warnings.push('COMPARE_PRICE_BASIS');
    const LA = levels(A, basis), LB = levels(B, basis);
    const seqA = ia.map((_, k) => k), seqB = seqA;
    const la = ia.map(i => LA[i]), lb = ib.map(i => LB[i]);
    const ra = returnsOver(la, seqA), rb = returnsOver(lb, seqB);
    const cumA = la[la.length - 1] / la[0] - 1, cumB = lb[lb.length - 1] / lb[0] - 1;
    let beta = null, corr = null;
    if (ra.length >= MIN_BETA_RETURNS) {
      const vb = sampleCov(rb, rb), cab = sampleCov(ra, rb), sa = sampleStd(ra), sb = sampleStd(rb);
      beta = vb > 0 ? cab / vb : null;
      corr = sa > 0 && sb > 0 ? cab / (sa * sb) : null;
    } else warnings.push('FEW_OBSERVATIONS');
    const a100 = la.map(v => v / la[0] * 100), b100 = lb.map(v => v / lb[0] * 100);
    return {
      basis, basisLabel: LABELS[basis], warnings, startDate: dates[0], endDate: dates[dates.length - 1], nReturns: ra.length,
      cumulativeReturnA: cumA, cumulativeReturnB: cumB, excessReturn: cumA - cumB, beta, correlation: corr,
      series: { dates, a: a100, b: b100, relative: a100.map((v, k) => v / b100[k] * 100) }
    };
  }

  /* ---------- chart helpers ---------- */
  /** Level arrays for the chosen period, rebased to 100, plus the drawdown curve (primary basis). */
  function chartData(series, period) {
    const w = windowFor(series, period);
    const idxs = []; for (let i = w.i0; i <= w.i1; i++) idxs.push(i);
    const hasDiv = Array.isArray(series.dividends);
    const L = levels(series, hasDiv ? 'total' : 'price');
    return {
      dates: idxs.map(i => series.dates[i]), close: idxs.map(i => series.close[i]),
      volume: Array.isArray(series.volume) ? idxs.map(i => series.volume[i]) : null,
      growth: idxs.map(i => L[i] / L[w.i0] * 100),
      priceGrowth: idxs.map(i => series.close[i] / series.close[w.i0] * 100),
      drawdown: drawdownSeries(L, idxs), basis: hasDiv ? 'total' : 'price'
    };
  }

  const api = { PERIODS, TRADING_DAYS, MIN_VOL_RETURNS, MIN_BETA_RETURNS, EPS, LABELS, startDateFor, shiftMonths, daysBetween,
    lastIndexOnOrBefore, firstIndexOnOrAfter, levels, dividendsByIndex, maxDrawdown, drawdownSeries, summarize, compare, chartData,
    sampleStd, sampleCov, returnsOver, mean };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Finance = api;
})(typeof window !== 'undefined' ? window : globalThis);
