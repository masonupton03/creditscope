// Checks assets/js/finance.js against (1) hand-computed cases and (2) numbers computed independently in Python
// (tests/ref_finance.py) for every simulated security and period.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const F = require('../../assets/js/finance.js');

const close = (a, b, msg, tol) => {
  if (a === null || b === null || a === undefined || b === undefined) return assert.equal(a == null ? null : a, b == null ? null : b, msg);
  tol = tol || 1e-9;
  assert.ok(Math.abs(a - b) <= tol * Math.max(1, Math.abs(a), Math.abs(b)), `${msg}: ${a} vs ${b}`);
};
// consecutive weekdays starting 2026-01-05 (a Monday)
function weekdays(n, start) {
  const out = []; let d = new Date(Date.UTC(...(start || [2026, 0, 5])));
  while (out.length < n) { if (d.getUTCDay() % 6 !== 0) out.push(d.toISOString().slice(0, 10)); d = new Date(d.getTime() + 86400000); }
  return out;
}
const mk = (close, o) => Object.assign({ dates: weekdays(close.length), close, volume: null, dividends: null }, o || {});
const fromReturns = (r, p0) => { const c = [p0 || 100]; r.forEach(x => c.push(c[c.length - 1] * (1 + x))); return c; };

test('period start dates use calendar arithmetic and clamp month ends', () => {
  assert.equal(F.startDateFor('1M', '2026-11-13'), '2026-10-13');
  assert.equal(F.startDateFor('3M', '2026-11-13'), '2026-08-13');
  assert.equal(F.startDateFor('6M', '2026-11-13'), '2026-05-13');
  assert.equal(F.startDateFor('1Y', '2026-11-13'), '2025-11-13');
  assert.equal(F.startDateFor('5Y', '2026-11-13'), '2021-11-13');
  assert.equal(F.startDateFor('YTD', '2026-11-13'), '2025-12-31');
  assert.equal(F.startDateFor('1M', '2026-03-31'), '2026-02-28');
  assert.equal(F.startDateFor('1M', '2024-03-31'), '2024-02-29');
  assert.equal(F.startDateFor('1Y', '2024-02-29'), '2023-02-28');
  assert.equal(F.startDateFor('MAX', '2026-11-13', '2016-11-14'), '2016-11-14');
  assert.throws(() => F.startDateFor('2W', '2026-11-13'));
});

test('price return and drawdown on a simple series', () => {
  const s = mk([100, 110, 121]);
  const r = F.summarize(s, 'MAX');
  close(r.cumulativeReturn, 0.21, 'cum'); close(r.priceReturn, 0.21, 'price'); assert.equal(r.totalReturn, null);
  assert.equal(r.basis, 'price'); assert.equal(r.maxDrawdown.depth, 0); assert.equal(r.maxDrawdown.peakDate, null);
  assert.ok(r.warnings.includes('NO_DIVIDEND_DATA'));
});

test('max drawdown: depth, peak, trough, recovery, not recovered, first deepest wins', () => {
  const dates = weekdays(4);
  let dd = F.maxDrawdown([100, 90, 99, 110], [0, 1, 2, 3], dates);
  close(dd.depth, -0.1, 'depth'); assert.equal(dd.peakDate, dates[0]); assert.equal(dd.troughDate, dates[1]); assert.equal(dd.recoveryDate, dates[3]);
  dd = F.maxDrawdown([100, 80, 90, 95], [0, 1, 2, 3], dates);
  close(dd.depth, -0.2, 'depth'); assert.equal(dd.recoveryDate, null);
  dd = F.maxDrawdown([100, 90, 100, 90], [0, 1, 2, 3], dates);
  assert.equal(dd.troughDate, dates[1]); assert.equal(dd.recoveryDate, dates[2]);          // recovered exactly to the peak
  dd = F.maxDrawdown([100, 120, 60, 90], [0, 1, 2, 3], dates);
  close(dd.depth, -0.5, 'depth from the higher peak'); assert.equal(dd.peakDate, dates[1]);
});

