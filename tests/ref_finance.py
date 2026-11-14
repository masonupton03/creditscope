"""Independent Python implementation of the Stock Explorer financial calculations (test reference only).

It follows the same written specification as assets/js/finance.js but is deliberately written in a
different style (bisect lookups, statistics.stdev, log-based CAGR, separate drawdown pass), so that
agreement between the two is evidence that the browser computes the right numbers.

Specification summary
  price basis : split-adjusted close, excludes dividends
  total basis : dividends reinvested on the ex-date: factor_i = (close_i + div_i) / close_{i-1}
                (only when the dividend history is known; dividends=None means unknown)
  window      : start = last close on or before the period's calendar start date
  volatility  : sample stdev of daily returns * sqrt(252), needs >= 20 returns
  CAGR        : (1+R) ** (365.25/days) - 1 only when days >= 365
  max drawdown: peak-to-trough of the level series, with peak / trough / recovery dates;
                levels within a 1e-12 relative tolerance are ties (earliest peak / trough wins)
  beta, corr  : sample covariance over returns between consecutive common dates, needs >= 60 returns
"""
from __future__ import annotations

import bisect
import calendar
import math
import statistics
from datetime import date

PERIODS = ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "MAX"]
EPS = 1e-12      # relative tolerance: levels closer than this are ties (floating-point noise)


def to_date(s):
    return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))


