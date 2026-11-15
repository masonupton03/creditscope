// Hand-computed cases for assets/js/portfolio.js. Every expected number below can be checked with a calculator.
const test = require('node:test');
const assert = require('node:assert/strict');
const P = require('../../assets/js/portfolio.js');

const close = (a, b, msg, tol) => { tol = tol || 1e-9; assert.ok(a !== null && Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), `${msg}: ${a} vs ${b}`); };
function weekdays(n) {
  const out = []; let d = new Date(Date.UTC(2026, 0, 5));
  while (out.length < n) { if (d.getUTCDay() % 6 !== 0) out.push(d.toISOString().slice(0, 10)); d = new Date(d.getTime() + 86400000); }
  return out;
}
const D = weekdays(40);
const mk = (close, o) => Object.assign({ dates: D.slice(0, close.length), close, volume: null, dividends: [], splits: [], type: 'Stock', name: 'X' }, o || {});
const flat = n => mk(new Array(n).fill(100), { type: 'ETF' });
const tx = (i, type, o) => Object.assign({ date: D[i], type }, o);
const run = (txs, series, extra) => P.analyze(Object.assign({ version: 1, transactions: txs }, extra || {}), series);

test('TWR, simple value change, investment gain and Modified Dietz are different numbers', () => {
  const r = run([tx(0, 'deposit', { amount: 1000 }), tx(0, 'buy', { symbol: 'X', shares: 10, price: 100 }),
                 tx(1, 'deposit', { amount: 1100 }), tx(1, 'buy', { symbol: 'X', shares: 10, price: 110 })],
                { SPY: flat(3), X: mk([100, 110, 99]) });
  assert.deepEqual(r.errors, []);
  const p = r.perf.ITD;
  close(p.twr, 1.1 * 0.9 - 1, 'TWR is -1%');
  close(p.valueChange, 980, 'account value rose by 980');
  close(p.netFlows, 1100, 'net contributions after the start');
  close(p.investmentGain, -120, 'but the investment lost 120');
  close(p.modifiedDietz, -120 / 1550, 'Dietz: flow weighted one half');
  assert.ok(p.valueChange > 0 && p.twr < 0);
});

test('a split is applied to historical share counts', () => {
  const x = mk([50, 55, 60.5], { splits: [[D[1], 2]] });
  const r = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true })], { SPY: flat(3), X: x });
  const h = r.holdings[0];
  close(h.shares, 20, 'adjusted shares'); close(h.costBasis, 1000, 'cost unchanged'); close(h.marketValue, 1210, 'value');
  close(h.unrealized, 210, 'unrealised'); close(r.perf.ITD.twr, 0.21, 'twr');
  const bad = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true })], { SPY: flat(3), X: mk([50, 55, 60.5], { splits: null }) });
  assert.ok(bad.warnings.some(w => w.code === 'SPLITS_UNKNOWN'));
});

test('dividends go to cash for shares held at the previous close, not for same-day buys', () => {
  const x = mk(new Array(4).fill(100), { dividends: [[D[2], 2]] });
  const r = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true }),
                 tx(2, 'buy', { symbol: 'X', shares: 10, price: 100, external: true })], { SPY: flat(4), X: x });
  assert.equal(r.basis, 'total');
  close(r.totals.cash, 20, 'cash = 10 shares x 2'); close(r.totals.dividends, 20, 'dividends received');
  close(r.perf.ITD.twr, 0.02, 'a 2 dividend on 100 is 2%');
});

test('unknown dividend history switches both sides to price and excludes dividends', () => {
  const x = mk(new Array(4).fill(100), { dividends: null });
  const r = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true })], { SPY: flat(4), X: x });
  assert.equal(r.basis, 'price'); assert.ok(r.warnings.some(w => w.code === 'PRICE_BASIS'));
  close(r.perf.ITD.twr, 0, 'no dividends counted');
  const manual = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true }), tx(2, 'dividend', { symbol: 'X', amount: 30 })],
                     { SPY: flat(4), X: x });
  assert.equal(manual.basis, 'total'); close(manual.totals.cash, 30, 'manual dividend');
  assert.equal(manual.holdings[0].dividendBasis, 'manual');
});

test('FIFO cost basis, realised and unrealised gains, fees', () => {
  const r = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true }),
                 tx(0, 'buy', { symbol: 'X', shares: 10, price: 120, external: true }),
                 tx(1, 'sell', { symbol: 'X', shares: 15, price: 130, fee: 5, external: true })], { SPY: flat(3), X: mk([120, 130, 140]) });
  close(r.totals.realized, (15 * 130 - 5) - (1000 + 5 * 120), 'realised = proceeds - FIFO cost');
  const h = r.holdings[0];
  close(h.shares, 5, 'remaining'); close(h.costBasis, 600, 'cost of the remaining lot'); close(h.avgCost, 120, 'avg');
  close(h.unrealized, 5 * 140 - 600, 'unrealised'); close(r.totals.fees, 5, 'fees');
  const fee = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, fee: 10, external: true })], { SPY: flat(3), X: mk([100, 100, 100]) });
  close(fee.holdings[0].costBasis, 1010, 'fee capitalised'); close(fee.holdings[0].unrealized, -10, 'fee shows as a loss');
});

