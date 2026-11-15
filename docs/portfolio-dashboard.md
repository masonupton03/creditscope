# Portfolio holdings dashboard: architecture and plan

Status: design approved in principle on 2026-11-14; implementation on `feature/stock-explorer` only (not merged, not deployed).
It supersedes the sketch in `personal-edition.md` ("lots" per account): a **transaction ledger** is the source of truth,
because cost basis, deposits, withdrawals and dividends all need dates, and a list of lots cannot express them.

## Hard rules

* **Private by construction.** Holdings live in `~/.creditscope/portfolio.json` (directory 0700, file 0600), outside the repo.
  They are read and written only through the localhost personal server. They are never put in `localStorage`, the service
  worker cache, a URL, a log line, a workflow or the repository. The public site shows a clearly labelled **simulated**
  sample portfolio, read-only.
* **No brokerage connection, no trading.** Positions are typed in by hand. Nothing here can place an order.
* **No change to the assignment pipeline** (`creditscope/`, `data/`, the three workflows, `index/browse/trends`).
* **Same validation discipline as `finance.js`:** every number is produced by a pure function with an independent Python
  reference (`tests/ref_portfolio.py`) and compared in tests.

## Data model (`portfolio.json`, version 1)

```json
{ "version": 1, "baseCurrency": "USD", "benchmark": "SPY",
  "transactions": [
    { "id": "t1", "date": "2024-01-02", "type": "deposit",    "amount": 10000 },
    { "id": "t2", "date": "2024-01-03", "type": "buy",        "symbol": "VTI", "shares": 20, "price": 235.10, "fee": 0 },
    { "id": "t3", "date": "2023-06-01", "type": "buy",        "symbol": "AAPL", "shares": 10, "price": 180.00, "external": true },
    { "id": "t4", "date": "2024-06-14", "type": "dividend",   "symbol": "VTI", "amount": 12.40 },
    { "id": "t5", "date": "2024-09-03", "type": "sell",       "symbol": "VTI", "shares": 5, "price": 260.00, "fee": 1 },
    { "id": "t6", "date": "2024-10-01", "type": "withdrawal", "amount": 500 },
    { "id": "t7", "date": "2024-10-02", "type": "fee",        "amount": 4 } ] }
```

* `buy`/`sell` use the **actual share count and price on that date** (before any later split). `external: true` means the cash
  came from / went to outside the portfolio (see decision D1). "Add position" in the UI is an `external` buy.
* `dividend` is an optional **manual** cash dividend. `fee` is a cash expense. Fees on trades are capitalised into cost basis
  (buys) or deducted from proceeds (sells).
* Validation (JS in the browser, Python in the server): ISO dates that exist, known types, positive numbers, symbol format,
  at most 5,000 transactions, file at most 1 MB. A sell may never exceed the shares held (no shorting).

## Calculation specification (all of it is implemented twice and cross-checked)

Calendar = the benchmark's (SPY's) trading dates. A transaction is applied at the end of the **first trading day on or after**
its date. Transactions after the last price date are ignored with a warning; those before the first benchmark date are applied on
the first date with a warning.

**Splits.** Series closes are split-adjusted to today. A transaction's shares are converted to the same basis:
`adjusted shares = shares x product of split ratios with ex-date after the transaction date`. Cost in dollars is unchanged.
Needs `series.splits`; if it is missing the holding is flagged `SPLITS_UNKNOWN` (a split would be silently wrong).

**Daily value.** `V(d) = cash(d) + sum(adjusted shares x close)`. A missing close is carried forward from the last earlier close
of that security and counted (`PRICE_STALE` if more than 7 days old). If a held security has **no** close at all on a date, the
day is *incomplete*; performance starts the day after the last incomplete day and the warning says so. Holdings are never
valued at cost to fill a gap.

