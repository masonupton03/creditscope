# CreditScope personal edition

A private, local-only version of the Stock Explorer that uses **your own** market-data account. It exists next to the public
site; it never touches the assignment pipeline, and nothing it downloads is committed or published.

```
public site (GitHub Pages)            personal edition (your computer only)
  simulated sample data      <──same Explorer page, same finance.js──>   real data from your Alpaca account
  explorer/sample/                                                        ~/.creditscope/data  (outside the repo)
```

## Why it is private

Every provider I reviewed restricts **public display** of its data on free plans (see `explorer-data-sources.md`). So the
real data is used for your own research only: stored outside the repository, served to `localhost`, never deployed, and
never shown to other people (screenshots and screen-sharing count as display under some providers' wording).

## What you need from Alpaca

| Question | Answer (from Alpaca's current docs, 2026-11-14) |
|---|---|
| Account type | **Paper Only Account.** "Anyone globally can create an Alpaca Paper Only Account! All you need to do is sign up with your email address." |
| Cost | Free. The Paper Trading API "does not require real money." The **Basic** market-data plan is the free default. |
| Do paper keys work for market data? | Yes: "If you have a paper account, you can call: Market Data API endpoints on `data.alpaca.markets`." |
| Identity verification / funding / SSN | **Not stated** in the pages I read for paper-only accounts. Live brokerage accounts do require verification; you do not need one. |
| Where keys come from | The web dashboard, "under the API keys on the right sidebar". Exact click steps, whether the secret is shown only once, and how to regenerate keys are **not documented** in the pages I read. Assume the secret is shown once and copy it straight into `setup`. |
| Limits on Basic | 200 historical calls per minute; daily bars "since 2016"; US stocks and ETFs. |
| **Important caveat** | The paper-trading docs say a Paper Only Account "is only entitled to receive and make use of IEX market data." IEX is one exchange: prices come from IEX trades and **volume is IEX-only**, a small fraction of the market. The Basic plan table separately lists consolidated (SIP) history older than 15 minutes. The documents disagree, so `python -m personal doctor` **tests which one your account gets** and every screen labels an IEX-only result. |
| Terms | Alpaca's Terms and Conditions (linked PDF, created 2021): content is "solely for your own personal and non-commercial purposes", and "publicly displayed" or "mirroring" needs prior written consent. Private use is what this edition does. |

If your account turns out to be IEX-only and you want consolidated data, the options are a funded live brokerage account
(identity verification) or another provider's free key for personal use. The code isolates the provider in
`personal/alpaca.py`, so a second provider is an adapter, not a rewrite.

## Secure setup (you never paste credentials into chat)

1. Create the Paper Only Account and generate a **paper** API key (key ID + secret) in Alpaca's dashboard.
2. Open a normal **Terminal** window (not this chat) and run:

   ```bash
   cd ~/creditscope
   git checkout feature/stock-explorer
   python3 -m personal setup        # two hidden prompts: key ID, then secret; nothing is echoed
   python3 -m personal doctor       # checks the account, feed (SIP or IEX), history depth, dividends, ETFs
   python3 -m personal doctor --verify-dividends   # cross-checks dividend amounts against Alpaca's adjusted bars
   python3 -m personal sync         # downloads 10 years of daily bars for your universe
   python3 -m personal serve        # http://localhost:8765/explorer.html
   ```
3. Python 3.9 is fine; the personal edition uses only the standard library.

Where things live and how they are protected:

| Item | Location | Protection |
|---|---|---|
| API key and secret | `~/.creditscope/credentials.json` | Outside the repo, directory `0700`, file `0600`; `setup` refuses to write inside any git repository; `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` environment variables override it |
| Market data | `~/.creditscope/data/` | Outside the repo; `.gitignore` also blocks `private/`, `private-data/`, `.env`, `credentials*.json`, `*.pem`, `*.key` |
| Your symbol list | `~/.creditscope/universe.json` (optional) | A JSON array of tickers; default is SPY plus the 12 assignment ETFs and a few others |
| Server | `127.0.0.1` only | Refuses non-loopback binds, rejects any `Host` header that is not localhost, serves only an allow-list of site files, marks private responses `no-store`, and the service worker never caches `private-data/` or `api/` |
| Tests | `tests/test_personal.py` | Scans every tracked file for secret-like strings, asserts the private paths are ignored, that no workflow mentions them, and that no response ever contains the credentials |

`python3 -m personal forget` deletes the stored credentials. If a key is ever exposed (pasted somewhere, committed,
screenshotted), regenerate it in Alpaca's dashboard and run `setup` again.

## What it does today

* **Searchable securities:** the whole Alpaca asset list is searchable (`doctor` reports how many symbols your account sees). ETF/stock labels are a
  **name-based guess** because Alpaca does not flag ETFs.
* **Historical data:** daily bars via `adjustment=split` (Alpaca's default is `raw`), so closes are split-adjusted and not
  dividend-adjusted, exactly the model `finance.js` expects.
* **Dividends:** from the corporate-actions endpoint. Amounts are divided by the product of later split ratios so they are on
  the same split-adjusted basis as the closes. Alpaca does not say whether it already adjusts dividend rates, so
  `doctor --verify-dividends` compares them with Alpaca's own dividend-adjusted bars.
* **Symbols you have not synced** are downloaded on demand by the local server and cached privately; if Alpaca cannot be
  reached, the stale cached copy is served.
* Everything the public Explorer does: SPY comparison, return/volatility/drawdown/volume, price-return vs total-return
  labels, the persistent watchlist.

## Designed for the next phases

**Custom watchlists.** Today a watchlist is a list of tickers in the browser's storage. Next: several named lists stored in
`~/.creditscope/watchlists.json` (survive browser changes), and `sync` keeps the union of all lists and holdings up to date.

**Portfolio holdings** are built: see `portfolio-dashboard.md` (transaction ledger in `~/.creditscope/portfolio.json`, edited through the
local server, analytics in `assets/js/portfolio.js` verified against `tests/ref_portfolio.py`).

**Still to add** to `finance.js`/`portfolio.js`, each with an independent reference: correlation matrix, contribution to risk, drift
from target weights, XIRR.

## Not done yet (decisions are in the project discussion)

* Alpaca account and keys (yours to create), and the result of `doctor` on them.
* Adapters for another provider if the IEX-only limit matters.
* Multiple named watchlists, risk contribution, target-weight drift, CSV import of transactions.