test('drawdown ignores floating-point noise: equal levels do not move the peak', () => {
  const dates = weekdays(5);
  const noisy = [1, 1.5, 1.5 * (1 + 1e-15), 1.2, 1.5 * (1 - 1e-15)];       // a "new peak" and a "recovery" that differ only by rounding
  const dd = F.maxDrawdown(noisy, [0, 1, 2, 3, 4], dates);
  assert.equal(dd.peakDate, dates[1]); assert.equal(dd.troughDate, dates[3]); assert.equal(dd.recoveryDate, dates[4]);
  close(dd.depth, 1.2 / 1.5 - 1, 'depth');
});

test('total return reinvests dividends on the ex-date; price return does not', () => {
  const dates = weekdays(3);
  const s = { dates, close: [100, 100, 100], volume: null, dividends: [[dates[2], 2]] };
  const r = F.summarize(s, 'MAX');
  assert.equal(r.basis, 'total'); close(r.totalReturn, 0.02, 'total'); close(r.priceReturn, 0, 'price'); close(r.cumulativeReturn, 0.02, 'primary is total');
  assert.equal(r.basisLabel, 'Total return (dividends reinvested)');
  assert.equal(r.dividends.count, 1); close(r.dividends.cash, 2, 'cash');
});

test('dividend credited to the next trading day when the ex-date is not a trading day; out-of-range dividends ignored', () => {
  const dates = ['2026-01-02', '2026-01-05', '2026-01-06'];                // Fri, Mon, Tue
  const s = { dates, close: [100, 100, 100], volume: null, dividends: [['2026-01-03', 1], ['2025-12-01', 5], ['2026-02-01', 7], ['2026-01-02', 9]] };
  const m = F.dividendsByIndex(s);
  assert.deepEqual(Array.from(m.entries()), [[1, 1]]);                       // Saturday ex-date -> Monday; before/at first close and after the last ignored
  close(F.levels(s, 'total')[2], 1.01, 'TRI');
});

test('compounding of dividends and price changes', () => {
  const dates = weekdays(3);
  const s = { dates, close: [100, 102, 101], volume: null, dividends: [[dates[1], 1], [dates[2], 1]] };
  const tri = F.levels(s, 'total');
  close(tri[1], (102 + 1) / 100, 'day1'); close(tri[2], ((102 + 1) / 100) * ((101 + 1) / 102), 'day2');
});

test('annualised return only for windows of a year or more, using 365.25-day years', () => {
  const dates = ['2025-01-01', '2026-02-05'];                              // 400 days
  const r = F.summarize({ dates, close: [100, 200], volume: null, dividends: null }, 'MAX');
  assert.equal(r.days, 400); close(r.annualizedReturn, Math.pow(2, 365.25 / 400) - 1, 'cagr');
  const s = F.summarize({ dates: ['2025-01-01', '2025-12-31'], close: [100, 200], volume: null, dividends: null }, 'MAX');
  assert.equal(s.days, 364); assert.equal(s.annualizedReturn, null);
});

test('volatility: sample standard deviation of daily returns times sqrt(252), needs 20 returns', () => {
  const r = []; for (let i = 0; i < 40; i++) r.push(i % 2 ? -0.01 : 0.01);
  const s = mk(fromReturns(r));
  const out = F.summarize(s, 'MAX');
  close(out.volatility, Math.sqrt(40 * 0.0001 / 39) * Math.sqrt(252), 'vol');
  assert.equal(F.summarize(mk(fromReturns(r.slice(0, 10))), 'MAX').volatility, null);
  assert.ok(F.summarize(mk(fromReturns(r.slice(0, 10))), 'MAX').warnings.includes('FEW_OBSERVATIONS'));
});

test('window starts at the last close on or before the period start; short history is flagged', () => {
  const dates = weekdays(300); const s = mk(dates.map((_, i) => 100 + i));
  const r = F.summarize(s, '1M');
  assert.ok(r.startDate <= F.startDateFor('1M', dates[299])); assert.ok(F.daysBetween(r.startDate, r.endDate) < 34);
  assert.equal(r.truncated, false);
  const short = F.summarize(mk(Array.from({ length: 50 }, (_, i) => 100 + i)), '1Y');
  assert.equal(short.truncated, true); assert.ok(short.warnings.includes('TRUNCATED')); assert.equal(short.startDate, short.startDate && weekdays(50)[0]);
  assert.equal(F.summarize(mk(Array.from({ length: 50 }, (_, i) => 100 + i)), 'MAX').truncated, false);
  const ytd = F.summarize({ dates: ['2025-12-30', '2025-12-31', '2026-01-02', '2026-03-02'], close: [90, 100, 101, 110], volume: null, dividends: null }, 'YTD');
  assert.equal(ytd.startDate, '2025-12-31'); close(ytd.cumulativeReturn, 0.1, 'ytd from last close of prior year');
});

