# Plan: a public SEC EDGAR fundamentals section (not built yet)

Goal: a **real, legally reusable** public section of the site: search real US companies and view their reported fundamentals
(revenue, profit, margins, balance sheet, cash flow) with analytics. No price data, no API key, no visitor account.

## What the primary documents say (read 2026-11-14)

| Topic | Statement | Source |
|---|---|---|
| Reuse | "Information presented on sec.gov is considered public information and may be copied or further distributed by users of the web site without the SEC's permission." and "Please consider appropriate citation to the SEC as the source." | sec.gov/about/privacy-information, "Website Dissemination" |
| Caveat | That statement names **sec.gov**; it does not name **data.sec.gov** where the JSON APIs live. The nightly bulk file is on `www.sec.gov/Archives/...`, which the statement does cover. | same + edgar-application-programming-interfaces |
| Authentication | "These APIs do not require any authentication or API keys to access." | edgar-application-programming-interfaces |
| Identification | "Please declare your user agent in request headers"; the sample shows a company name plus an admin contact email. | accessing-edgar-data, "Fair access" |
| Rate | "Current max request rate: 10 requests/second." No botnets or crawling. | accessing-edgar-data |
| Browser access | "data.sec.gov does not support Cross Origin Resource Scripting (CORS)." The browser cannot call it, so a server-side job must fetch the data. | edgar-application-programming-interfaces |
| Endpoints | `data.sec.gov/submissions/CIK##########.json`; `.../api/xbrl/companyfacts/CIK##########.json` (all concepts for a company); `.../companyconcept/...`; `.../frames/...`; ticker files `www.sec.gov/files/company_tickers.json`, `company_tickers_exchange.json`, `company_tickers_mf.json`. The SEC does "not guarantee accuracy or scope" of the ticker files. | same |
| Bulk | `companyfacts.zip` (all XBRL data) is "recompiled nightly" (about 3 a.m. ET) at `www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip`. | same |
| Periods | Frames use CY#### (annual, 365 ± 30 days) and CY####Q# (quarterly, 91 ± 30 days); fiscal calendars "can start and end on any month or day". | same |

Not stated in the pages read: whether `company_tickers_mf.json` includes ETFs, caching rules, and which concept names exist
(AccountsPayableCurrent is the only example named). These must be checked against real files when the work starts.

## The dedicated contact email

The SEC asks for contact details in the User-Agent. Use a **dedicated project mailbox**, never a personal address, and keep
it out of the repository:

* store the whole header as a GitHub Actions **secret** `SEC_USER_AGENT` (for example `CreditScope educational project
  contact@[project-domain]`); the build job reads it from the environment and the value never appears in the repo, the logs
  or the published files;
* locally, read it from `SEC_USER_AGENT` in the environment;
* **Decision needed:** create or choose that mailbox before any request is made. No SEC request has been sent yet.

## Architecture

```
GitHub Actions (nightly, new workflow; the assignment pipeline is untouched)
  1. fetch company_tickers_exchange.json (+ _mf.json if it contains ETFs)       -> searchable directory
  2. fetch companyfacts for a chosen universe (about 500 companies, <= 10 requests/second, throttled to ~5)
  3. reduce each company to a small, clean annual+quarterly table                -> explorer/sec/company/<TICKER>.json
  4. write explorer/sec/index.json (ticker, name, CIK, exchange, latest fiscal year)
  5. deploy as part of the Pages artifact (not committed to git history)
Browser: search the directory, load one small JSON file per company, compute analytics, chart. No API calls to the SEC.
```

Why server-side: no CORS, a declared User-Agent is required, and a static site cannot hold a contact header safely.

## Data model (per company)

* Annual and quarterly series for: Revenues, CostOfRevenue, GrossProfit, OperatingIncomeLoss, NetIncomeLoss, EPS (diluted),
  Assets, Liabilities, StockholdersEquity, Cash, LongTermDebt, NetCashProvidedByOperatingActivities,
  PaymentsToAcquirePropertyPlantAndEquipment, shares outstanding.
* Concept fallbacks (for example Revenues, RevenueFromContractWithCustomerExcludingAssessedTax, SalesRevenueNet) recorded in a
  mapping table, with the chosen tag stored in the output so every number is traceable.
* Facts are de-duplicated to the **latest filed** value per period; 10-K vs 10-Q durations are not mixed (year-to-date vs
  quarter handled explicitly); restatements keep the latest. Units are USD (or USD-per-share).

## Analytics (computed in the browser, verified against an independent Python reference)

Revenue and profit growth (YoY, CAGR), gross/operating/net margin, return on equity and assets, debt-to-equity and net
debt, free cash flow and FCF margin, share-count change. Charts of each over time, and a peer comparison within the chosen
universe. Every figure shows its source concept and filing period.

## Tests

* Fixtures: trimmed real `companyfacts` JSON for two or three companies (public SEC data), committed with the SEC citation.
* Python reference for the reduction and the ratios; JS compared against it; tests for duplicate facts, restatements, missing
  concepts, 52/53-week and non-calendar fiscal years, and negative or zero denominators.
* A test that the build refuses to run without `SEC_USER_AGENT` and never logs it.

## Open questions

1. The project contact email (see above).
2. Whether to rely on the per-company `data.sec.gov` API (simple, but the SEC reuse statement names sec.gov) or the nightly
   `companyfacts.zip` on `www.sec.gov` (clearly covered, but a very large download; size not stated in the pages read).
3. Whether `company_tickers_mf.json` lists ETFs, to decide whether ETFs appear in this section.
