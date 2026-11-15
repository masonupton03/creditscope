# SEC EDGAR fundamentals: plan and status

**Status (2026-11-14, branch `feature/stock-explorer`, not merged, not deployed):** the whole pipeline and page are built and tested
against simulated data. **No request has been sent to the SEC**, because the SEC asks every client to declare a contact address and
none has been configured. What exists:

| Piece | Where |
|---|---|
| Tag map, reducer (company facts to a compact annual file with filing references) | `fundamentals/concepts.py`, `fundamentals/reduce.py` |
| Polite client (needs `SEC_USER_AGENT`, rejects placeholders, throttled to 5 requests/second, never prints the contact) | `fundamentals/sec.py` |
| Build command | `python -m fundamentals build` (refuses to run without a configured contact) |
| Simulated demo set (four fictional companies, labelled, no filing links) | `fundamentals/sample.py` -> `explorer/sec-sample/` |
| Ratios, verified against an independent Python reference | `assets/js/fundamentals-calc.js`, `tests/ref_fundamentals.py` |
| Page | `fundamentals.html`, `assets/js/fundamentals.js` (uses `explorer/sec/` when it has data, else the labelled sample) |
| Example manual workflow (inactive) | `docs/fundamentals-workflow.example.yml` |

**Contact address:** read from the environment variable `SEC_USER_AGENT` (a GitHub Actions secret in CI). It is never stored in the
repository; a test fails if an email-like string appears in the fundamentals code or data, or if the owner's personal address
appears anywhere. To switch real data on: create a project mailbox, add the secret, run the build, inspect the output, and approve
publishing it.

Original research notes follow.

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

---

## Public dataset design (decided 2026-11-15)

The public repository will hold a **compact, reproducible dataset** and nothing else from the SEC:

| Stored | Not stored |
|---|---|
| Per company one file `explorer/sec/company/<TICKER>.json` (< 60 KB, enforced by a test): fiscal-year values for each metric, the tag that supplied each value, period start/end, form, filing date, accession number (for the filing link), fiscal-year label, coverage report, automatic data checks | Raw company-facts JSON, filings, exhibits, PDFs, or any price data |
| `explorer/sec/index.json`: company list for search, with latest period end and filing date | Anything from a market-data provider |
| In each file: `reducerVersion` and `sourceDigest` (SHA-256 of the SEC response it was reduced from), `generated` time | Contact address (it lives only in the `SEC_USER_AGENT` secret) |

**Reproducible** means: the code in `fundamentals/` plus the SEC's response for that company yields the same file, and the recorded
`sourceDigest` shows whether a later rebuild used different input. Reducer rules are covered by `tests/test_fundamentals.py`.
Estimated size for 30 companies: well under 2 MB; 500 companies about 10 MB, so keep the universe modest.

## Companies planned first: Microsoft, Apple, Walmart, JPMorgan Chase

Their fiscal calendars differ, which the reducer handles by labelling a year with the year its period ends (Microsoft June,
Apple late September, Walmart 31 January, JPMorgan December; tested on invented numbers with those calendars). Expected
non-standard shapes, **not yet confirmed against real data (no SEC request has been made)**:

- **JPMorgan (bank):** no cost of revenue, gross profit or operating income; revenue is the total net revenue tag
  (`RevenuesNetOfInterestExpense` is accepted as a last fallback; gross interest income is never used as revenue); cash may be
  "cash and due from banks". Missing items are left blank and listed under "Not reported under the standard tags".
- **Apple:** revenue tagged `RevenueFromContractWithCustomerExcludingAssessedTax`; debt = non-current plus current portion of
  long-term debt; **commercial paper is not included** (the Fundamentals page says what "Debt" means).
- **Walmart:** consolidated equity versus equity attributable to shareholders can differ (noncontrolling interest); the automatic
  balance-identity check flags a gap above 2 %.
- **Microsoft:** a June year end and tag changes over time are handled by the tag priority list; the stored tag shows which applied.

## Verification procedure once the contact email exists (needs your approval before any request)

1. **Build four companies:** `SEC_USER_AGENT="CreditScope educational project <mailbox>" python -m fundamentals build --tickers MSFT,AAPL,WMT,JPM --out /tmp/sec-check`
   (from the workflow artifact or locally). About 6 requests.
2. **Automatic re-confirmation:** `python -m fundamentals verify MSFT --out /tmp/sec-check --sheet msft.md`. Each stored value is
   re-fetched through a *different* SEC endpoint (`companyconcept`) and compared (value, period and accession). Any mismatch fails.
3. **Manual comparison with the original filing (the real check):** open `msft.md`; each row links to the filing index. In the
   10-K's financial statements find the figure, remember that statements print millions or thousands, and tick the box. Do at
   least revenue, net income, total assets, total liabilities and operating cash flow for the latest **three** fiscal years of each company.
4. Read the page "Data checks and coverage" for each company; every flag needs an explanation (restatement, minority interest,
   acquisition) or a code fix. A discrepancy is never fixed by editing a number.
5. Record the result (date, who checked, what matched) in this file before any real data is committed or deployed.