test('volume statistics skip missing values and use unadjusted shares', () => {
  const s = mk([10, 20, 30], { volume: [100, null, 300] });
  const v = F.summarize(s, 'MAX').volume;
  close(v.avg, 200, 'avg'); close(v.avgDollar, (100 * 10 + 300 * 30) / 2, 'avg $'); assert.equal(v.latest, 300);
  assert.equal(F.summarize(mk([10, 20]), 'MAX').volume, null);
});

test('trailing-twelve-month dividend yield', () => {
  const dates = ['2025-06-02', '2025-12-01', '2026-06-01', '2026-11-13'];
  const s = { dates, close: [100, 100, 100, 200], volume: null, dividends: [['2025-12-01', 1], ['2026-06-01', 2], ['2025-06-02', 99]] };
  close(F.summarize(s, 'MAX').dividends.yieldTTM, 3 / 200, 'ttm');         // the 2025-06-02 payment is credited nowhere (first close) and outside the 12 months
});

function pair(n, dividendsA, dividendsB, k) {
  const dates = weekdays(n); const rb = [];
  for (let i = 0; i < n - 1; i++) rb.push(((i * 37) % 11 - 5) / 400);
  const ra = rb.map(x => (k || 2) * x);
  return [{ dates, close: fromReturns(ra), volume: null, dividends: dividendsA }, { dates, close: fromReturns(rb), volume: null, dividends: dividendsB }];
}
test('beta and correlation against the benchmark; same basis on both sides', () => {
  const [a, b] = pair(130, [], [], 2);
  const c = F.compare(a, b, 'MAX');
  assert.equal(c.basis, 'total'); close(c.beta, 2, 'beta', 1e-9); close(c.correlation, 1, 'corr', 1e-9); assert.equal(c.nReturns, 129);
  close(c.excessReturn, c.cumulativeReturnA - c.cumulativeReturnB, 'excess');
  close(c.series.a[0], 100, 'rebased'); close(c.series.relative[0], 100, 'relative');
  const [a2, b2] = pair(130, [], [], -1);
  close(F.compare(a2, b2, 'MAX').beta, -1, 'negative beta', 1e-9);
});
test('comparison falls back to price basis when either side lacks dividend data', () => {
  let [a, b] = pair(130, null, [], 1.5);
  let c = F.compare(a, b, 'MAX');
  assert.equal(c.basis, 'price'); assert.ok(c.warnings.includes('COMPARE_PRICE_BASIS')); assert.equal(c.basisLabel, 'Price return (excludes dividends)');
  [a, b] = pair(130, [], null, 1.5);
  assert.equal(F.compare(a, b, 'MAX').basis, 'price');
  const sum = F.summarize(a, 'MAX', b);
  assert.equal(sum.basis, 'total'); assert.equal(sum.compare.basis, 'price');   // the security keeps its own basis; the comparison says which one it used
});
test('too few overlapping returns: beta and correlation are withheld', () => {
  const [a, b] = pair(40, [], [], 2);
  const c = F.compare(a, b, 'MAX');
  assert.equal(c.beta, null); assert.equal(c.correlation, null); assert.ok(c.warnings.includes('FEW_OBSERVATIONS'));
});
test('comparison uses only dates both series traded', () => {
  const [a, b] = pair(100, [], [], 2);
  const a2 = { dates: a.dates.filter((_, i) => i !== 50), close: a.close.filter((_, i) => i !== 50), volume: null, dividends: [] };
  const c = F.compare(a2, b, 'MAX');
  assert.equal(c.series.dates.length, 99); assert.ok(!c.series.dates.includes(b.dates[50]));
});
test('chart helpers: growth of 100 on the primary basis and the drawdown curve', () => {
  const s = mk([100, 110, 99, 110]);
  const c = F.chartData(s, 'MAX');
  close(c.growth[3], 110, 'growth'); close(c.drawdown[2], (99 / 110 - 1) * 100, 'drawdown'); assert.equal(c.basis, 'price');
  const t = F.chartData({ dates: weekdays(3), close: [100, 100, 100], volume: null, dividends: [[weekdays(3)[2], 2]] }, 'MAX');
  close(t.growth[2], 102, 'total growth'); close(t.priceGrowth[2], 100, 'price growth'); assert.equal(t.basis, 'total');
});

