# CreditScope

Automated daily tracker for 12 stock and bond ETFs (SPY, QQQ, IWM, EFA, EEM, XLF, SHY, IEF, TLT, AGG, LQD, HYG),
built for Financial Data Analytics - Data Tracker Project.

**Status:** pipeline under construction (website and tests come next). Full documentation will be added as each part is finished.

## Data source testing (2026-11-14, from a GitHub Actions runner)

| Source | Result |
|---|---|
| Nasdaq quote API (`api.nasdaq.com/api/quote/{SYMBOL}/info?assetclass=etf`) | 12/12 ETFs returned price and volume. **Used.** |
| Yahoo Finance chart JSON | 0/12: HTTP 429 (Too Many Requests) from the runner. Not usable. |
| Stooq CSV | Not usable: requires a JavaScript proof-of-work challenge. |

Nasdaq is currently the only source. It is requested once per ETF, and each response is one source named
`nasdaq-<SYMBOL>`. Only the 12 tracked symbols are requested.
