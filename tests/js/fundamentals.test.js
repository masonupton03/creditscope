const test = require('node:test'); const assert = require('node:assert/strict');
const C = require('../../assets/js/fundamentals-calc.js');
const close = (a, b, m) => assert.ok(a !== null && Math.abs(a - b) < 1e-12, `${m}: ${a} vs ${b}`);
const co = rows => ({ metrics: Object.fromEntries(Object.entries(rows).map(([k, pairs]) => [k, { label: k, points: pairs.map(([fy, val]) => ({ fy, val, end: fy + '-12-31', accn: '0000000001-24-000001' })) }])) });

test('growth, margins, returns and cash-flow ratios on hand-checkable numbers', () => {
  const a = C.analyze(co({ revenue: [[2022, 100], [2023, 120]], grossProfit: [[2023, 48]], operatingIncome: [[2023, 24]], netIncome: [[2023, 12]],
    equity: [[2022, 50], [2023, 70]], assets: [[2022, 200], [2023, 240]], liabilities: [[2023, 170]], debt: [[2023, 35]], cash: [[2023, 20]],
    operatingCashFlow: [[2023, 30]], capex: [[2023, 10]] }));
  const r = a.ratios[2023];
  close(r.revenueGrowth, 0.2, 'growth'); close(r.grossMargin, 0.4, 'gross'); close(r.operatingMargin, 0.2, 'op'); close(r.netMargin, 0.1, 'net');
  close(r.roe, 12 / 60, 'ROE uses average equity'); close(r.roa, 12 / 220, 'ROA uses average assets'); close(r.debtToEquity, 0.5, 'D/E');
  close(r.netDebt, 15, 'net debt'); close(r.fcf, 20, 'FCF'); close(r.fcfMargin, 20 / 120, 'FCF margin'); close(r.liabilitiesToAssets, 170 / 240, 'L/A');
  assert.equal(a.ratios[2022].revenueGrowth, null);
});

test('blank, never zero, when a denominator is not positive or a year is missing', () => {
  const a = C.analyze(co({ revenue: [[2020, 0], [2021, 50], [2023, 80]], netIncome: [[2020, 1], [2021, 2], [2023, 3]], equity: [[2021, -5], [2022, 4], [2023, 6]], debt: [[2023, 3]] }));
  assert.equal(a.ratios[2020].netMargin, null); assert.equal(a.ratios[2021].revenueGrowth, null);           // previous revenue is zero
  assert.equal(a.ratios[2023].revenueGrowth, null);                                                         // 2022 is missing: no growth across the gap
  assert.equal(a.ratios[2021].roe, null);                                                                   // negative equity
  close(a.ratios[2023].roe, 3 / 5, 'ROE with both years'); assert.ok(a.warnings.some(w => w.code === 'NEGATIVE_EQUITY'));
  assert.ok(C.analyze(co({ revenue: [[2018, 1], [2021, 2]] })).warnings.some(w => w.code === 'GAPS'));
});

test('derived gross profit is flagged and CAGR needs both ends and the exact span', () => {
  const rev = []; for (let y = 2015; y <= 2024; y++) rev.push([y, 100 * Math.pow(1.1, y - 2015)]);
  const a = C.analyze(co({ revenue: rev, costOfRevenue: [[2024, 60]] }));
  assert.equal(a.ratios[2024].grossProfitDerived, true); close(a.ratios[2024].grossProfit, 100 * Math.pow(1.1, 9) - 60, 'gp');
  close(a.cagr[3], 0.1, 'cagr3'); close(a.cagr[5], 0.1, 'cagr5');
  assert.equal(C.analyze(co({ revenue: [[2020, 10], [2024, 20]] })).cagr[3], null);
});

test('freshness and filing links', () => {
  const f = C.freshness({ latestFiled: '2025-02-01', latestPeriodEnd: '2024-12-31', generated: '2026-11-14T00:00:00Z' }, '2026-11-14');
  assert.equal(f.daysSinceFiled, 651); assert.equal(f.stale, true); assert.equal(f.daysSinceCompiled, 0);
  assert.equal(C.freshness({ latestFiled: '2026-02-01', generated: '2026-11-14T00:00:00Z' }, '2026-11-14').stale, false);
  assert.equal(C.filingUrl(320193, '0000320193-24-000123'), 'https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/0000320193-24-000123-index.htm');
});

test('return on equity is blank when equity turns negative, even if the average is positive', () => {
  const a = C.analyze(co({ revenue: [[2022, 10], [2023, 10]], netIncome: [[2023, 5]], equity: [[2022, 10], [2023, -2]] }));
  assert.equal(a.ratios[2023].roe, null);
});
