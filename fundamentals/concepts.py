"""Which us-gaap XBRL tags make up each metric, in priority order, and how a metric is read.

kind  'duration' = a flow over a fiscal year (income and cash-flow items); 'instant' = a balance at the fiscal year end.
The tag that supplied each number is stored with it, so every figure is traceable to a concept in the filing.
"""
METRICS = {
    "revenue":          {"label": "Revenue", "kind": "duration", "unit": "USD", "tags": [
        "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
        "RevenuesNetOfInterestExpense"]},                      # last: the total net revenue a bank reports; interest income alone is never used as revenue
    "costOfRevenue":    {"label": "Cost of revenue", "kind": "duration", "unit": "USD", "tags": [
        "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]},
    "grossProfit":      {"label": "Gross profit", "kind": "duration", "unit": "USD", "tags": ["GrossProfit"]},
    "operatingIncome":  {"label": "Operating income", "kind": "duration", "unit": "USD", "tags": ["OperatingIncomeLoss"]},
    "netIncome":        {"label": "Net income", "kind": "duration", "unit": "USD", "tags": ["NetIncomeLoss", "ProfitLoss"]},
    "epsDiluted":       {"label": "Diluted EPS", "kind": "duration", "unit": "USD/shares", "tags": ["EarningsPerShareDiluted"]},
    "operatingCashFlow": {"label": "Operating cash flow", "kind": "duration", "unit": "USD", "tags": ["NetCashProvidedByUsedInOperatingActivities"]},
    "capex":            {"label": "Capital expenditure", "kind": "duration", "unit": "USD", "tags": [
        "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]},
    "assets":           {"label": "Total assets", "kind": "instant", "unit": "USD", "tags": ["Assets"]},
    "liabilities":      {"label": "Total liabilities", "kind": "instant", "unit": "USD", "tags": ["Liabilities"]},
    "equity":           {"label": "Shareholders' equity", "kind": "instant", "unit": "USD", "tags": [
        "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]},
    "cash":             {"label": "Cash and equivalents", "kind": "instant", "unit": "USD", "tags": [
        "CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndDueFromBanks"]},                               # banks; the tag is stored with each value so the meaning stays visible
}
# Debt is assembled from parts: LongTermDebt already includes the current portion; LongTermDebtNoncurrent does not.
DEBT_TOTAL = ["LongTermDebt"]
DEBT_NONCURRENT = ["LongTermDebtNoncurrent"]
DEBT_CURRENT = ["DebtCurrent", "LongTermDebtCurrent"]

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "10-KT/A"}
ANNUAL_DAYS = (350, 380)         # a fiscal year is 52 or 53 weeks or a calendar year
MAX_YEARS = 12

# Data checks (see reduce.quality_checks). They flag, never change, a number.
IDENTITY_TOLERANCE = 0.02        # assets vs liabilities + equity (minority interest and redeemable equity can explain a gap)
GROSS_PROFIT_TOLERANCE = 0.01
JUMP_LIMIT = 0.8                 # a year-over-year revenue change larger than this is worth a second look

STALE_YEARS = 2                  # a series whose newest value is older than this many years behind the company is flagged
TAG_SWITCH_JUMP = 0.4            # a change this large at the year a tag changes is flagged (the definition may differ)
