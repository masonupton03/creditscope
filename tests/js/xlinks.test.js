const test = require('node:test'); const assert = require('node:assert/strict');
const X = require('../../assets/js/xlinks.js');

test('links go to the other pages with the same ticker and only when data exists', () => {
  const all = X.build('AAPL', { price: true, fund: true }, 'explorer');
  assert.deepEqual(all.map(i => [i.key, i.href, i.enabled]), [['fundamentals', 'fundamentals.html#AAPL', true], ['compare', 'compare.html#s=AAPL,SPY&p=1Y', true]]);
  const noFund = X.build('AAPL', { price: true, fund: false, fundSynthetic: true }, 'explorer');
  assert.equal(noFund[0].enabled, false); assert.match(noFund[0].reason, /fictional companies/);
  const fundOnly = X.build('DEMA', { price: false, fund: true }, 'fundamentals');
  assert.deepEqual(fundOnly.map(i => [i.key, i.enabled]), [['explorer', false], ['compare', false]]);
  assert.match(fundOnly[0].reason, /No price history for DEMA/);
});

test('SPY compares with a different peer, invalid tickers produce nothing, the current page is omitted', () => {
  assert.equal(X.build('SPY', { price: true, fund: false }, 'explorer')[1].href, 'compare.html#s=SPY,QQQ&p=1Y');
  assert.deepEqual(X.build('<script>', { price: true, fund: true }), []); assert.deepEqual(X.build('', {}), []);
  assert.ok(!X.build('MSFT', { price: true, fund: true }, 'compare').some(i => i.key === 'compare'));
});
