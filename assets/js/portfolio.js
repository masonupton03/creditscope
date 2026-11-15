/* CreditScope portfolio analytics (pure functions: no DOM, no network, no storage).
 *
 * Specification: docs/portfolio-dashboard.md. Verified against an independent Python implementation (tests/ref_portfolio.py).
 * Reuses Finance (finance.js) for dates, index levels, drawdown and statistics so the maths is not copied.
 *
 * Input
 *   portfolio = { version:1, transactions:[{date,type,symbol?,shares?,price?,amount?,fee?,external?}] }
 *   series    = { SYMBOL: Explorer series (dates, close, dividends, splits, type, name) }, must include the benchmark.
 * Output of analyze(): { errors } when the ledger is invalid, otherwise
 *   { asOf, startDate, benchmark, basis, basisLabel, holdings, totals, concentration, allocation, daily, perf, warnings }
 */
(function (root) {
  'use strict';
  const F = typeof module !== 'undefined' && module.exports ? require('./finance.js') : root.Finance;
  const SYMBOL = /^[A-Z0-9][A-Z0-9.\-]{0,9}$/;
  const TYPES = ['deposit', 'withdrawal', 'buy', 'sell', 'dividend', 'fee'];
  const RANK = { deposit: 0, buy: 1, dividend: 2, sell: 3, withdrawal: 4, fee: 5 };   // order within one day
  const PERIODS = ['1M', '3M', '6M', 'YTD', '1Y', '3Y', '5Y', 'ITD'];
  const MAX_TX = 5000, STALE_DAYS = 7, SHARE_TOL = 1e-9, CASH_TOL = 0.005;
  const LABELS = {
    total: 'Time-weighted return, dividends received as cash, net of fees',
    price: 'Time-weighted price return (dividends excluded on both sides)'
  };

  /* ---------- validation ---------- */
  const isDate = s => {
    if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    const d = new Date(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)));
    return d.toISOString().slice(0, 10) === s;
  };
  const num = x => typeof x === 'number' && isFinite(x);

  function validate(p) {
    const errors = [];
    if (!p || typeof p !== 'object' || !Array.isArray(p.transactions)) return [{ index: -1, code: 'BAD_FILE', message: 'portfolio needs a transactions list' }];
    if (p.transactions.length > MAX_TX) errors.push({ index: -1, code: 'TOO_MANY', message: 'more than ' + MAX_TX + ' transactions' });
    p.transactions.forEach((t, index) => {
      const bad = (code, message) => errors.push({ index, code, message });
      if (!t || typeof t !== 'object') return bad('BAD_TX', 'not an object');
      if (!isDate(t.date)) bad('BAD_DATE', 'date must be a real YYYY-MM-DD date');
      if (TYPES.indexOf(t.type) < 0) return bad('BAD_TYPE', 'type must be one of ' + TYPES.join(', '));
      if (t.type === 'buy' || t.type === 'sell' || t.type === 'dividend') {
        if (typeof t.symbol !== 'string' || !SYMBOL.test(t.symbol)) bad('BAD_SYMBOL', 'symbol must look like AAPL or BRK.B');
      }
      if (t.type === 'buy' || t.type === 'sell') {
        if (!num(t.shares) || t.shares <= 0) bad('BAD_SHARES', 'shares must be a positive number');
        if (!num(t.price) || t.price <= 0) bad('BAD_PRICE', 'price must be a positive number');
        if (t.fee != null && (!num(t.fee) || t.fee < 0)) bad('BAD_FEE', 'fee must be zero or positive');
      } else if (!num(t.amount) || t.amount <= 0) bad('BAD_AMOUNT', 'amount must be a positive number');
    });
    return errors;
  }

  /* ---------- helpers ---------- */
  /** Product of split ratios with ex-date after `date` (shares then -> shares on today's split-adjusted basis). */
  function splitFactor(series, date) {
    let f = 1;
    (series && Array.isArray(series.splits) ? series.splits : []).forEach(([ex, ratio]) => { if (ex > date) f *= ratio; });
    return f;
  }
  /** For each calendar index, the index of the security's last close on or before that date (-1 if none). */
  function priceIndex(cal, dates) {
    const out = new Array(cal.length); let j = -1;
    for (let i = 0; i < cal.length; i++) {
      while (j + 1 < dates.length && dates[j + 1] <= cal[i]) j++;
      out[i] = j;
    }
    return out;
  }

  /* ---------- the ledger simulation ---------- */
  function simulate(txs, cal, ctx, includeDividends) {
    const n = cal.length;
    const shares = new Map(), lots = new Map();
    let cash = 0, realized = 0, fees = 0;
    const V = new Array(n).fill(0), CASH = new Array(n).fill(0), FLOW = new Array(n).fill(0);
    const incomplete = new Array(n).fill(false);
    const divBySymbol = new Map(); const errors = []; let t = 0;
    for (let i = 0; i < n; i++) {
      if (includeDividends) {                                   // entitlement = shares held at the previous close
        ctx.autoDiv.forEach((byIdx, sym) => {
          const amt = byIdx.get(i), sh = shares.get(sym) || 0;
          if (amt && sh > 0) { cash += amt * sh; divBySymbol.set(sym, (divBySymbol.get(sym) || 0) + amt * sh); }
        });
      }
      for (; t < txs.length && txs[t].idx === i; t++) {
        const x = txs[t];
        if (x.type === 'deposit') { cash += x.amount; FLOW[i] += x.amount; }
        else if (x.type === 'withdrawal') { cash -= x.amount; FLOW[i] -= x.amount; }
        else if (x.type === 'fee') { cash -= x.amount; fees += x.amount; }
        else if (x.type === 'dividend') {
          if (includeDividends) { cash += x.amount; divBySymbol.set(x.symbol, (divBySymbol.get(x.symbol) || 0) + x.amount); }
        } else if (x.type === 'buy') {
          const cost = x.shares * x.price + x.fee;
          if (x.external) FLOW[i] += cost; else cash -= cost;
          fees += x.fee;
          shares.set(x.symbol, (shares.get(x.symbol) || 0) + x.adj);
          if (!lots.has(x.symbol)) lots.set(x.symbol, []);
          lots.get(x.symbol).push({ sh: x.adj, cost, date: x.date });
        } else if (x.type === 'sell') {
          const held = shares.get(x.symbol) || 0;
          if (x.adj > held * (1 + SHARE_TOL) + SHARE_TOL) {
            errors.push({ index: x.input, code: 'OVERSELL', message: 'sells ' + x.shares + ' ' + x.symbol + ' on ' + x.date + ' but only ' + (held / x.factor) + ' held' });
            continue;
          }
          const proceeds = x.shares * x.price - x.fee;
          if (x.external) FLOW[i] -= proceeds; else cash += proceeds;
          fees += x.fee;
          let need = Math.min(x.adj, held), consumed = 0;
          const L = lots.get(x.symbol);
          while (need > SHARE_TOL * 0.01 && L.length) {
            const lot = L[0], take = Math.min(lot.sh, need), part = lot.cost * (take / lot.sh);
            consumed += part; lot.cost -= part; lot.sh -= take; need -= take;
            if (lot.sh <= SHARE_TOL * 0.01) L.shift();
          }
          realized += proceeds - consumed;
          shares.set(x.symbol, held - Math.min(x.adj, held));
        }
      }
      let v = cash;
      shares.forEach((sh, sym) => {
        if (sh <= 0) return;
        const j = ctx.pidx.get(sym) ? ctx.pidx.get(sym)[i] : -1;
        if (j < 0) { incomplete[i] = true; return; }
        v += sh * ctx.series[sym].close[j];
      });
      V[i] = v; CASH[i] = cash;
    }
    return { V, CASH, FLOW, incomplete, shares, lots, cash, realized, fees, divBySymbol, errors };
  }

  /* ---------- time-weighted chain ---------- */
  function twrChain(V, FLOW, s) {
    const n = V.length; const L = new Array(n).fill(null); const R = new Array(n).fill(null); let skipped = 0;
    L[s] = 1;
    for (let i = s + 1; i < n; i++) {
      if (V[i - 1] > 0) { R[i] = (V[i] - FLOW[i]) / V[i - 1] - 1; L[i] = L[i - 1] * (1 + R[i]); }
      else { R[i] = 0; L[i] = L[i - 1]; skipped++; }
    }
    return { L, R, skipped };
  }

  /* ---------- analyze ---------- */
  function analyze(portfolio, series, opts) {
    opts = opts || {};
    const benchSym = (portfolio && portfolio.benchmark) || opts.benchmark || 'SPY';
    const errors = validate(portfolio).map(e => e);
    if (errors.length) return { errors };
    const bench = series[benchSym];
    if (!bench || !bench.dates || bench.dates.length < 2) return { errors: [{ index: -1, code: 'NO_BENCHMARK', message: 'benchmark ' + benchSym + ' has no price history (sync it first)' }] };
    const cal = bench.dates, n = cal.length, warnings = [];
    const warn = (code, message) => warnings.push({ code, message });

    // 1. order the ledger and map each transaction onto the trading calendar
    const raw = portfolio.transactions.map((t, input) => Object.assign({ input, fee: 0, external: false }, t, { fee: t.fee || 0, external: !!t.external }));
    raw.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : RANK[a.type] - RANK[b.type] || a.input - b.input));
    const txs = []; let dropped = 0, early = 0;
    raw.forEach(x => {
      if (x.date > cal[n - 1]) { dropped++; return; }
      if (x.date < cal[0]) early++;
      x.idx = Math.max(0, F.firstIndexOnOrAfter(cal, x.date));
      if (x.type === 'buy' || x.type === 'sell') { x.factor = splitFactor(series[x.symbol], x.date); x.adj = x.shares * x.factor; }
      txs.push(x);
    });
    if (dropped) warn('TX_AFTER_END', dropped + ' transaction(s) are dated after the last price date (' + cal[n - 1] + ') and are not included');
    if (early) warn('TX_BEFORE_START', early + ' transaction(s) are dated before the first benchmark date (' + cal[0] + ') and are applied on that date');
    if (!txs.length) return { errors: [{ index: -1, code: 'EMPTY', message: 'no transactions to analyse' }] };

    // 2. securities used and what we know about them
    const held = []; const seen = new Set();
    txs.forEach(x => { if (x.type === 'buy' && !seen.has(x.symbol)) { seen.add(x.symbol); held.push(x.symbol); } });
    const manualDiv = new Set(txs.filter(x => x.type === 'dividend').map(x => x.symbol));
    const missing = held.filter(s => !series[s] || !series[s].dates || !series[s].dates.length);
    if (missing.length) return { errors: [{ index: -1, code: 'NO_PRICES', message: 'no price history for ' + missing.join(', ') + ' (sync them, or open them once in the Explorer)', symbols: missing }] };
    const pidx = new Map(); held.forEach(s => pidx.set(s, priceIndex(cal, series[s].dates)));
    const autoDiv = new Map(); const unknownDiv = [];
    held.forEach(s => {
      const d = series[s].dividends;
      if (manualDiv.has(s)) return;
      if (!Array.isArray(d)) { unknownDiv.push(s); return; }
      const byIdx = new Map();
      d.forEach(([ex, amt]) => { if (ex > cal[0] && ex <= cal[n - 1]) { const i = F.firstIndexOnOrAfter(cal, ex); byIdx.set(i, (byIdx.get(i) || 0) + amt); } });
      autoDiv.set(s, byIdx);
    });
    held.forEach(s => { if (!Array.isArray(series[s].splits)) warn('SPLITS_UNKNOWN', s + ': split history is not available, so share counts are not adjusted for any split'); });
    const benchKnown = Array.isArray(bench.dividends);
    const basis = benchKnown && !unknownDiv.length ? 'total' : 'price';
    if (basis === 'price') {
      const why = [].concat(benchKnown ? [] : [benchSym + ' (benchmark)'], unknownDiv);
      warn('PRICE_BASIS', 'Dividend history is unknown for ' + why.join(', ') + ', so performance is shown on a price-only basis for both the portfolio and ' + benchSym + '.');
    }
    const ctx = { series, pidx, autoDiv };

    // 3. simulate (account values always include dividends; performance uses the chosen basis)
    const full = simulate(txs, cal, ctx, true);
    if (full.errors.length) return { errors: full.errors };
    const perfSim = basis === 'total' ? full : simulate(txs, cal, ctx, false);

    // 4. validity of each day
    const i0 = txs[0].idx; let lastBad = -1;
    for (let i = i0; i < n; i++) if (full.incomplete[i]) lastBad = i;
    const s = Math.max(i0, lastBad + 1);
    if (lastBad >= i0) warn('PRICE_GAP_EARLY', 'No price exists for a holding before ' + cal[s] + ', so performance starts on that date (earlier days are not valued at cost).');
    if (s >= n - 1) return { errors: [{ index: -1, code: 'TOO_SHORT', message: 'not enough priced days after the first transaction to compute performance' }] };
    for (let i = i0; i < n; i++) if (full.CASH[i] < -CASH_TOL) { warn('NEGATIVE_CASH', 'Cash goes negative on ' + cal[i] + ' (a purchase without enough deposited cash; mark it "external" or add a deposit).'); break; }
    held.forEach(sym => {
      const sr = series[sym], last = sr.dates[sr.dates.length - 1];
      if (F.daysBetween(last, cal[n - 1]) > STALE_DAYS) warn('PRICE_STALE', sym + ': last price is ' + last + ', older than ' + STALE_DAYS + ' days before ' + cal[n - 1] + '; it is carried forward');
    });

    // 5. performance chain and benchmark levels
    const chain = twrChain(perfSim.V, perfSim.FLOW, s);
    if (chain.skipped) warn('ZERO_VALUE_DAYS', chain.skipped + ' day(s) followed a zero portfolio value and were skipped in the return chain');
    const BL = F.levels(bench, basis);
    const benchR = new Array(n).fill(null); for (let i = 1; i < n; i++) benchR[i] = BL[i] / BL[i - 1] - 1;
    const cumFlow = []; let cf = 0; for (let i = 0; i < n; i++) { cf += full.FLOW[i]; cumFlow.push(cf); }

    // 6. metrics per period
    const perf = {};
    const lastDate = cal[n - 1];
    PERIODS.forEach(period => {
      const sd = period === 'ITD' ? cal[s] : F.startDateFor(period, lastDate, cal[s]);
      let a = F.lastIndexOnOrBefore(cal, sd), truncated = false;
      if (a < s) { a = s; truncated = period !== 'ITD'; }
      const b = n - 1, w = [];
      if (b <= a) { perf[period] = { period, warnings: ['FEW_OBSERVATIONS'] }; return; }
      const days = F.daysBetween(cal[a], cal[b]);
      const twr = chain.L[b] / chain.L[a] - 1;
      const V0 = full.V[a], V1 = full.V[b];                       // the real account (dividends included) for dollar figures
      let netFlows = 0, wsum = 0;
      for (let i = a + 1; i <= b; i++) { const f = perfSim.FLOW[i]; netFlows += f; wsum += f * ((days - F.daysBetween(cal[a], cal[i])) / days); }
      const dietzDen = perfSim.V[a] + wsum;
      const R = [], RB = [];
      for (let i = a + 1; i <= b; i++) { R.push(chain.R[i]); RB.push(benchR[i]); }
      const sd2 = R.length >= F.MIN_VOL_RETURNS ? F.sampleStd(R) : null;
      let beta = null, corr = null;
      if (R.length >= F.MIN_BETA_RETURNS) {
        const vb = F.sampleCov(RB, RB), cab = F.sampleCov(R, RB), sa = F.sampleStd(R), sb = F.sampleStd(RB);
        beta = vb > 0 ? cab / vb : null; corr = sa > 0 && sb > 0 ? cab / (sa * sb) : null;
      }
      const idxs = []; for (let i = a; i <= b; i++) idxs.push(i);
      const benchCum = BL[b] / BL[a] - 1;
      if (truncated) w.push('TRUNCATED');
      if (R.length < F.MIN_VOL_RETURNS) w.push('FEW_OBSERVATIONS');
      perf[period] = {
        period, startDate: cal[a], endDate: cal[b], days, truncated, nReturns: R.length, warnings: w,
        valueStart: V0, valueEnd: V1, valueChange: V1 - V0, netFlows, investmentGain: V1 - V0 - netFlows,
        twr, annualizedTwr: days >= 365 ? Math.pow(1 + twr, 365.25 / days) - 1 : null,
        modifiedDietz: dietzDen > 0 ? (perfSim.V[b] - perfSim.V[a] - netFlows) / dietzDen : null,
        benchmarkReturn: benchCum, excess: twr - benchCum,
        volatility: sd2 === null ? null : sd2 * Math.sqrt(F.TRADING_DAYS),
        benchmarkVolatility: RB.length >= F.MIN_VOL_RETURNS ? F.sampleStd(RB) * Math.sqrt(F.TRADING_DAYS) : null,
        beta, correlation: corr, maxDrawdown: F.maxDrawdown(chain.L, idxs, cal)
      };
    });

    // 7. holdings, totals, concentration, allocation (as of the last date)
    const end = n - 1; const holdings = [];
    full.shares.forEach((sh, sym) => {
      if (sh <= SHARE_TOL * 0.01) return;
      const j = pidx.get(sym)[end], sr = series[sym];
      const price = j >= 0 ? sr.close[j] : null;
      const cost = full.lots.get(sym).reduce((a, l) => a + l.cost, 0);
      const value = price === null ? null : sh * price;
      holdings.push({ symbol: sym, name: sr.name || sym, type: sr.type || '', shares: sh, price, priceDate: j >= 0 ? sr.dates[j] : null,
        costBasis: cost, avgCost: cost / sh, marketValue: value, unrealized: value === null ? null : value - cost,
        unrealizedPct: value === null || cost <= 0 ? null : value / cost - 1, dividendsReceived: full.divBySymbol.get(sym) || 0,
        dividendBasis: manualDiv.has(sym) ? 'manual' : Array.isArray(sr.dividends) ? 'auto' : 'unknown' });
    });
    const cash = full.cash;
    const invested = holdings.reduce((a, h) => a + (h.marketValue || 0), 0);
    const total = cash + invested;
    holdings.forEach(h => { h.weight = total > 0 && h.marketValue !== null ? h.marketValue / total : null; });
    holdings.sort((a, b) => (b.marketValue || 0) - (a.marketValue || 0));
    const cost = holdings.reduce((a, h) => a + h.costBasis, 0);
    const unreal = holdings.reduce((a, h) => a + (h.unrealized || 0), 0);
    const divTotal = Array.from(full.divBySymbol.values()).reduce((a, b) => a + b, 0);
    const ws = holdings.map(h => (invested > 0 ? (h.marketValue || 0) / invested : 0)).sort((a, b) => b - a);
    const hhi = ws.reduce((a, w) => a + w * w, 0);
    const top = k => ws.slice(0, k).reduce((a, b) => a + b, 0);
    const byType = {};
    holdings.forEach(h => { const k = h.type || 'Other'; byType[k] = (byType[k] || 0) + (h.marketValue || 0); });
    const allocation = { bySecurity: holdings.map(h => ({ label: h.symbol, value: h.marketValue || 0 })).concat(cash > CASH_TOL ? [{ label: 'Cash', value: cash }] : []),
      byType: Object.keys(byType).map(k => ({ label: k, value: byType[k] })).concat(cash > CASH_TOL ? [{ label: 'Cash', value: cash }] : []) };

    return {
      errors: [], asOf: lastDate, startDate: cal[s], inceptionDate: cal[i0], benchmark: benchSym, basis, basisLabel: LABELS[basis], warnings,
      holdings,
      totals: { totalValue: total, marketValue: invested, cash, costBasis: cost, unrealized: unreal, unrealizedPct: cost > 0 ? unreal / cost : null,
        realized: full.realized, dividends: divTotal, fees: full.fees },
      concentration: { positions: holdings.length, top1: top(1), top3: top(3), top5: top(5), hhi, effectiveN: hhi > 0 ? 1 / hhi : null,
        largest: holdings.length ? holdings[0].symbol : null },
      allocation,
      daily: { dates: cal.slice(s), value: full.V.slice(s), cash: full.CASH.slice(s), netContributions: cumFlow.slice(s).map(x => x - cumFlow[s]),
        twrLevel: chain.L.slice(s), benchLevel: BL.slice(s).map(v => v / BL[s]) },
      perf
    };
  }

  /** Chart arrays for one period, everything rebased to 100 at the period start. */
  function chart(result, period) {
    const p = result.perf[period]; if (!p || !p.startDate) return null;
    const d = result.daily; const a = d.dates.indexOf(p.startDate);
    const dates = d.dates.slice(a), t0 = d.twrLevel[a], b0 = d.benchLevel[a];
    const twr = d.twrLevel.slice(a).map(v => v / t0 * 100), bench = d.benchLevel.slice(a).map(v => v / b0 * 100);
    let peak = -Infinity;
    const dd = twr.map(v => { if (v > peak) peak = v; return (v / peak - 1) * 100; });
    return { dates, twr, bench, drawdown: dd, value: d.value.slice(a), netContributions: d.netContributions.slice(a).map(v => v - d.netContributions[a]) };
  }

  const api = { PERIODS, LABELS, validate, analyze, chart, splitFactor };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Portfolio = api;
})(typeof window !== 'undefined' ? window : globalThis);
