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

---

# Second pass: public-display rights by provider (2026-11-14)

Question: which provider lets a **free public GitHub Pages site** show real prices, and what exactly is permitted:
displaying **quotes**, displaying **charts**, or **redistributing historical datasets**. Quotes below are short and
literal, taken from the primary terms (or pages that state the terms). "Not stated" means the page I read is silent.
This is research, not legal advice.

## Result in one table

| Provider | Free-tier use | Public display / redistribution | Path to permission | Verdict |
|---|---|---|---|---|
| **Alpaca** (free "Basic" data) | Personal, non-commercial | T&C: content may not be "publicly displayed ... (including "mirroring")" without "express prior written consent". Separately: to make content available to others "through your own application (a 'User Application')" give Alpaca "30 days advance written notice". Support FAQ (Nov 2022): "you cannot redistribute Alpaca API data." | **Written consent / 30-day notice**: the only provider whose terms describe a route for third-party apps | Best candidate to ask |
| **Alpha Vantage** | "private and individual in nature" (§2a) | Commercial if you "provide information ... that allows individuals or entities other than User to access information" (§2a-iii); contact premium@alphavantage.co | Commercial agreement. FAQ line "unlimited API requests for verified open-source or educational projects" concerns request limits; it grants no display rights | Not for public display |
| **Finnhub** | "strictly for personal use" | "not redistribute or share access to data or derived results from the data" | Business approval | No (even derived results) |
| **EODHD** | Free = "Sandbox Free Package", personal | "Displaying the data to anyone else, for example on a public website, ... is not permitted." A "chart, screenshot or report containing the data is still a way of displaying or distributing it." Allowed privately: "store, manipulate, and analyze the data for private, non-commercial purposes" | Commercial licence via sales; price not published on the pages read. Student discount 50% for 12 months, no display rights | No for public; fine for private |
| **Twelve Data** | Free tier: "Use Free Tier data for commercial purposes" is a listed restriction | §2.2(e): "Redistribute or provide external display of Data only if and as expressly authorized by a Redistribution Rights Add-On or separate written agreement". External display data access listed first under Venture ($149/mo) | Non-profit/academic programme: "free access to one of our standard plans" for "Registered as a non-profit or academic institution"; "permanent, visible reference to Twelve Data" required; display rights not stated beyond Venture | Possible only for an eligible institution |
| **Massive (Polygon)** | Individual plans: "solely for your own personal, non-business and non-commercial use" | Individuals: "does not permit you to share Information with anyone else, develop or provide a service or application to other users". Businesses terms grant display within the customer's own sites | Business plan: "Stocks Business ... $2,499/month" | No |
| **Financial Modeling Prep** | Personal, non-commercial (per FMP's own articles) | Per FMP guidance (secondary reading): prior written approval is required to publish or publicly display; Enterprise plan is for display and redistribution | Written approval | **Primary terms not read**: FMP's site returned HTTP 403 to automated fetching and I did not circumvent that block. Open the terms in a browser to confirm |
| **Marketstack** | Free: "Non-Commercial Use", 100 requests/month, 1 year history | Not stated on pages read | Paid tiers list "Commercial Use" | No |
| **Tiingo** | Free: "internal consumption only" | Display to others needs a redistribution licence | Sales | No |
| **IEX Exchange** | n/a | Historical PCAP "not currently available for direct download"; no end-of-day bars | n/a | No |
| **Stooq** | n/a | Terms pages returned empty bodies; the CSV endpoints sit behind a JavaScript proof-of-work challenge | n/a | Unverifiable, not usable |
| **Nasdaq (current source)** | n/a | Content "may not be ... displayed ... distributed ... without the prior written consent of Nasdaq" (nasdaqtrader.com copyright page) | Written consent | No for public redistribution |
| **TradingView widgets** | Free embeddable widgets | Widget docs: "a free and powerful chart for you to easily embed in any website"; attribution must remain ("without a proper attribution of TradingView, is not allowed"). Policies §3: licence "strictly limited to personal or internal business purposes", "we do not permit commercial usage"; "explicitly prohibits any form of non-display usage". Docs: "We don't have an API that gives access to data." US data is delayed | Contact form to change branding; commercial question unresolved | Charts can be shown; **no analytics from the data are possible or permitted**; ask TradingView to confirm a non-commercial portfolio site |

Distinctions that came out of the terms:

* **Quotes vs charts:** no provider separates them cleanly. EODHD treats a published chart or a screenshot as display;
  TradingView is the only one that licenses displaying charts, and only inside its own iframe.
* **Redistributing historical datasets** is the most restricted everywhere (Alpaca "mirroring", Finnhub "derived results",
  Massive "data feed, file", EODHD "in its original or repackaged form").
* **Screenshots and screen-sharing of real data count as display** under EODHD's wording and are risky under the others.
  Use simulated data for screenshots, GIFs and any recording.

## Sources with explicit permission to reuse

| Source | What the primary text says | Usable for |
|---|---|---|
| **SEC EDGAR** (sec.gov privacy page, "Website Dissemination") | "Information presented on sec.gov is considered public information and may be copied or further distributed by users of the web site without the SEC's permission." and "Please consider appropriate citation to the SEC as the source." Programmatic access: declare a User-Agent with contact details; "10 requests/second"; no crawling with "botnets or automated tools". The statement names sec.gov, not data.sec.gov. | A real, redistributable company directory and company fundamentals (XBRL "company facts"). **No price history.** |
| **US Treasury** | Interest-rate pages carry no reuse statement ("not stated"). US government works are generally public domain (background knowledge, not stated on the page). | Risk-free rate and yield curve |
| **FRED** | "Public Domain: Citation requested" series "may be used without permission" (DGS2, DGS10, DGS30 seen under that label; DGS3MO and TB3MS not confirmed). Copyrighted series (for example S&P 500: "reproduction ... prohibited without ... prior written permission") are restricted. Terms also forbid "Store, cache, or archive any portion of the FRED Services or Content". | Rates only, and not as a cached copy |
| **Kenneth French library** | Terms not stated on the page read | Not relied on |

## What could not be verified

FMP primary terms (blocked), Stooq terms (empty pages), TradingView symbol search inside the Advanced Chart widget (option
list is client-rendered, not in the text read), EODHD commercial pricing, Alpaca's current terms (the linked PDF carries a
2021 creation date), Alpha Vantage free-tier history depth and adjusted-price availability, and Twelve Data free-tier
dividends and `adjust` access.
