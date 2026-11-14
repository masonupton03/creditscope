"""Throwaway source test: call each candidate source for all 12 ETFs and report.

Run from a GitHub Actions runner to find out which sources work from runner IPs.
Prints one line per request and a summary; never fails the job.
"""
import json
import sys
import time
import urllib.request

SYMBOLS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "XLF",
           "SHY", "IEF", "TLT", "AGG", "LQD", "HYG"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SOURCES = {
    "yahoo": "https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=5d&interval=1d",
    "nasdaq": "https://api.nasdaq.com/api/quote/{s}/info?assetclass=etf",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(), time.time() - start
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.time() - start
    except Exception as e:  # noqa: BLE001 - spike script, report everything
        return "ERR %s" % type(e).__name__, str(e).encode(), time.time() - start


def has_values(name, body):
    try:
        d = json.loads(body)
        if name == "yahoo":
            m = d["chart"]["result"][0]["meta"]
            return m.get("regularMarketPrice") is not None and m.get("regularMarketVolume") is not None
        p = d["data"]["primaryData"]
        return bool(p["lastSalePrice"]) and bool(p["volume"])
    except Exception:  # noqa: BLE001
        return False


def main():
    summary = {}
    for name, tmpl in SOURCES.items():
        ok = 0
        for s in SYMBOLS:
            status, body, dt = fetch(tmpl.format(s=s))
            good = status == 200 and has_values(name, body)
            ok += good
            print("%-7s %-4s status=%s bytes=%d %.2fs values=%s"
                  % (name, s, status, len(body), dt, good))
            if not good:
                print("   body: %r" % body[:160])
            time.sleep(0.5)
        summary[name] = "%d/%d usable" % (ok, len(SYMBOLS))
    print("\nSUMMARY", json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
