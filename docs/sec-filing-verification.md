# Filing-level verification of the first four companies (2026-11-15)

Method: each company's annual report (Form 10-K) was read on sec.gov through a page-fetch tool, **not** through the XBRL companyfacts or companyconcept
APIs. CreditScope's reduced files were then compared with the printed amounts. Amounts are USD millions as printed. 82 figures (latest and prior fiscal
year, 4 companies) were compared: 0 differences.

What "read the filing" means here, per company (the fetch tool caps long pages, so this differs):

| Company | Main 10-K document | Statements read from |
|---|---|---|
| Apple | read, text verbatim through Note 7 | the document itself (income statement, balance sheet, cash flows); debt table from the filing's rendered R pages (R66, R68) |
| Microsoft | cover and MD&A summary table verbatim; Item 8 not reached | the filing's rendered statement pages R2, R4, R6; debt note R20, R73; lease supplement R91 |
| Walmart | cover and MD&A verbatim; Item 8 not reached | the filing's rendered statement pages R3, R5, R8 |
| JPMorgan | **not retrieved** (12.9 MB, over the tool's 10 MB limit) | the filing's rendered statement pages R3, R5, R9 |

The rendered R pages are the filing's own presentation of its financial statements, but they are produced from the filing's XBRL data, so for Microsoft,
Walmart and JPMorgan the statements were not read from the printed 10-K text. The tool also summarises pages in places; only verbatim table text was
used. A human spot check of a few figures on the printed filing is still advisable before public launch.

Filings: Apple https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/aapl-20260926.htm ·
Microsoft https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm ·
Walmart https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm ·
JPMorgan https://www.sec.gov/Archives/edgar/data/19617/000162828026008131/ (index; statements R3, R5, R9). Filing dates come from the EDGAR index, not the cover pages.

## Apple (fiscal year ended 2026-09-26, 10-K filed 2026-11-03)

| Figure | Filing | CreditScope | Difference |
|---|---|---|---|
| Net sales | 478,834 | 478,834 | none |
| Cost of sales / gross margin | 245,232 / 233,602 | 245,232 / 233,602 | none |
| Operating income | 158,063 | 158,063 | none |
| Net income | 132,175 | 132,175 | none |
| Total assets / liabilities / equity | 404,548 / 292,455 / 112,093 | same | none (292,455 + 112,093 = 404,548) |
| Cash and equivalents | 36,305 | 36,305 | none |
| Operating cash flow | 145,097 | 145,097 | none |
| Payments for property, plant and equipment | 9,041 | 9,041 | none |
| Debt | term debt 78,114 (commercial paper 1,997 shown separately) | 78,114 | **definition**: CreditScope's debt is term debt and excludes commercial paper; with it, 80,111 |

Verdict: **verified with one disclosed definition** (debt excludes commercial paper; say so next to the figure).

## Microsoft (fiscal year ended 2026-06-30, 10-K filed 2026-07-29)

| Figure | Filing | CreditScope | Difference |
|---|---|---|---|
| Revenue | 331,839 | 331,839 | none |
| Cost of revenue / gross margin | 106,374 / 225,465 | same | none |
| Operating income | 155,237 | 155,237 | none |
| Net income | 133,749 | 133,749 | none |
| Total assets / liabilities / equity | 758,376 / 315,989 / 442,387 | same | none |
| Cash and equivalents | 20,935 | 20,935 | none (short-term investments of 55,908 are separate) |
| Net cash from operations | 182,935 | 182,935 | none |
| Additions to property and equipment | 115,948 | 115,948 | none; **definition**: excludes right-of-use assets obtained under finance leases (24,608, non-cash), so free cash flow excludes them |
| Debt | Note 10 total debt 40,294 (face value 46,136) | 40,294 | **definition**: carrying amount, not face value |

Prior year (FY2025) also matches on all compared figures. Not checked against the filing: FY2015 operating cash flow of 29,668 (continuing operations tag, from the FY2017 10-K) and all years before FY2025.
Verdict: **verified with disclosed limitations** (capex excludes finance leases; debt at carrying value; older years carry only the automatic cross-check).

## Walmart (fiscal year ended 2026-01-31, 10-K filed 2026-03-13)

| Figure | Filing | CreditScope | Difference |
|---|---|---|---|
| Total revenues | 713,163 (net sales 706,413 + membership and other income 6,750) | 713,163 | none |
| Cost of sales | 535,395 | 535,395 | none |
| Operating income | 29,825 | 29,825 | none |
| Net income | consolidated 22,270; attributable to Walmart 21,893 | 21,893 | **definition**: attributable to Walmart |
| Total assets | 284,668 | 284,668 | none |
| Equity | Walmart shareholders' equity 99,617; noncontrolling interest 6,270; total 105,887 | 99,617 | **definition**: shareholders' equity excluding noncontrolling interest |
| Total liabilities | no such line on the balance sheet (redeemable noncontrolling interest 293 sits outside) | blank | correct: not estimated |
| Operating cash flow | 41,565 | 41,565 | none |
| Payments for property and equipment | 26,642 | 26,642 | none |
| Debt | due within one year 3,542 + long-term 34,624 = 38,166 | 38,166 | **definition**: excludes short-term borrowings (6,596) and finance leases (6,761) |
| Gross profit | not reported | derived 177,768 | **definition**: Walmart's own gross profit is net sales minus cost of sales = 171,018; CreditScope's derived figure includes 6,750 of membership and other income |

Prior year (FY2025) matches on all compared figures.
Verdict: **verified with disclosed limitations**. The derived gross profit and gross margin (24.9% against 24.2% on Walmart's basis) are the one figure a reader could misread. Decision for the owner: show it as derived (current, marked `*`), relabel it, or suppress it for this company.

## JPMorgan Chase (year ended 2025-12-31, 10-K filed 2026-02-13)

| Figure | Filing | CreditScope | Difference |
|---|---|---|---|
| Total net revenue (reported basis) | 182,447 (net interest income 95,443 + noninterest revenue 87,004) | 182,447 | none; managed-basis revenue (MD&A) not retrieved and not used |
| Net income | 57,048 | 57,048 | none |
| Total assets / liabilities / equity | 4,424,900 / 4,062,462 / 362,438 | same | none |
| Operating cash flow | (147,782) (2024: (42,012); 2023: 12,974) | -147,782 | none; the sign is real and typical of a bank (trading assets, loans held for sale) |
| Cash | cash and due from banks 21,742 + deposits with banks 321,596 = 343,338 (cash flow statement total) | 343,338 | **definition**: FY2019 onward uses the cash flow statement total; FY2015-2018 cash and equivalents; FY2014 cash and due from banks only (27.8bn). The filing shows no restricted-cash line; the tag name says "including restricted cash" |
| Debt | long-term debt 435,206; short-term borrowings 64,776 | not shown | correct: JPM stopped using the tag we read (last FY2013); never presented as current |

Prior year (2024) matches on all compared figures.
Verdict: **verified with disclosed limitations**; the weakest evidence of the four (main document not read; statements from the rendered pages). Not claimed: managed-basis revenue, debt, gross profit, operating income, capex, free cash flow.

## Summary

| Company | Verdict |
|---|---|
| Apple | verified (debt excludes commercial paper, disclosed) |
| Microsoft | verified with disclosed limitations |
| Walmart | verified with disclosed limitations (derived gross profit needs a decision) |
| JPMorgan | verified with disclosed limitations (weakest evidence; spot check advised) |

No figure was changed to make it match.
