const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { buildIndex, search, watch, squash } = require('../../assets/js/search.js');

const E = [
  { s: 'AAPL', n: 'Apple Inc.', t: 'S', x: 'Nasdaq', r: 3 },
  { s: 'APLE', n: 'Apple Hospitality REIT, Inc.', t: 'S', x: 'NYSE', r: 90 },
  { s: 'SPY', n: 'SPDR S&P 500 ETF Trust', t: 'E', x: 'NYSE Arca', r: 1 },
  { s: 'SPYG', n: 'SPDR Portfolio S&P 500 Growth ETF', t: 'E', x: 'NYSE Arca', r: 60 },
  { s: 'BRK.B', n: 'Berkshire Hathaway Inc. Class B', t: 'S', x: 'NYSE', r: 5 },
  { s: 'TLT', n: 'iShares 20+ Year Treasury Bond ETF', t: 'E', x: 'Nasdaq', r: 6 },
  { s: 'JPM', n: 'JPMorgan Chase & Co.', t: 'S', x: 'NYSE', r: 23 },
  { s: 'AMZN', n: 'Amazon.com, Inc.', t: 'S', x: 'Nasdaq', r: 17 }
];
const idx = buildIndex(E);
const tickers = q => search(idx, q).map(e => e.s);

test('exact ticker beats prefix and name matches', () => { assert.deepEqual(tickers('spy').slice(0, 2), ['SPY', 'SPYG']); assert.equal(tickers('AAPL')[0], 'AAPL'); });
test('ticker prefix', () => assert.deepEqual(tickers('sp'), ['SPY', 'SPYG']));
test('company name, case and punctuation insensitive', () => {
  assert.equal(tickers('apple')[0], 'AAPL');                    // lower popularity rank number wins the tie
  assert.ok(tickers('apple').includes('APLE'));
  assert.deepEqual(tickers('BERKSHIRE hathaway'), ['BRK.B']);
  assert.equal(tickers('amazon')[0], 'AMZN');
  assert.equal(tickers('jp morgan').length, 0);                  // honest: "jp morgan" is not a prefix of "jpmorgan"
  assert.equal(tickers('jpmorgan')[0], 'JPM');
});
test('punctuation in tickers is ignored', () => { assert.equal(tickers('brk.b')[0], 'BRK.B'); assert.equal(tickers('brkb')[0], 'BRK.B'); assert.equal(tickers('brk b')[0], 'BRK.B'); });
test('ampersand and multiword names', () => { assert.equal(tickers('s&p 500')[0], 'SPY'); assert.equal(tickers('treasury bond')[0], 'TLT'); });
test('empty, whitespace and no-match queries return nothing; limit is honoured', () => {
  assert.deepEqual(tickers(''), []); assert.deepEqual(tickers('   '), []); assert.deepEqual(tickers('zzzzzz'), []); assert.deepEqual(tickers('!!!'), []);
  assert.equal(search(idx, 'a', 3).length <= 3, true);
});
test('generic words alone rank below real matches', () => { const r = tickers('etf'); assert.ok(r.length > 0); assert.ok(!tickers('inc').includes('SPY')); });
test('results are the original entries', () => assert.deepEqual(search(idx, 'tlt')[0], E[5]));
test('every simulated security is findable by its ticker and by the start of its name', () => {
  const sample = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'explorer', 'sample', 'index.json'), 'utf8')).entries;
  const si = buildIndex(sample);
  sample.forEach(e => {
    assert.equal(search(si, e.s)[0].s, e.s, 'ticker ' + e.s);
    assert.ok(search(si, e.n.split(/\s+/)[0], 10).some(x => x.s === e.s), 'name ' + e.n);
  });
});

function fakeStorage(seed) { const m = new Map(seed ? [[watch.KEY, seed]] : []); return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v), raw: () => m.get(watch.KEY) }; }
test('watchlist: add, remove, de-duplicate, upper-case, validate', () => {
  let l = []; l = watch.add(l, 'aapl'); l = watch.add(l, 'AAPL'); l = watch.add(l, 'brk.b'); l = watch.add(l, 'bad ticker!'); l = watch.add(l, '');
  assert.deepEqual(l, ['AAPL', 'BRK.B']); assert.ok(watch.has(l, 'aapl'));
  assert.deepEqual(watch.remove(l, 'aapl'), ['BRK.B']);
});
test('watchlist persists through storage and survives corrupt or missing data', () => {
  const st = fakeStorage(); assert.deepEqual(watch.load(st), []);
  assert.ok(watch.save(st, ['spy', 'qqq', 'spy']));
  assert.equal(st.raw(), '["SPY","QQQ"]'); assert.deepEqual(watch.load(fakeStorage(st.raw())), ['SPY', 'QQQ']);
  assert.deepEqual(watch.load(fakeStorage('not json')), []); assert.deepEqual(watch.load(fakeStorage('{"a":1}')), []);
  assert.deepEqual(watch.load(fakeStorage('[1,null,"ok","  tsla "]')), ['OK', 'TSLA']);
  const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  assert.deepEqual(watch.load(broken), []); assert.equal(watch.save(broken, ['SPY']), false);
});
test('watchlist is capped', () => {
  const many = Array.from({ length: 150 }, (_, i) => 'T' + i);
  assert.equal(watch.clean(many).length, watch.MAX);
});
test('squash', () => assert.equal(squash(' BRK.B-x '), 'brkbx'));
