# First real SEC build: review (MSFT, AAPL, WMT, JPM)

Built locally by the owner on 2026-11-15 from SEC company-facts data. Nothing here is published or committed; the generated files live
outside the repository. This note records what the build showed and what was done about it.

## Figures that are right but look odd

| Company | Observation | Explanation |
|---|---|---|
| WMT | fiscal year labelled FY2026 for the year ended 31 Jan 2026 | Walmart names its year for the calendar year in which it ends, so the label is correct. (An earlier note in `docs/sec-activation.md` said the opposite; corrected.) |
| WMT | no `Liabilities` and no `GrossProfit` | Walmart does not tag them. Total liabilities are not derived because Walmart's redeemable noncontrolling interest sits between liabilities and equity; gross profit is shown as derived (revenue minus cost of revenue, marked `*`), which differs from Walmart's own gross-profit-rate definition because membership income is in revenue. |
| JPM | no cost of revenue, gross profit, operating income or capex | a bank does not report them; left blank on purpose. |
| JPM | operating cash flow of -147.8 billion USD (FY2025) | banks' operating cash flow swings with trading assets and deposits; free cash flow is not meaningful for a bank. Needs the filing check. |
| AAPL | debt is `LongTermDebt` from FY2022 and noncurrent + current before | excludes commercial paper (documented). |

## Things the rules did not handle and what changed (reducer version 3)

1. **JPM debt looked current but stopped at FY2013** (JPM stopped using the `LongTermDebt` tag). The review printed "latest 267.9 billion" for a
   figure 12 years old. New check `STALE_SERIES` flags a series whose newest value is more than two years behind the company.
2. **MSFT operating cash flow lacks FY2014 and FY2015**, and the first point is FY2013. New check `GAP_IN_SERIES` flags a hole inside a series. The cause
   needs the saved SEC response: `python3 -m fundamentals explain MSFT operatingCashFlow --raw-dir ... --year 2015` shows every fact behind it.
3. **MSFT FY2016 balance sheet does not balance (5.7%).** Equity (83.09 billion) comes from a later filing than assets and liabilities: the FY2018 10-K
   restated the year (Microsoft adopted a new revenue standard retrospectively), while assets and liabilities still carry the original FY2016 filing. The
   rule "latest filed value wins" is applied per figure, so vintages mix. The check message now names the filing dates when they differ.
   FY2016 is outside the ten years shown on the page.
4. **JPM cash changes definition** (cash and due from banks, then cash and equivalents, then cash including restricted cash from FY2019). New check
   `TAG_SWITCH_JUMP` flags a change of more than 40% at the year a tag changes.

## Open items

- `verify` results for each company (automatic cross-check) and the manual comparison with the filings are still to be reported by the owner.
- MSFT FY2014 and FY2015 operating cash flow: pending `explain` on a saved response (needs one more build with `--raw-dir`).
- MSFT FY2016: decide whether to keep per-figure latest vintage (current) or take each balance sheet from a single filing.
