"""Independent Python implementation of the multi-security comparison (test reference only); see assets/js/compare-calc.js."""
from __future__ import annotations

import bisect
import math
import statistics

import ref_finance as rf


def compare(series_list, period, benchmark=None):
    everything = list(series_list)
    if benchmark is not None and all(s["symbol"] != benchmark["symbol"] for s in series_list):
        everything.append(benchmark)
    as_of = min(s["dates"][-1] for s in everything)
    anchors = []
    for s in everything:
        i = bisect.bisect_right(s["dates"], rf.start_date(period, as_of, s["dates"][0])) - 1
        anchors.append(s["dates"][0] if i < 0 else s["dates"][i])
    start = max(anchors)
    common = set(d for d in everything[0]["dates"] if start <= d <= as_of)
    for s in everything[1:]:
        common &= set(s["dates"])
    dates = sorted(common)
    basis = "total" if all(s.get("dividends") is not None for s in everything) else "price"
    levels = []
    for s in everything:
        full = rf.level_series(s, basis)
        pos = {d: i for i, d in enumerate(s["dates"])}
        levels.append([full[pos[d]] for d in dates])
    rets = [[l[i] / l[i - 1] - 1.0 for i in range(1, len(l))] for l in levels]
    days = (rf.to_date(dates[-1]) - rf.to_date(dates[0])).days
    idx = list(range(len(dates)))
    bi = next((k for k, s in enumerate(everything) if benchmark is not None and s["symbol"] == benchmark["symbol"]), None)
    out = {"basis": basis, "startDate": dates[0], "endDate": dates[-1], "nReturns": len(dates) - 1, "stats": [], "correlation": None}
    for k, s in enumerate(series_list):
        L, r = levels[k], rets[k]
        cum = L[-1] / L[0] - 1.0
        beta = corr = None
        if bi is not None and len(r) >= 60:
            vb = rf.cov(rets[bi], rets[bi])
            beta = rf.cov(r, rets[bi]) / vb if vb > 0 else None
            sa, sb = statistics.stdev(r), statistics.stdev(rets[bi])
            corr = rf.cov(r, rets[bi]) / (sa * sb) if sa > 0 and sb > 0 else None
        out["stats"].append({"symbol": s["symbol"], "cumulative": cum,
                             "annualized": math.expm1(math.log1p(cum) * 365.25 / days) if days >= 365 else None,
                             "volatility": statistics.stdev(r) * math.sqrt(252) if len(r) >= 20 else None,
                             "maxDrawdown": rf.drawdown(L, idx, dates), "beta": beta, "correlationToBenchmark": corr})
    if len(rets[0]) >= 60:
        n = len(series_list)
        out["correlation"] = [[(rf.cov(rets[a], rets[b]) / (statistics.stdev(rets[a]) * statistics.stdev(rets[b]))) for b in range(n)] for a in range(n)]
    return out