test('concentration and allocation', () => {
  const r = run([tx(0, 'buy', { symbol: 'A', shares: 30, price: 100, external: true }), tx(0, 'buy', { symbol: 'B', shares: 10, price: 100, external: true }),
                 tx(0, 'deposit', { amount: 500 })], { SPY: flat(3), A: mk([100, 100, 100]), B: mk([100, 100, 100], { type: 'ETF' }) });
  const c = r.concentration;
  close(c.top1, 0.75, 'top1'); close(c.hhi, 0.625, 'hhi'); close(c.effectiveN, 1.6, 'effective N'); assert.equal(c.largest, 'A');
  close(r.holdings[0].weight, 3000 / 4500, 'weight includes cash in the denominator');
  assert.deepEqual(r.allocation.byType.map(x => x.label).sort(), ['Cash', 'ETF', 'Stock']);
});

test('missing prices: carried forward, stale warned, early gap moves the start, never valued at cost', () => {
  const x = mk([100, 100, 110, 110], {}); x.dates = [D[0], D[1], D[3], D[4]];                   // no close on D[2]
  const r = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true })], { SPY: flat(5), X: x });
  assert.deepEqual(r.daily.value.map(Math.round), [1000, 1000, 1000, 1100, 1100]);
  const late = mk([100, 100], {}); late.dates = [D[3], D[4]];
  const g = run([tx(0, 'deposit', { amount: 500 }), tx(1, 'buy', { symbol: 'X', shares: 5, price: 100 })], { SPY: flat(6), X: late });
  assert.ok(g.warnings.some(w => w.code === 'PRICE_GAP_EARLY')); assert.equal(g.startDate, D[3]);
  const stale = mk([100, 100]); const long = flat(20);
  const s = run([tx(0, 'buy', { symbol: 'X', shares: 1, price: 100, external: true })], { SPY: long, X: stale });
  assert.ok(s.warnings.some(w => w.code === 'PRICE_STALE'));
});

test('calendar: weekend trades move to the next trading day, later trades are ignored, same-day order is deposit before buy', () => {
  const sat = '2026-01-10';                                                                    // between D[4] (Fri) and D[5] (Mon)
  const r = run([{ date: sat, type: 'buy', symbol: 'X', shares: 1, price: 100, external: true }, tx(0, 'deposit', { amount: 1 }),
                 { date: '2030-01-01', type: 'deposit', amount: 99 }], { SPY: flat(8), X: mk([100, 100, 100, 100, 100, 100, 100, 100]) });
  assert.ok(r.warnings.some(w => w.code === 'TX_AFTER_END'));
  assert.equal(r.daily.value[4], 1); assert.equal(r.daily.value[5], 101 - 0);
  const same = run([tx(1, 'buy', { symbol: 'X', shares: 1, price: 100 }), tx(1, 'deposit', { amount: 100 })], { SPY: flat(4), X: mk([100, 100, 100, 100]) });
  assert.deepEqual(same.errors, []); assert.ok(!same.warnings.some(w => w.code === 'NEGATIVE_CASH'));
  const neg = run([tx(1, 'buy', { symbol: 'X', shares: 1, price: 100 }), tx(0, 'fee', { amount: 1 })], { SPY: flat(4), X: mk([100, 100, 100, 100]) });
  assert.ok(neg.warnings.some(w => w.code === 'NEGATIVE_CASH'));
});

test('withdrawals reduce value but not the time-weighted return', () => {
  const r = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true }), tx(1, 'sell', { symbol: 'X', shares: 5, price: 100, external: true })],
                { SPY: flat(3), X: mk([100, 100, 100]) });
  close(r.perf.ITD.twr, 0, 'twr'); close(r.perf.ITD.valueChange, -500, 'value fell'); close(r.perf.ITD.investmentGain, 0, 'gain zero');
});

test('invalid ledgers and missing data produce errors, not numbers', () => {
  assert.equal(run([tx(0, 'deposit', { amount: -5 })], { SPY: flat(3) }).errors[0].code, 'BAD_AMOUNT');
  assert.equal(run([tx(0, 'sell', { symbol: 'X', shares: 1, price: 1 })], { SPY: flat(3), X: mk([1, 1, 1]) }).errors[0].code, 'OVERSELL');
  assert.equal(run([tx(0, 'deposit', { amount: 1 })], {}).errors[0].code, 'NO_BENCHMARK');
  assert.equal(P.validate(null)[0].code, 'BAD_FILE');
  assert.equal(P.validate({ transactions: [tx(0, 'deposit', { amount: 1, date: '2026-02-29' })] })[0].code, 'BAD_DATE');
});

test('chart arrays rebase to 100 and share the period start', () => {
  const r = run([tx(0, 'buy', { symbol: 'X', shares: 10, price: 100, external: true })], { SPY: flat(5), X: mk([100, 110, 121, 121, 133.1]) });
  const c = P.chart(r, 'ITD');
  close(c.twr[0], 100, 'start'); close(c.twr[4], 133.1, 'end'); close(c.bench[4], 100, 'flat benchmark'); assert.equal(c.dates.length, 5);
  assert.ok(c.drawdown.every(v => v <= 0));
});