**Dividends.** Credited to **cash** on the first trading day on or after the ex-date, for the shares held at the close of the
previous trading day (so buying on the ex-date earns nothing). Not reinvested. If a security has manual dividend transactions,
its automatic dividends are switched off (the user's records win). If a security's dividend history is unknown and there are
no manual dividends, the performance basis falls back to price (below).

**Time-weighted return (TWR), the number to compare with SPY.** External flows (`deposit`, `withdrawal`, `external` trades) are
assumed to happen at the end of the day, at the traded price, so intraday movement after a trade still counts:
`r(d) = (V(d) - F(d)) / V(d-1) - 1`, `F` = net external flow that day; the TWR index is the chain of `1 + r`. The index starts at the
end of the first day with value. Days following a zero value are skipped and counted. Fees reduce return; dividends are in `V`.

**Money-weighted view, Modified Dietz (any window):**
`R = (V1 - V0 - sum F) / (V0 + sum w F)`, `w = (T - t) / T`, `t` = days from the window start, end-of-day flows.

**Simple change in account value is never called a return.** The page always shows, side by side and labelled:
account value change, net contributions (deposits minus withdrawals), investment gain (`value change - net contributions`,
in dollars, after fees, including dividends), TWR %, Modified Dietz %.

**Basis.** `total` if SPY and every security ever held have known dividends (or manual dividends); otherwise **both** sides use
`price`, with dividends excluded from the portfolio simulation, and the label says so. The two bases are never mixed.

**Risk (over the chosen window, on TWR daily returns).** Volatility = sample stdev x sqrt(252) (needs 20 returns); beta, correlation
vs SPY need 60 overlapping returns; maximum drawdown of the TWR index with peak/trough/recovery dates (same 1e-12 tie rule as
`finance.js`, reused, not copied); annualised return only for windows of at least 365 days.

**Holdings and concentration (as of the last date).** FIFO lots; cost basis includes buy fees; unrealised = value - remaining cost;
realised = proceeds - consumed cost. Weights are of total portfolio value (cash is its own line). Concentration over
positions only: top-1 / top-3 / top-5 share, Herfindahl index `sum w^2`, effective number of holdings `1 / HHI`; allocation by
security, by type (ETF / stock / cash).

## Decisions that materially affect accuracy or privacy (user to confirm)

| # | Decision | Default I implemented | Why it matters |
|---|---|---|---|
| D1 | How a manually entered position is funded | `external: true` buy = an implicit deposit of cost + fee on the buy date | Without cash tracking there is no other correct choice; a buy that is **not** marked external draws down tracked cash and warns on negative cash |
| D2 | Flow timing | End of day, at the traded price | Start-of-day would credit a day's return that was never earned |
| D3 | Dividends | To cash, ex-date, previous-close shares, not reinvested | Pay dates are not in the data; reinvestment is a choice the real account may not have made. Benchmark total return **does** reinvest, so the label says so |
| D4 | Missing prices | Carry forward, flag staleness, never value at cost; start performance after a gap | Silent fill would invent returns |
| D5 | IEX-only data | Prices are IEX trade prices; volume is **not** shown for the portfolio at all, and the IEX label is shown wherever prices are | IEX volume is a fraction of market volume |
| D6 | Privacy of the file | Local file only, server-side validation, no browser storage, backups kept beside it | A browser store would sit in a profile that screenshots and sync can expose |
| D7 | Tax lots, wash sales, currencies, options, shorting | Out of scope; FIFO only, USD only | Wrong tax numbers are worse than none |

## Components

| Piece | Where | Public? |
|---|---|---|
| Engine `analyze()` | `assets/js/portfolio.js` (pure) | yes (code only) |
| Independent reference | `tests/ref_portfolio.py` | yes |
| Storage + validation | `personal/portfolio.py`; `GET/PUT /api/portfolio` on the personal server (loopback, Host check, Origin check, custom header, optimistic revision, atomic write, one backup) | yes (code only) |
| Page | `portfolio.html`, `assets/js/portfolio-page.js` | yes (code only) |
| Real holdings | `~/.creditscope/portfolio.json` | **never** |
| Demo | `explorer/sample/portfolio.json` (simulated) | yes, labelled |

## Build order and tests

1. Engine + reference + cross-check fixtures (cash flows, splits, dividends, gaps, oversell, price/total basis).
2. Splits in the series files from Alpaca (additive field) + tests.
3. Storage/server endpoints + security tests (bad Host, bad Origin, missing header, oversize, malformed, concurrent revision).
4. Page: holdings table, allocation charts, value vs contributions, TWR vs SPY, risk cards, add/edit/delete transactions.
5. Browser verification in demo mode and personal mode against the mock; privacy checks (no storage, no cache, no console errors).

Not in this phase: SEC fundamentals (next public feature), CSV import, XIRR, risk contribution, target-weight drift.
