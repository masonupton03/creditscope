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

## Methodology decisions (reducer version 4), approved by the owner on 2026-11-15

1. **One filing per balance sheet.** Total assets, total liabilities and shareholders' equity of a fiscal year all come from the latest annual
   filing that reports all of them. If the winning filing lacks one, that figure stays unavailable: it is never borrowed from another filing
   version. Every figure keeps its own filing date and accession number, and the Fundamentals page states the basis. (MSFT FY2016: the original
   equity of 71,997 million now pairs with that filing's assets and liabilities; the later restated 83,090 is not mixed in.)
2. **Stale series are not shown.** A series whose newest value is more than two fiscal years behind the company is moved out of the figures into
   `coverage.stale` with its last value, tag and filing, and the page says so. (JPM debt, last reported FY2013, is never presented as current.)
3. **Changes of meaning are disclosed.** Where tags for one metric are not interchangeable (cash: cash and equivalents, with restricted cash, cash and due
   from banks) the file records each run of one meaning, the check `DEFINITION_CHANGE` fires, the table marks cells of an older meaning with a dagger
   and a footnote, and the balance-sheet chart leaves cash out. Equivalent tags (for example debt as one tag or as noncurrent plus current) are not flagged.
4. **Banks are analysed as banks.** A company that reports deposits or interest income and has neither cost of revenue nor operating income gets
   `profile: "bank"`. Gross profit, operating income, capex, free cash flow, net debt, debt-to-equity and the margins built from them are not shown
   (the page says so) and key figures become net revenue, net margin, return on equity and return on assets.
5. **Missing means missing.** Nothing is estimated. Unreported figures are listed in the page's data panel and shown as a dash with a tooltip.

## Checks added along the way

`STALE_SERIES`, `GAP_IN_SERIES` (a hole inside a series), `TAG_SWITCH_JUMP` (more than 40% at a tag change), `DEFINITION_CHANGE`, and a balance-identity
message that names the filing dates when figures differ.

## Open items

- MSFT operating cash flow lacks FY2014 and FY2015 (and starts at FY2013). Cause unknown until the saved SEC response is examined with
  `python3 -m fundamentals explain MSFT operatingCashFlow --raw-dir ... --year 2015`.
- `verify` results and the manual comparison with the filings, per company, from the owner.
- JPM operating cash flow of -147.8 billion USD (FY2025): plausible for a bank, to be confirmed against the filing.
- WMT gross profit is derived (revenue minus cost of revenue) and is not Walmart's own gross-profit-rate definition; total liabilities are not reported.
