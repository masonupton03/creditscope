# Stock Explorer: data-source findings

Research notes for the Stock Explorer (development branch). Written 2026-11-14; provider terms and free tiers change, so
re-check before relying on any of this. Nothing here is legal advice.

## Requirement

A public GitHub Pages site where a visitor can search stocks and ETFs, see historical prices, compare against SPY and see
return, volatility, drawdown and volume, **without the visitor supplying an API key** and **without exposing a key in the
repository or the page**.

## What was tested

### Keyless endpoints, from a GitHub Actions runner (2026-11-14)

| Endpoint | Result |
|---|---|
| Nasdaq `api.nasdaq.com/api/quote/{SYM}/historical` | 10 years of daily open/high/low/close/volume (2,514 rows for SPY, QQQ, TLT, HYG, AAPL, MSFT, BRK.B). Recent IPO returns its shorter history (RDDT 666 rows). Unknown ticker returns an empty table. |
| Same, load | 40 sequential requests, 40 succeeded, no throttling, 2.6 s average. |
| Nasdaq `.../dividends` | See "Dividend coverage" below. |
| Nasdaq Trader `nasdaqlisted.txt`, `otherlisted.txt` | 5,606 and 7,684 lines, with an ETF flag. |
| Nasdaq screener | 7,252 stock rows with market cap and sector. |
| Yahoo chart JSON | HTTP 429 from the runner (earlier test) and from a home IP. No CORS headers. |
| Stooq | Requires a JavaScript proof-of-work challenge. |

### Price adjustment (verified)

Nasdaq history is **split-adjusted but not dividend-adjusted**: AAPL's close on 2020-08-28 is returned as $124.81 (the
unadjusted print was $499.23), while SPY's closes are the raw prices. So the series gives **price return** only.

### Dividend coverage (verified, and an earlier claim corrected)

Dividend history exists only for **Nasdaq-listed** securities: AAPL (84), MSFT (55), NVDA (53), PEP (92), QQQ (58),
SHY (219), IEF (219), TLT (204). It is empty for NYSE and NYSE Arca listings, including **SPY**, IWM, EFA, EEM, XLF, AGG, LQD,
HYG, VTI, VOO, GLD and the dividend payers KO, JNJ, PG, XOM, JPM, T and VZ. An earlier note in the conversation said
"no ETF dividends under any asset class"; that was too broad. Coverage is partial and follows the listing exchange.
Consequence: with Nasdaq alone, the benchmark (SPY) has no dividend data, so total-return comparisons against SPY are not
possible and the Explorer falls back to price return for both sides.

### Browser access (CORS, verified with an `Origin` header)

| No CORS headers (cannot be called from a Pages site) | CORS enabled (callable from the browser, key would be in the page) |
|---|---|
| Yahoo, all Nasdaq endpoints, SEC, Nasdaq Trader files | Twelve Data, Alpha Vantage, Financial Modeling Prep, Finnhub, Massive (Polygon) |

Tiingo returned 403 with no headers for an invalid token, so its CORS behaviour is unverified.

## Licensing

| Source | What the terms say | Consequence |
|---|---|---|
| **Nasdaq** (nasdaqtrader.com copyright and disclaimer page, read in full) | Content "may not be copied, reproduced, transmitted, displayed, performed, distributed ... without the prior written consent of Nasdaq"; exceptions are fair use and one personal, non-commercial copy; "Nasdaq stock symbols are proprietary to Nasdaq, Inc." Nasdaq's data policies say an appropriate licence is required to use, distribute and access Nasdaq information. The nasdaq.com Terms of Use page could not be fetched (timeout), so it was not read; a separate Nasdaq terms document found by search prohibits automated capture of its service without written permission. | No permission to publicly display or redistribute bulk Nasdaq history was found. **A preloaded public dataset of Nasdaq data is not supported by any permission located, and was not built.** |
| **Twelve Data free (Basic)** (pricing page and help-centre articles) | "internal non-display usage only"; individual plans do not permit "redistribution of data" or "commercial display of data to third parties". External display starts at the Venture business plan ($149/month) and requires the attribution "Data provided by Twelve Data". Free-plan limits: 8 credits/minute, 800/day. Not stated on the pages read: history depth, dividends endpoint and `adjust` parameter availability on the free plan, and whether a visitor using their own free key in someone else's browser app is allowed. | Cannot power a public site on the owner's key. A bring-your-own-key mode is a grey area the terms do not address. |
| **Tiingo free** | Data is for "internal consumption only"; displaying it to others needs a redistribution licence. | Rejected for a public site. |
| Others (Alpha Vantage 25 requests/day, FMP 250/day and non-commercial, Massive 5 requests/minute and 2 years of history) | Not read in full; free tiers are small and generally personal use. | Not suitable as a public backend. |

No free provider with a verified right to display historical prices on a public website was found.

## Conclusion and what was built instead

* The financial calculation module, search and watchlist were built provider-independently
  (`assets/js/finance.js`, `search.js`) and verified against an independent Python implementation.
* The Explorer ships with **simulated sample data** (`explorer/sample/`, generated by
  `scripts/make_explorer_sample.py`), clearly labelled on the page, so every feature can be used and demonstrated without
  any data licence.
* Connecting real data requires a decision on licensing (see the open decisions in the project discussion).
