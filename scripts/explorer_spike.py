"""Throwaway runner test for the Stock Explorer data sources (deleted after the results are recorded).

Run from a GitHub Actions runner to learn whether the keyless Nasdaq endpoints work from runner IPs:
historical prices, dividends (stocks and ETFs), the symbol directory files, and a small sustained load.
Prints one line per request; never fails the job.
"""
import json
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def get(url, accept="application/json", timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.time() - t
    except Exception as e:  # noqa: BLE001
        return "ERR " + type(e).__name__, str(e).encode(), time.time() - t


def hist(sym, cls):
    url = ("https://api.nasdaq.com/api/quote/%s/historical?assetclass=%s&fromdate=2016-11-14"
           "&todate=2026-12-31&limit=9999" % (sym, cls))
    status, body, dt = get(url)
    rows = []
    try:
        rows = ((json.loads(body).get("data") or {}).get("tradesTable") or {}).get("rows") or []
    except Exception:  # noqa: BLE001
        pass
    return status, len(rows), (rows[-1]["date"] if rows else "-"), dt


def divs(sym, cls):
    status, body, dt = get("https://api.nasdaq.com/api/quote/%s/dividends?assetclass=%s" % (sym, cls))
    rows = []
    try:
        rows = (((json.loads(body).get("data") or {}).get("dividends") or {}).get("rows")) or []
    except Exception:  # noqa: BLE001
        pass
    return status, len(rows), dt


def main():
    print("== historical prices (split-adjusted, not dividend-adjusted)")
    for sym, cls in [("SPY", "etf"), ("QQQ", "etf"), ("TLT", "etf"), ("HYG", "etf"), ("AAPL", "stocks"),
                     ("MSFT", "stocks"), ("BRK.B", "stocks"), ("RDDT", "stocks"), ("ZZZZZZ", "stocks")]:
        s, n, oldest, dt = hist(sym, cls)
        print("hist %-6s %-6s status=%s rows=%s oldest=%s %.1fs" % (sym, cls, s, n, oldest, dt))
        time.sleep(0.4)
    print("== dividends")
    for sym, cls in [("AAPL", "stocks"), ("MSFT", "stocks"), ("KO", "stocks"), ("SPY", "etf"), ("QQQ", "etf"), ("TLT", "etf")]:
        s, n, dt = divs(sym, cls)
        print("divs %-6s %-6s status=%s rows=%s %.1fs" % (sym, cls, s, n, dt))
        time.sleep(0.4)
    print("== symbol directory files")
    for name in ("nasdaqlisted", "otherlisted"):
        s, body, dt = get("https://www.nasdaqtrader.com/dynamic/SymDir/%s.txt" % name, accept="text/plain")
        lines = body.decode("utf-8", "replace").splitlines()
        print("symdir %-12s status=%s lines=%s %.1fs first=%r" % (name, s, len(lines), dt, lines[0][:60] if lines else ""))
    s, body, dt = get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&download=true")
    try:
        n = len((json.loads(body).get("data") or {}).get("rows") or [])
    except Exception:  # noqa: BLE001
        n = "?"
    print("screener stocks status=%s rows=%s %.1fs" % (s, n, dt))
    s, body, dt = get("https://api.nasdaq.com/api/autocomplete/slookup/10?search=apple")
    print("autocomplete status=%s bytes=%d %.1fs" % (s, len(body), dt))
    print("== sustained load: 40 sequential historical requests")
    syms = ("AAPL MSFT NVDA AMZN GOOGL META TSLA JPM V UNH XOM JNJ PG HD KO PEP COST WMT DIS NFLX "
            "ADBE CRM INTC CSCO ORCL BAC PFE MRK ABBV LLY AVGO TXN QCOM AMD IBM GE CAT BA MMM NKE").split()
    ok = bad = 0
    t0 = time.time()
    codes = {}
    for sym in syms:
        s, n, oldest, dt = hist(sym, "stocks")
        codes[str(s)] = codes.get(str(s), 0) + 1
        if n > 2000:
            ok += 1
        else:
            bad += 1
            print("   problem: %s status=%s rows=%s" % (sym, s, n))
        time.sleep(0.3)
    print("load: %d ok, %d problems, %.0fs total (%.1fs avg), status codes %s" % (ok, bad, time.time() - t0, (time.time() - t0) / len(syms), codes))


if __name__ == "__main__":
    main()