/* ---------- against the independent Python implementation ---------- */
const SAMPLE = path.join(__dirname, '..', '..', 'explorer', 'sample');
const expected = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'fixtures', 'explorer_expected.json'), 'utf8'));
const index = JSON.parse(fs.readFileSync(path.join(SAMPLE, 'index.json'), 'utf8'));
const load = sym => JSON.parse(fs.readFileSync(path.join(SAMPLE, 'series', sym + '.json'), 'utf8'));
const spy = load('SPY');
function sameScalars(got, want, label) {
  Object.keys(want).forEach(k => {
    const w = want[k];
    if (k === 'compare' || k === 'maxDrawdown' || k === 'volume' || k === 'dividends') return;
    if (typeof w === 'number' || w === null) close(got[k], w, `${label}.${k}`);
    else assert.equal(got[k], w, `${label}.${k}`);
  });
}
test('all simulated securities and periods match the independent Python implementation', () => {
  let checked = 0;
  index.entries.forEach(e => {
    const s = load(e.s);
    expected.periods.forEach(period => {
      const want = expected.summaries[e.s][period]; const label = `${e.s}/${period}`;
      const got = F.summarize(s, period, e.s === 'SPY' ? null : spy);
      sameScalars(got, want, label);
      if (want.maxDrawdown) ['depth'].forEach(k => close(got.maxDrawdown[k], want.maxDrawdown[k], `${label}.dd.${k}`));
      if (want.maxDrawdown) ['peakDate', 'troughDate', 'recoveryDate'].forEach(k => assert.equal(got.maxDrawdown[k], want.maxDrawdown[k], `${label}.dd.${k}`));
      if (want.volume === null || want.volume === undefined) assert.equal(got.volume == null ? null : got.volume, want.volume == null ? null : want.volume, label + '.volume');
      else ['avg', 'avgDollar', 'latest'].forEach(k => close(got.volume[k], want.volume[k], `${label}.volume.${k}`));
      if (want.dividends === null || want.dividends === undefined) assert.equal(got.dividends == null ? null : got.dividends, want.dividends == null ? null : want.dividends, label + '.dividends');
      else ['cash', 'count', 'yieldTTM'].forEach(k => close(got.dividends[k], want.dividends[k], `${label}.dividends.${k}`));
      if (want.compare) {
        const wc = want.compare; const gc = got.compare;
        ['basis', 'nReturns', 'startDate', 'endDate'].forEach(k => assert.equal(gc[k], wc[k], `${label}.compare.${k}`));
        ['cumulativeReturnA', 'cumulativeReturnB', 'excessReturn', 'beta', 'correlation'].forEach(k => close(gc[k], wc[k], `${label}.compare.${k}`));
        if (wc.checkpoints) {
          assert.equal(gc.series.dates.length, wc.checkpoints.n, label + ' compare length');
          wc.checkpoints.at.forEach((idx, j) => {
            assert.equal(gc.series.dates[idx], wc.checkpoints.dates[j]);
            ['a', 'b', 'relative'].forEach(k => close(gc.series[k][idx], wc.checkpoints[k][j], `${label}.compare.series.${k}[${idx}]`));
          });
        }
      }
      checked++;
    });
  });
  assert.equal(checked, index.entries.length * expected.periods.length);
});
test('the simulated data exercises every labelling state', () => {
  const bases = new Set(); const warns = new Set();
  index.entries.forEach(e => { const r = F.summarize(load(e.s), '1Y', e.s === 'SPY' ? null : spy); bases.add(r.basis + (r.compare ? '/' + r.compare.basis : '')); r.warnings.forEach(w => warns.add(w)); (r.compare ? r.compare.warnings : []).forEach(w => warns.add(w)); });
  assert.ok(bases.has('total/total') && bases.has('price/price') && bases.has('total') , Array.from(bases).join(','));
  assert.ok(warns.has('NO_DIVIDEND_DATA') && warns.has('COMPARE_PRICE_BASIS'));
  assert.equal(F.summarize(load('RDDT'), '5Y').truncated, true);
});
