// Checks assets/js/stats.js (the code the Trends/Today pages run in the browser) against numbers
// computed independently in Python (tests/ref_stats.py) from the same history.csv, plus edge cases.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Stats = require('../../assets/js/stats.js');

const dir = path.join(__dirname, '..', 'fixtures', 'sample');
const csv = fs.readFileSync(path.join(dir, 'history.csv'), 'utf8');
const expected = JSON.parse(fs.readFileSync(path.join(dir, 'expected.json'), 'utf8'));
const rows = Stats.parseHistory(csv);
const report = Stats.trendsReport(rows);

const close = (a, b, msg) => {
  if (a === null || b === null) return assert.equal(a, b, msg);
  assert.ok(Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b)), `${msg}: ${a} vs ${b}`);
};
function same(a, b, label) {
  if (typeof b === 'number' || b === null) return close(a, b, label);
  if (Array.isArray(b)) { assert.equal(a.length, b.length, label + ' length'); b.forEach((x, i) => same(a[i], x, `${label}[${i}]`)); return; }
  if (typeof b === 'object') { Object.keys(b).forEach(k => same(a[k], b[k], `${label}.${k}`)); return; }
  assert.equal(a, b, label);
}

test('parses every row of history.csv', () => {
  assert.equal(rows.length, expected.n_rows);
  assert.equal(report.meta.n_rows, expected.n_rows);
});
test('meta: runs, sessions, items, dates', () => {
  const m = report.meta;
  assert.equal(m.n_runs, expected.n_runs); assert.equal(m.n_sessions, expected.n_sessions); assert.equal(m.n_items, expected.n_items);
  assert.equal(m.first_run_date, expected.first_run_date); assert.equal(m.last_run_date, expected.last_run_date);
  assert.deepEqual(m.session_dates, expected.session_dates);
});
test('finding 1: returns since the first session', () => {
  same(report.returns.map(r => ({ item_id: r.item_id, first_price: r.first_price, last_price: r.last_price, ret_pct: r.ret_pct })), expected.returns, 'returns');
  same(report.latestMoves.map(r => ({ item_id: r.item_id, pct_change: r.pct_change })), expected.latest_moves, 'latestMoves');
});
test('finding 2: biggest single-day move and per-session averages', () => {
  same(report.biggest, expected.biggest, 'biggest');
  same(report.perSession, expected.per_session, 'perSession');
});
test('finding 3: stocks vs bonds', () => {
  same(report.classDaily, expected.class_daily, 'classDaily');
  close(report.classCumulative.Stock, expected.class_cumulative.Stock, 'Stock cumulative');
  close(report.classCumulative.Bond, expected.class_cumulative.Bond, 'Bond cumulative');
});
test('finding 4: volume', () => {
  same(report.volume.map(v => ({ item_id: v.item_id, avg_volume: v.avg_volume, latest_volume: v.latest_volume, ratio: v.ratio, n: v.n, share: v.share })), expected.volume, 'volume');
});
test('Today page: biggest moves match the pipeline move rule', () => {
  const c = Stats.runComparison(rows);
  assert.equal(c.latest, expected.run_comparison.latest); assert.equal(c.prev, expected.run_comparison.prev);
  assert.equal(c.newSession, expected.run_comparison.new_session);
  same(c.movers.map(m => ({ item_id: m.item_id, pct: m.pct })), expected.run_comparison.movers, 'movers');
});

const HEAD = 'date,item_id,item,source,asset_class,category,price,volume,net_change,pct_change,price_date,market_status\n';
const line = (d, id, price, vol, pct, pd, cls) => `${d},${id},${id} ETF,nasdaq-${id},${cls || 'Stock'},c,${price},${vol},,${pct},${pd},Closed\n`;

