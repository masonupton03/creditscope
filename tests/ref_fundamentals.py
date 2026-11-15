"""Independent Python implementation of the fundamentals ratios (test reference only); see assets/js/fundamentals-calc.js."""
from __future__ import annotations


def analyze(company):
    pts = {k: {p["fy"]: p["val"] for p in m["points"]} for k, m in company["metrics"].items()}
    years = sorted({y for d in pts.values() for y in d})

    def g(k, y):
        return pts.get(k, {}).get(y)

    def div(a, b):
        return a / b if a is not None and b is not None and b > 0 else None

    def avg(k, y):
        a, b = g(k, y), g(k, y - 1)
        return (a + b) / 2 if a is not None and b is not None else None

    ratios = {}
    for y in years:
        rev, prev = g("revenue", y), g("revenue", y - 1)
        gp = g("grossProfit", y)
        derived = False
        if gp is None and rev is not None and g("costOfRevenue", y) is not None:
            gp, derived = rev - g("costOfRevenue", y), True
        ocf, capex = g("operatingCashFlow", y), g("capex", y)
        fcf = None if ocf is None or capex is None else ocf - capex
        ni, eq, debt, cash = g("netIncome", y), g("equity", y), g("debt", y), g("cash", y)
        ae, aa = avg("equity", y), avg("assets", y)
        ratios[y] = {
            "revenueGrowth": rev / prev - 1 if rev is not None and prev is not None and prev > 0 else None,
            "grossMargin": div(gp, rev), "operatingMargin": div(g("operatingIncome", y), rev), "netMargin": div(ni, rev),
            "roe": ni / ae if ni is not None and ae is not None and ae > 0 and g("equity", y) > 0 and g("equity", y - 1) > 0 else None,
            "roa": ni / aa if ni is not None and aa is not None and aa > 0 else None,
            "debtToEquity": debt / eq if debt is not None and eq is not None and eq > 0 else None,
            "netDebt": None if debt is None or cash is None else debt - cash,
            "fcf": fcf, "fcfMargin": div(fcf, rev), "liabilitiesToAssets": div(g("liabilities", y), g("assets", y)),
            "grossProfit": gp, "grossProfitDerived": derived,
        }
    rev_years = [y for y in years if g("revenue", y) is not None]
    latest = rev_years[-1] if rev_years else None
    cagr = {}
    for n in (3, 5):
        a = g("revenue", latest - n) if latest is not None else None
        b = g("revenue", latest) if latest is not None else None
        cagr[n] = (b / a) ** (1.0 / n) - 1 if a is not None and b is not None and a > 0 and b > 0 else None
    return {"years": years, "ratios": ratios, "cagr": cagr, "latestFiscalYear": latest}
