const test = require('node:test'); const assert = require('node:assert/strict');
const R = require('../../assets/js/redact.js');

test('aliases are neutral, stable and unique', () => {
  const m = R.aliasMap(['AAPL', 'KO', 'AAPL', 'BRK.B']);
  assert.deepEqual(m, { AAPL: 'Holding A', KO: 'Holding B', 'BRK.B': 'Holding C' });
  assert.equal(R.letters(25), 'Z'); assert.equal(R.letters(26), 'AA'); assert.equal(R.letters(27), 'AB');
  assert.equal(Object.values(R.aliasMap(Array.from({ length: 80 }, (_, i) => 'S' + i))).length, 80);
});

test('clean removes tickers as whole words and company names, in any text', () => {
  const m = R.aliasMap(['KO', 'BRK.B', 'BRK', 'T']);
  assert.equal(R.clean('KO: split history is not available', m), 'Holding A: split history is not available');
  assert.equal(R.clean('Dividend history unknown for KO, BRK.B', m), 'Dividend history unknown for Holding A, Holding B');
  assert.equal(R.clean('https://x/api/series/KO returned HTTP 502', m), 'https://x/api/series/Holding A returned HTTP 502');
  assert.equal(R.clean('KOALA and OKO and KO.', m), 'KOALA and OKO and Holding A.');                       // not inside other words
  assert.equal(R.clean('Coca-Cola Company sells 5 KO', m, ['Coca-Cola Company']), 'a security sells 5 Holding A');
  assert.equal(R.clean(null, m), ''); assert.equal(R.clean('no names here', {}), 'no names here');
  assert.ok(!/BRK/.test(R.clean('BRK.B and BRK', m)));                                                      // longest symbol first
});
