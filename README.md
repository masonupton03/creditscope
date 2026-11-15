# CreditScope

[![Tests](https://github.com/masonupton03/creditscope/actions/workflows/tests.yml/badge.svg)](https://github.com/masonupton03/creditscope/actions/workflows/tests.yml)
[![Daily update](https://github.com/masonupton03/creditscope/actions/workflows/daily.yml/badge.svg)](https://github.com/masonupton03/creditscope/actions/workflows/daily.yml)

**Live site: <https://masonupton03.github.io/creditscope/>**

CreditScope is an automated daily tracker for **12 stock and bond ETFs**. Every day a GitHub Actions workflow downloads
each ETF's latest quote, saves the raw responses, rebuilds a one-row-per-ETF-per-day history, opens a GitHub Issue
listing the biggest moves, and publishes an installable website with three pages (Today, Browse, Trends).

Built for *Financial Data Analytics, Data Tracker Project*, with Claude Code.

| ETF | Class | Category | ETF | Class | Category |
|---|---|---|---|---|---|
| SPY | Stock | US large cap | SHY | Bond | Short Treasury |
| QQQ | Stock | US growth | IEF | Bond | Intermediate Treasury |
| IWM | Stock | US small cap | TLT | Bond | Long Treasury |
| EFA | Stock | Developed international | AGG | Bond | Broad market |
| EEM | Stock | Emerging markets | LQD | Bond | Investment-grade corporate |
| XLF | Stock | Financials | HYG | Bond | High-yield corporate |

The key that identifies an item from day to day is the **ticker** (`item_id`, e.g. `SPY`).

## How it works

1. **Daily schedule.** `daily.yml` runs every day at 21:45 UTC (weekends and holidays included, shortly after the US
   close) and can be started by hand (`workflow_dispatch`). Each run takes the **UTC date of the moment it runs**.
2. **Download.** One request per ETF to the Nasdaq quote API. Each response is saved exactly as received, gzip-compressed,
   in `data/raw/<YYYY-MM-DD>/<source>.json.gz` (for example `data/raw/2026-11-14/nasdaq-SPY.json.gz`). A source that
   fails (after 3 attempts) or returns something unusable writes **no raw file**, and the run carries on with the others.
   The result of every source, success or failure, is recorded in `data/runs/<date>.json`.
3. **Build.** `data/history.csv` is rebuilt **from the raw files alone**, so rerunning the build gives the same file and
   a change to a rule applies to every day. A day with no raw file for a source has no row from that source. Rows are
   sorted by date, then `item_id`.
4. **Status.** `data/status.json` describes the latest run.
5. **Issue.** A GitHub Issue titled `CreditScope daily update: <date>` is opened every day (even with no changes) listing
   the biggest moves and any item that appeared or disappeared, and the previous day's issue is closed.
6. **Commit and publish.** The raw files, history, run log and status are committed by the workflow, then the site is
   deployed to GitHub Pages.

GitHub starts scheduled workflows on a best-effort basis and may delay them by several minutes; the 21:45 UTC slot leaves
over two hours before UTC midnight so a run still lands on the intended date. If a scheduled run is ever missed, start
it by hand from the Actions tab (`Daily update` → *Run workflow*).

A run counts as successful when it finishes and commits, even if some sources failed. **A second run on the same day**
replaces that day's raw files (only for sources that succeed again), rebuilds the history, and updates that day's issue
instead of opening another, so each day counts once.

### Weekends, holidays and market dates

Markets are closed on weekends and holidays, so the source repeats the last trading session's quote. The history keeps
both dates: `date` is the UTC **collection** date, `price_date` is the **market** date the quote belongs to. The site
and the issues label repeated quotes as "carried over" and never present them as new market activity. The Trends page
counts each (ETF, market date) pair once.

### The move rule

For every ETF present in both the latest run and the previous run (the previous date that has rows in `history.csv`):

`move = (price_now − price_before) ÷ price_before × 100`

ETFs are ranked by the **absolute value** of the move (ties broken by ticker); the **top 5** with a non-zero move are
listed in the issue with their old and new price and volume. ETFs that appear in only one of the two runs are listed as
*appeared* or *disappeared*. An ETF whose download failed is reported as a failed source, not as disappeared. If the
source still reports the same trading session, the issue says so.

## Data source

| Source | Format | URL pattern | Notes |
|---|---|---|---|
| `nasdaq-<SYMBOL>` (12 sources) | JSON | `https://api.nasdaq.com/api/quote/<SYMBOL>/info?assetclass=etf` | No login or API key. Only the 12 tracked symbols are requested; from each response the pipeline keeps the quote fields listed below (the full response is saved raw). |

Source testing on 2026-11-14 from a GitHub Actions runner: Nasdaq returned all 12 ETFs; **Yahoo Finance** chart JSON
returned HTTP 429 (blocked) from the runner; **Stooq** CSV requires a JavaScript proof-of-work challenge. Nasdaq is
therefore the only source. If it stops working it will be replaced by another (see `creditscope/sources.py` and
`creditscope/convert.py`, where adding a source means one new converter).

## Columns of `data/history.csv`

One row per ETF per run date. Empty means the source did not report the value that day.

| Column | Meaning | Unit / format |
|---|---|---|
| `date` | UTC date of the run that collected the row | `YYYY-MM-DD` |
| `item_id` | ETF ticker (the key) | text, e.g. `SPY` |
| `item` | ETF name as reported by the source | text |
| `source` | Source that produced the row (= raw file name) | text, e.g. `nasdaq-SPY` |
| `asset_class` | `Stock` or `Bond` | text |
| `category` | Sub-category (e.g. Long Treasury) | text |
| `price` | Last sale price (the close once the market has closed) | US dollars |
| `volume` | Shares traded in the session | shares |
| `net_change` | Change versus the previous close, as reported by the source | US dollars |
| `pct_change` | Percent change versus the previous close, as reported by the source | percent (`-0.38` means −0.38 %) |
| `price_date` | Market date of the quote; earlier than `date` on weekends and holidays | `YYYY-MM-DD` |
| `market_status` | Market status reported with the quote (`Closed`, `Open`, …) | text |

`price`, `volume`, `net_change` and `pct_change` are the numeric values tracked for every ETF.

## `data/status.json`

`run_time` (UTC, of the latest run), `first_run_date` (date of the earliest raw file), `days_with_success` (number of
different dates with a raw file), `items` (items in the latest run), `new_today` and `gone_today` (**lists of
`item_id`s** that appeared or disappeared; the Today page shows their counts), and `sources`, a list with one entry per
source holding `name`, `ok` and `count`.

## Rebuild the history from the raw files

```bash
python -m creditscope build
```

This reads only `data/raw/` and rewrites `data/history.csv`; no network access is needed. The daily command is
`python -m creditscope run` (download, build, status) followed by `python -m creditscope issue` (needs the `gh` CLI and
`GH_TOKEN`). The pipeline uses only the Python standard library.

## The website

Served from the repository root by GitHub Pages; all three pages load `data/history.csv` and `data/status.json` in the
browser and do their calculations there.

* **Today** (`index.html`): last run time, status of every source, the counts from `status.json`, the latest value of
  every ETF with its change since the previous run and a trend line, and the biggest moves.
* **Browse** (`browse.html`): latest values with search, filters (asset class, category, direction, shortlist only),
  sorting up and down on every numeric column, and a ★ on every ETF that saves it to a shortlist kept in the browser
  (`localStorage`, still there after reload).
* **Trends** (`trends.html`): a chart of each numeric value over time with an ETF picker, plus four findings whose
  headlines, numbers and explanations are generated in the browser from `history.csv` (return since the first session,
  biggest single-day move, stocks versus bonds, trading volume). It handles short histories gracefully.
* **Installable and offline.** `manifest.webmanifest` and `sw.js` make it installable as an app. Online, pages load the
  data from the network; offline, the site still opens and shows the last data it loaded (with a banner).

All pages share one navigation bar (Markets · Research · Portfolio, with the section's pages as tabs underneath: **Today, Browse and
Trends are the Markets tabs**; About is a small link at the right), one stylesheet (fonts and colours) and a dark theme with a
light-mode toggle. The navigation markup is generated by `scripts/sync_nav.py` so every page is identical.
Chart.js (MIT) is vendored in `assets/vendor/` so charts work offline.

## Run it locally

```bash
python -m creditscope run          # download today's quotes, save raw files, rebuild history, write status
python -m http.server 8000         # then open http://localhost:8000/ (the service worker needs http://localhost or https)
```

## Tests

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

`tests.yml` runs the suite on every push and pull request (Python 3.12). The browser-statistics check needs Node and is skipped if Node is missing. It covers conversion of the source to the common columns (including missing
values and unusable responses), failed downloads, the move rule, the history logic (determinism, ordering, rebuilding
from raw files, a changed rule applying to every day), same-day reruns, the issue logic, the site structure, and a
check that the statistics the Trends page computes in the browser (`assets/js/stats.js`) equal an independent Python
implementation (`tests/ref_stats.py`) on the same history file.

## Files

| Path | What it does |
|---|---|
| `creditscope/__init__.py` | Marks the folder as the `creditscope` Python package. |
| `creditscope/config.py` | The 12 ETFs, history columns and paths. |
| `creditscope/sources.py` | List of sources and the HTTP download with retries. |
| `creditscope/convert.py` | Converts one raw response to the common columns. |
| `creditscope/raw.py` | Writes and reads the compressed raw files. |
| `creditscope/build.py` | Builds `data/history.csv` from the raw files. |
| `creditscope/moves.py` | The move rule and the comparison of the latest run with the previous run. |
| `creditscope/status.py` | Writes `data/status.json` and the per-day run log. |
| `creditscope/run.py` | One daily run: download, save raw, build, status. |
| `creditscope/issues.py` | Creates, updates and closes the daily GitHub Issues through `gh`. |
| `creditscope/__main__.py` | Command line: `run`, `build`, `issue`. |
| `data/raw/<date>/*.json.gz` | Compressed raw responses (one per source per day). |
| `data/runs/<date>.json` | Result of every source in that day's latest run, including errors. |
| `data/history.csv`, `data/status.json` | The two data files described above. |
| `index.html`, `browse.html`, `trends.html` | The Today, Browse and Trends pages. |
| `assets/css/site.css` | Shared design system (dark and light themes). |
| `assets/js/common.js` | Theme, data loading, number formatting, shortlist storage, install prompt. |
| `assets/js/stats.js` | CSV parser and every calculation (runs in the browser and in Node tests). |
| `assets/js/today.js`, `browse.js`, `trends.js` | Page scripts. |
| `assets/vendor/chart.umd.min.js` | Chart.js 4.4.7. |
| `assets/icons/*`, `scripts/make_icons.py` | App icons and the script that draws them. |
| `manifest.webmanifest`, `sw.js` | Web app manifest and service worker (offline support). |
| `.github/workflows/daily.yml` | Daily pipeline: run, commit, issue, then deploy. |
| `.github/workflows/pages.yml` | Publishes the site to GitHub Pages (on push and after each daily run). |
| `.github/workflows/tests.yml` | Runs pytest on every push. |
| `tests/conftest.py` | Shared test helpers: synthetic Nasdaq responses and a fake downloader. |
| `tests/test_convert.py` | Conversion of the source response to the common columns, missing values, unusable responses. |
| `tests/test_moves.py` | The move rule, ranking, appeared/disappeared items, weekend carry-overs. |
| `tests/test_build.py` | History logic: ordering, reproducibility from raw files, rule changes, corrupt files. |
| `tests/test_run.py` | Full runs with a fake downloader: failed sources, same-day reruns, `status.json`, run log. |
| `tests/test_issues.py` | Issue text and the create / update / close logic (the `gh` CLI is mocked). |
| `tests/test_site.py` | Website checks (shared nav, assets, manifest, service worker) and the browser-vs-Python statistics comparison. |
| `tests/js/stats.test.js` | Node test of `assets/js/stats.js` against numbers computed independently in Python. |
| `tests/ref_stats.py` | Independent Python implementation of the Trends statistics (test reference only). |
| `tests/sample_data.py`, `tests/make_fixtures.py` | Deterministic sample history (weekends, a failed source, an all-failed day) and the fixture generator. |
| `tests/fixtures/` | A real saved Nasdaq response and the generated sample `history.csv`, `status.json`, `expected.json`. |
| `pytest.ini`, `requirements-dev.txt` | Test configuration and dependencies (pytest). |
| `.gitignore`, `README.md` | Ignored local files; this document. |

## Research platform (optional additions)

Beyond the assignment, the repository also holds a stock-research platform built on the same site: a security **Explorer**, SEC
**Fundamentals**, a **Compare** tool, a **Portfolio** analytics page and an **About** page. None of it is needed by the daily
pipeline or the three required pages, and the pipeline files above are unchanged. Prices on these pages are **simulated and
labelled as such**; the only real data is SEC filings (fundamentals), and a private "personal edition" that runs only on the
owner's computer and never publishes market data or holdings. See `docs/portfolio-dashboard.md`, `docs/personal-edition.md`,
`docs/sec-edgar-plan.md` and `docs/explorer-data-sources.md`.

| Path | What it does |
|---|---|
| `explorer.html`, `fundamentals.html`, `compare.html`, `portfolio.html`, `platform.html` | Explorer, Fundamentals, Compare, Portfolio and About pages. |
| `assets/css/explorer.css`, `assets/css/portfolio.css` | Styles for the research pages (sub-navigation, charts, tables). |
| `assets/js/finance.js` | Return, volatility, drawdown, beta and total-return calculations (browser and Node). |
| `assets/js/search.js`, `assets/js/picker.js`, `assets/js/xlinks.js` | Security search, the shared search box, and consistent links between pages. |
| `assets/js/explorer.js` | Explorer page. |
| `assets/js/compare-calc.js`, `assets/js/compare.js` | Comparison calculations and the Compare page. |
| `assets/js/fundamentals-calc.js`, `assets/js/fundamentals.js` | Financial-statement ratios and the Fundamentals page. |
| `assets/js/portfolio.js`, `assets/js/portfolio-page.js`, `assets/js/redact.js` | Portfolio analytics (time-weighted return, risk, concentration), the Portfolio page, and the hide-everything view. |
| `explorer/sample/index.json`, `explorer/sample/series/*.json`, `explorer/sample/portfolio.json` | Simulated securities, price histories and demo portfolio (generated, not real data). |
| `explorer/sec/index.json`, `explorer/sec/company/*.json` | Real SEC fundamentals for the companies approved for release (Apple and Microsoft), built from SEC filings with their verification statements and limitations. Not covered by the MIT licence (see `NOTICE`). |
| `explorer/sec-sample/index.json`, `explorer/sec-sample/company/*.json` | Four fictional demonstration companies (simulated), shown only when no real SEC data is present. |
| `fundamentals/*.py`, `fundamentals/universe.txt`, `fundamentals/curated.json` | SEC EDGAR pipeline: tag map, reducer, polite client, build, verify, review and explain commands, simulated sample, and the hand-written verification statements and release list (`curated.json`). Needs the `SEC_USER_AGENT` secret for live use. |
| `personal/*.py` | Private personal edition: credential storage outside the repository, market-data client, local server, portfolio storage. |
| `scripts/make_explorer_sample.py`, `scripts/make_portfolio_sample.py` | Generate the simulated sample data. |
| `scripts/sync_nav.py` | Single source of the navigation markup used by every page (`--check` verifies they match). |
| `scripts/browser-audit/*` | Optional real-browser audits in Chrome, Firefox and WebKit (accessibility, responsiveness, theme, privacy, offline, screenshots); see its README and `docs/browser-compatibility.md` for results and limits (no real iPhone was tested). |
| `docs/visual-review/*.jpg` | Full-page screenshots of the five main pages (desktop and phone, light and dark; simulated data) used by `docs/visual-review.md`. |
| `LICENSE` · `NOTICE` · `THIRD_PARTY_NOTICES.md` | MIT licence for CreditScope's original code; the notice excluding third-party datasets (Nasdaq quotes, SEC filing data) and trademarks; the required Chart.js and @kurkle/color notices. |
| `docs/*.md`, `docs/permission-requests/*.md`, `docs/fundamentals-workflow.example.yml` | Design notes, data-licensing research, unsent permission-request drafts, the rubric audit, launch checklist, and an inactive workflow example. `docs/browser-compatibility.md` records the browser results; `docs/sec-activation.md` lists the steps to switch on real SEC data; `docs/sec-first-review.md` records the first real build's review; `docs/sec-filing-verification.md` compares the four companies with their 10-K filings; `docs/licensing-review.md` reviews dependencies and data rights before any licence is added. |
| `tests/test_explorer.py`, `tests/test_compare.py`, `tests/test_fundamentals.py`, `tests/test_portfolio.py`, `tests/test_portfolio_private.py`, `tests/test_personal.py`, `tests/test_pages.py`, `tests/test_readme.py` | Tests of the research platform: calculations against independent references, privacy and security, accessibility structure, README completeness. |
| `tests/ref_finance.py`, `tests/ref_compare.py`, `tests/ref_portfolio.py`, `tests/ref_fundamentals.py` | Independent Python implementations of each calculation (test references only). |
| `tests/mock_alpaca.py`, `tests/make_explorer_fixtures.py` | A local mock of the market-data API and the generator of the Explorer fixtures. |
| `tests/js/*.js` | Node tests and cross-language check scripts for the browser calculations. |
| `tests/fixtures/explorer_expected.json`, `tests/fixtures/nasdaq-SPY.json`, `tests/fixtures/sample/*` | Expected Explorer numbers, a real saved Nasdaq response, and the sample history fixtures. |

## Notes and limits

* Quotes are delayed public data from Nasdaq, for information only; this is not investment advice.
* Raw files are committed to the repository but are not published on the site (only the two data files are).
* The history starts on 2026-11-14; early on, the Trends findings use fewer sessions and say so.
* Licence: the code is MIT (see `LICENSE`). Third-party data (Nasdaq quotes in `data/`, SEC filing data in `explorer/sec/`) is **not** covered; see `NOTICE`.
