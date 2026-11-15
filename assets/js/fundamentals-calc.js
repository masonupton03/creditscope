/* Financial-statement ratios from a reduced SEC company file (fundamentals/reduce.py). Pure functions: no DOM, no network.
 * Verified against an independent Python implementation (tests/ref_fundamentals.py).
 *
 * Definitions (every denominator must be positive, otherwise the ratio is null, never 0 or a guess)
 *   revenue growth     Revenue(t) / Revenue(t-1) - 1, only when fiscal year t-1 is present
 *   gross profit       as reported, else Revenue - Cost of revenue (marked derived)
 *   gross / operating / net margin    metric / Revenue
 *   return on equity   Net income / average(Equity(t), Equity(t-1)); needs BOTH year-ends positive (a year that crosses zero is blank)
 *   return on assets   Net income / average(Assets(t), Assets(t-1))
 *   debt to equity     Debt / Equity, only when Equity > 0
 *   net debt           Debt - Cash (needs both)
 *   free cash flow     Operating cash flow - Capital expenditure (needs both); FCF margin = FCF / Revenue
 *   liabilities / assets
 *   revenue CAGR (n)   (Revenue(L) / Revenue(L-n)) ^ (1/n) - 1 over n fiscal years, both ends positive
 */
(function (root) {
  'use strict';
  const RATIOS = ['revenueGrowth', 'grossMargin', 'operatingMargin', 'netMargin', 'roe', 'roa', 'debtToEquity', 'netDebt', 'fcf', 'fcfMargin', 'liabilitiesToAssets'];
  const STALE_DAYS = 460;                                   // an annual report older than this means a newer one is probably missing
  const days = (a, b) => Math.round((Date.UTC(+b.slice(0, 4), +b.slice(5, 7) - 1, +b.slice(8, 10)) - Date.UTC(+a.slice(0, 4), +a.slice(5, 7) - 1, +a.slice(8, 10))) / 86400000);

  function analyze(company) {
    const M = company.metrics || {};
    const V = {};                                            // V[key][fy] = point
    Object.keys(M).forEach(k => { V[k] = {}; M[k].points.forEach(p => { V[k][p.fy] = p; }); });
    const val = (k, y) => (V[k] && V[k][y] ? V[k][y].val : null);
    const yearsSet = new Set(); Object.keys(V).forEach(k => Object.keys(V[k]).forEach(y => yearsSet.add(+y)));
    const years = Array.from(yearsSet).sort((a, b) => a - b);
    const warnings = [];
    const ratio = (num, den) => (num == null || den == null || den <= 0 ? null : num / den);
    const avg = (k, y) => { const a = val(k, y), b = val(k, y - 1); return a == null || b == null ? null : (a + b) / 2; };
    const out = {};
    const derivedGP = [];
    years.forEach(y => {
      const rev = val('revenue', y), prev = val('revenue', y - 1);
      let gp = val('grossProfit', y);
      if (gp == null && rev != null && val('costOfRevenue', y) != null) { gp = rev - val('costOfRevenue', y); derivedGP.push(y); }
      const eq = val('equity', y), debt = val('debt', y), cash = val('cash', y);
      const ocf = val('operatingCashFlow', y), capex = val('capex', y);
      const fcf = ocf != null && capex != null ? ocf - capex : null;
      const ae = avg('equity', y), aa = avg('assets', y), ni = val('netIncome', y);
      out[y] = {
        revenueGrowth: rev != null && prev != null && prev > 0 ? rev / prev - 1 : null,
        grossMargin: ratio(gp, rev), operatingMargin: ratio(val('operatingIncome', y), rev), netMargin: ratio(ni, rev),
        roe: ni != null && ae != null && ae > 0 && val('equity', y) > 0 && val('equity', y - 1) > 0 ? ni / ae : null, roa: ni != null && aa != null && aa > 0 ? ni / aa : null,
        debtToEquity: debt != null && eq != null && eq > 0 ? debt / eq : null,
        netDebt: debt != null && cash != null ? debt - cash : null,
        fcf, fcfMargin: ratio(fcf, rev), liabilitiesToAssets: ratio(val('liabilities', y), val('assets', y)),
        grossProfit: gp, grossProfitDerived: derivedGP.indexOf(y) >= 0
      };
    });
    const revYears = years.filter(y => val('revenue', y) != null);
    const L = revYears.length ? revYears[revYears.length - 1] : null;
    const cagr = {};
    [3, 5].forEach(n => {
      const a = L == null ? null : val('revenue', L - n), b = L == null ? null : val('revenue', L);
      cagr[n] = a != null && b != null && a > 0 && b > 0 ? Math.pow(b / a, 1 / n) - 1 : null;
    });
    const negEq = years.filter(y => val('equity', y) != null && val('equity', y) <= 0);
    if (negEq.length) warnings.push({ code: 'NEGATIVE_EQUITY', years: negEq, message: 'Shareholders\' equity is zero or negative in ' + negEq.join(', ') + ': return on equity and debt-to-equity are not meaningful and are left blank.' });
    const missing = ['revenue', 'netIncome', 'operatingIncome', 'assets', 'liabilities', 'equity', 'cash', 'debt', 'operatingCashFlow', 'capex'].filter(k => !V[k]);
    if (missing.length) warnings.push({ code: 'MISSING_METRICS', metrics: missing, message: 'Not reported under the standard tags used here: ' + missing.map(k => M[k] ? M[k].label : k).join(', ') + '. Ratios that need them are blank.' });
    const gaps = []; for (let i = 1; i < years.length; i++) if (years[i] - years[i - 1] > 1) gaps.push(years[i - 1] + '→' + years[i]);
    if (gaps.length) warnings.push({ code: 'GAPS', gaps, message: 'Fiscal years are missing between ' + gaps.join(', ') + '; growth and averages across the gap are blank.' });
    if (derivedGP.length) warnings.push({ code: 'DERIVED_GROSS_PROFIT', years: derivedGP, message: 'Gross profit is revenue minus cost of revenue in ' + derivedGP.join(', ') + ' (not reported as a total).' });
    return { years, ratios: out, cagr, latestFiscalYear: L, warnings, values: V };
  }

  /** Data freshness relative to `today` (YYYY-MM-DD). */
  function freshness(company, today) {
    const ageFiled = company.latestFiled ? days(company.latestFiled, today) : null;
    return { latestPeriodEnd: company.latestPeriodEnd, latestFiled: company.latestFiled, generated: company.generated,
      daysSinceFiled: ageFiled, daysSinceCompiled: company.generated ? days(company.generated.slice(0, 10), today) : null,
      stale: ageFiled != null && ageFiled > STALE_DAYS };
  }

  /** SEC filing index page for an accession number (real companies only). */
  function filingUrl(cik, accn) {
    return 'https://www.sec.gov/Archives/edgar/data/' + parseInt(cik, 10) + '/' + String(accn).replace(/-/g, '') + '/' + accn + '-index.htm';
  }

  const api = { RATIOS, STALE_DAYS, analyze, freshness, filingUrl };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.FundCalc = api;
})(typeof window !== 'undefined' ? window : globalThis);