test('csv parser handles quotes, commas, CRLF and empty cells', () => {
  const t = HEAD.replace('\n', '\r\n') + '2026-11-14,SPY,"Trust, The ""Big"" ETF",nasdaq-SPY,Stock,c,100.5,,,, ,Closed\r\n';
  const r = Stats.parseHistory(t);
  assert.equal(r.length, 1); assert.equal(r[0].item, 'Trust, The "Big" ETF');
  assert.equal(r[0].price, 100.5); assert.equal(r[0].volume, null); assert.equal(r[0].pct_change, null);
});
test('empty history gives an empty, non-crashing report', () => {
  assert.deepEqual(Stats.parseHistory(''), []);
  assert.deepEqual(Stats.parseHistory(HEAD), []);
  const rep = Stats.trendsReport([]);
  assert.equal(rep.meta.n_sessions, 0); assert.equal(rep.biggest, null); assert.deepEqual(rep.returns, []); assert.deepEqual(rep.volume, []);
});
test('one session: no returns yet, but latest moves and volume work', () => {
  const rep = Stats.trendsReport(Stats.parseHistory(HEAD + line('2026-11-14', 'A', 10, 500, 1.5, '2026-11-13') + line('2026-11-14', 'B', 20, 300, -2, '2026-11-13', 'Bond')));
  assert.equal(rep.meta.n_sessions, 1); assert.deepEqual(rep.returns, []);
  assert.deepEqual(rep.latestMoves.map(m => m.item_id), ['A', 'B']);
  assert.equal(rep.biggest.item_id, 'B'); assert.equal(rep.volume.length, 2);
  assert.equal(rep.classCumulative.gap, null);
});
test('weekend carry-over rows do not count as new sessions or moves', () => {
  const t = HEAD + line('2026-11-13', 'A', 100, 10, 1, '2026-11-13') + line('2026-11-14', 'A', 100, 10, 1, '2026-11-13') + line('2026-11-15', 'A', 100, 10, 1, '2026-11-13') + line('2026-11-16', 'A', 110, 12, 10, '2026-11-16');
  const rep = Stats.trendsReport(Stats.parseHistory(t));
  assert.equal(rep.meta.n_runs, 4); assert.equal(rep.meta.n_sessions, 2);
  assert.deepEqual(rep.meta.session_dates, ['2026-11-13', '2026-11-16']);
  close(rep.returns[0].ret_pct, 10, 'return');
  assert.equal(rep.perSession.length, 2);
  const c = Stats.runComparison(Stats.parseHistory(t));
  assert.equal(c.newSession, true); close(c.movers[0].pct, 10, 'mover');
  const sat = Stats.runComparison(Stats.parseHistory(HEAD + line('2026-11-14', 'A', 100, 10, 1, '2026-11-13') + line('2026-11-15', 'A', 100, 10, 1, '2026-11-13')));
  assert.equal(sat.newSession, false); assert.deepEqual(sat.movers, []);
});
test('missing volume/price cells are skipped, not treated as zero', () => {
  const t = HEAD + line('2026-11-12', 'A', 100, 1000, 1, '2026-11-12') + line('2026-11-13', 'A', 100, '', 0, '2026-11-13') + line('2026-11-16', 'A', 100, 3000, 0, '2026-11-16');
  const v = Stats.trendsReport(Stats.parseHistory(t)).volume[0];
  close(v.avg_volume, 2000, 'avg volume'); assert.equal(v.n, 2); close(v.ratio, 1.5, 'ratio');
});
test('a source failure on one day leaves that ETF out of that session only', () => {
  const t = HEAD + line('2026-11-12', 'A', 100, 1, 1, '2026-11-12') + line('2026-11-12', 'B', 50, 1, 1, '2026-11-12') + line('2026-11-13', 'A', 101, 1, 1, '2026-11-13');
  const rep = Stats.trendsReport(Stats.parseHistory(t));
  assert.equal(rep.meta.n_sessions, 2); assert.deepEqual(rep.returns.map(r => r.item_id), ['A']);
});
test('an intraday run is replaced by the later run for the same session', () => {
  const t = HEAD + line('2026-11-12', 'A', 100, 1, 0, '2026-11-12') + line('2026-11-13', 'A', 105, 1, 0, '2026-11-13') + line('2026-11-13', 'A', 106, 1, 0, '2026-11-13').replace('2026-11-13,A', '2026-11-14,A');
  const rep = Stats.trendsReport(Stats.parseHistory(t.replace('106,1,,0,2026-11-13', '106,1,,0,2026-11-13')));
  close(rep.returns[0].last_price, 106, 'latest run wins');
});