def shift_months(iso, months):
    d = to_date(iso)
    idx = d.year * 12 + (d.month - 1) - months
    y, m = divmod(idx, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()


def start_date(period, as_of, first):
    if period == "MAX":
        return first
    if period == "YTD":
        return "%04d-12-31" % (int(as_of[:4]) - 1)
    n, unit = int(period[:-1]), period[-1]
    return shift_months(as_of, n * (12 if unit == "Y" else 1))


def credited_dividends(series):
    """{trading-day index: cash} using the first trading day on/after each ex-date."""
    out = {}
    divs = series.get("dividends")
    if divs is None:
        return out
    dates = series["dates"]
    for ex, amount in divs:
        if ex <= dates[0] or ex > dates[-1]:
            continue
        i = bisect.bisect_left(dates, ex)
        out[i] = out.get(i, 0.0) + amount
    return out


def level_series(series, basis):
    close = series["close"]
    if basis == "price":
        return list(close)
    credited = credited_dividends(series)
    factors = [(close[i] + credited.get(i, 0.0)) / close[i - 1] for i in range(1, len(close))]
    levels = [1.0]
    for f in factors:
        levels.append(levels[-1] * f)
    return levels


def window(series, period):
    dates = series["dates"]
    as_of = dates[-1]
    sd = start_date(period, as_of, dates[0])
    i0 = bisect.bisect_right(dates, sd) - 1
    truncated = False
    if i0 < 0:
        i0, truncated = 0, period != "MAX"
    return i0, len(dates) - 1, truncated


def simple_returns(levels, idx):
    return [levels[idx[k]] / levels[idx[k - 1]] - 1.0 for k in range(1, len(idx))]


def drawdown(levels, idx, dates):
    """Ties (within EPS) go to the earliest peak and trough; recovery means regaining the peak level."""
    peak, peak_pos = levels[idx[0]], 0
    worst, worst_k, worst_peak = 0.0, 0, 0
    for k, i in enumerate(idx):
        if levels[i] > peak * (1 + EPS):
            peak, peak_pos = levels[i], k
        depth = levels[i] / peak - 1.0
        if depth < worst - EPS:
            worst, worst_k, worst_peak = depth, k, peak_pos
    if worst == 0.0:
        return {"depth": 0.0, "peakDate": None, "troughDate": None, "recoveryDate": None}
    target = levels[idx[worst_peak]] * (1 - EPS)
    recovery = next((dates[idx[k]] for k in range(worst_k + 1, len(idx)) if levels[idx[k]] >= target), None)
    return {"depth": worst, "peakDate": dates[idx[worst_peak]], "troughDate": dates[idx[worst_k]], "recoveryDate": recovery}


def cov(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - 1)


def summarize(series, period, benchmark=None):
    dates = series["dates"]
    has_div = series.get("dividends") is not None
    i0, i1, truncated = window(series, period)
    out = {"period": period, "startDate": dates[i0], "endDate": dates[i1], "truncated": truncated,
           "basis": "total" if has_div else "price"}
    if i1 <= i0:
        return out
    idx = list(range(i0, i1 + 1))
    price_l = level_series(series, "price")
    total_l = level_series(series, "total") if has_div else None
    levels = total_l if has_div else price_l
    cum = levels[i1] / levels[i0] - 1.0
    days = (to_date(dates[i1]) - to_date(dates[i0])).days
    rets = simple_returns(levels, idx)
    out.update({
        "days": days, "nReturns": len(rets), "cumulativeReturn": cum,
        "priceReturn": price_l[i1] / price_l[i0] - 1.0,
        "totalReturn": (total_l[i1] / total_l[i0] - 1.0) if has_div else None,
        "annualizedReturn": math.expm1(math.log1p(cum) * 365.25 / days) if days >= 365 else None,
        "volatility": statistics.stdev(rets) * math.sqrt(252) if len(rets) >= 20 else None,
        "maxDrawdown": drawdown(levels, idx, dates),
    })
    vol = series.get("volume")
    if vol is not None:
        pairs = [(vol[i], series["close"][i]) for i in idx if vol[i] is not None]
        out["volume"] = ({"avg": sum(v for v, _ in pairs) / len(pairs), "avgDollar": sum(v * c for v, c in pairs) / len(pairs),
                          "latest": vol[i1]} if pairs else None)
    else:
        out["volume"] = None
    if has_div:
        credited = credited_dividends(series)
        ttm_start = shift_months(dates[i1], 12)
        out["dividends"] = {
            "cash": sum(a for i, a in credited.items() if i0 < i <= i1),
            "count": sum(1 for i in credited if i0 < i <= i1),
            "yieldTTM": sum(a for i, a in credited.items() if dates[i] > ttm_start) / series["close"][i1],
        }
    else:
        out["dividends"] = None
    if benchmark is not None:
        out["compare"] = compare(series, benchmark, period)
    return out


def compare(a, b, period):
    as_of = min(a["dates"][-1], b["dates"][-1])

    def anchor(s):
        i = bisect.bisect_right(s["dates"], start_date(period, as_of, s["dates"][0])) - 1
        return (s["dates"][0], period != "MAX") if i < 0 else (s["dates"][i], False)

    (da, ta), (db, tb) = anchor(a), anchor(b)
    s = max(da, db)
    b_index = {d: i for i, d in enumerate(b["dates"])}
    pairs = [(i, b_index[d], d) for i, d in enumerate(a["dates"]) if s <= d <= as_of and d in b_index]
    if len(pairs) < 2:
        return {"basis": "price", "nReturns": 0}
    both_total = a.get("dividends") is not None and b.get("dividends") is not None
    basis = "total" if both_total else "price"
    la_full, lb_full = level_series(a, basis), level_series(b, basis)
    la = [la_full[i] for i, _, _ in pairs]
    lb = [lb_full[j] for _, j, _ in pairs]
    ra = [la[k] / la[k - 1] - 1.0 for k in range(1, len(la))]
    rb = [lb[k] / lb[k - 1] - 1.0 for k in range(1, len(lb))]
    cum_a, cum_b = la[-1] / la[0] - 1.0, lb[-1] / lb[0] - 1.0
    beta = corr = None
    if len(ra) >= 60:
        vb = cov(rb, rb)
        beta = cov(ra, rb) / vb if vb > 0 else None
        sa, sb = statistics.stdev(ra), statistics.stdev(rb)
        corr = cov(ra, rb) / (sa * sb) if sa > 0 and sb > 0 else None
    a100 = [v / la[0] * 100.0 for v in la]
    b100 = [v / lb[0] * 100.0 for v in lb]
    return {"basis": basis, "startDate": pairs[0][2], "endDate": pairs[-1][2], "nReturns": len(ra),
            "cumulativeReturnA": cum_a, "cumulativeReturnB": cum_b, "excessReturn": cum_a - cum_b,
            "beta": beta, "correlation": corr,
            "series": {"dates": [d for _, _, d in pairs], "a": a100, "b": b100,
                       "relative": [x / y * 100.0 for x, y in zip(a100, b100)]}}
