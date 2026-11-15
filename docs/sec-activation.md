# Activating real SEC EDGAR fundamentals (Microsoft, Apple, Walmart, JPMorgan Chase)

Status: everything is built and tested offline. **No request has been made to the SEC.** The steps below need you; each step that
contacts the SEC or publishes data is marked **[needs your OK]**.

## What is ready

| Piece | Where | State |
|---|---|---|
| Client (5 requests/second, retries, gzip, refuses a missing or placeholder contact, never prints it) | `fundamentals/sec.py` | tested against a local mock server |
| Reducer (annual 10-K facts, tag priority, restatements, fiscal-year labels, bank shape, missing tags left blank) | `fundamentals/reduce.py`, `concepts.py` | tested, including a Microsoft-style June year, Apple-style 52/53-week year, Walmart-style January year and a bank |
| Coverage and data checks (flag, never change numbers) | `fundamentals/reduce.py` | tested |
| Cross-check and manual checklist | `python -m fundamentals verify` | tested against the mock |
| Offline review report (`review`) | `python -m fundamentals review --out DIR` | tested |
| Offline readiness check | `python -m fundamentals preflight` | makes no request |
| Manual build workflow (inactive example) | `docs/fundamentals-workflow.example.yml` | builds, verifies, uploads an artifact; commits nothing |
| Page | `fundamentals.html` | shows the simulated companies today; shows real ones once `explorer/sec/` has files |

The first run is `MSFT, AAPL, WMT, JPM`. Their quirks are covered in `docs/sec-edgar-plan.md`: Microsoft's year ends in June, Apple's
ends on a Saturday near 30 September (52 or 53 weeks), Walmart's ends 31 January and is named for the year before, and JPMorgan is a
bank, so gross profit and operating income are legitimately blank and revenue is "net revenue".

## Step 1: create a dedicated contact mailbox (you)

The SEC asks every automated client to identify itself with a real contact. Use a mailbox that exists only for this project, not your
personal address, because the SEC may write to it and the address appears in request headers on the SEC's side.

1. Create a free mailbox, for example `creditscope.project@<provider>` (any provider you control and will check).
2. Send yourself a test message so you know it works.
3. Do not put the address in the repository, the README, an issue, a commit message or a chat that is shared.

## Step 2: add it as a GitHub secret (you)

The value is a short text that names the project and gives the contact:

`CreditScope educational project creditscope.project@<provider>`

In the browser:

1. Open `https://github.com/masonupton03/creditscope/settings/secrets/actions` (Repository, Settings, Secrets and variables, Actions).
2. Choose **New repository secret**.
3. Name: `SEC_USER_AGENT` (exactly).
4. Secret: the line above with your real mailbox.
5. Choose **Add secret**. GitHub hides the value afterwards and masks it in logs.

Or with the command line (the value is typed at a prompt and not stored in your shell history):

```bash
gh secret set SEC_USER_AGENT --repo masonupton03/creditscope
```

Check that it exists (the value is never shown): `gh secret list --repo masonupton03/creditscope`.

## Step 3: activate the workflow (tell me, I make the change) [needs your OK]

The workflow lives outside `.github/workflows/` so GitHub ignores it. After you say go, I copy it to
`.github/workflows/fundamentals.yml` on `feature/stock-explorer`. GitHub only lists and runs a manually triggered workflow that is
on the default branch, so it will not be runnable until the branch is merged, **or** you can run the same steps locally (Step 4, option B).
Merging is a separate approval, and the daily assignment workflow is not touched either way.

## Step 4: the first live build [needs your OK]

**Option A, in GitHub (after the workflow is on `main`).** Actions, **Build SEC fundamentals (manual)**, **Run workflow**, keep the
default tickers `MSFT,AAPL,WMT,JPM`. The job runs `preflight` (no request), then `build`, then `verify` for each company, and
uploads an artifact named `sec-fundamentals` (the four company files, `index.json`, and one checklist per company). Download it.

**Option B, on your computer (works today).** Run these in your own Terminal, from the repository folder. Nothing is written inside the repository.

```bash
cd ~/creditscope
# 1. contact: typed at a hidden prompt, kept only in this Terminal window (never in a file, history or chat)
read -rs "SEC_USER_AGENT?Contact (e.g. CreditScope educational project name@your-project-mailbox): "; echo   # zsh; in bash use: read -rsp "..." SEC_USER_AGENT
export SEC_USER_AGENT
# 2. offline readiness check: must end with "Ready"; makes no request
python3 -m fundamentals preflight
# 3. fetch MSFT, AAPL, WMT, JPM into a folder OUTSIDE the repository
OUT=~/creditscope-sec-review; mkdir -p "$OUT"
python3 -m fundamentals build --tickers MSFT,AAPL,WMT,JPM --out "$OUT"
# 4. cross-check each company through a second SEC endpoint and write a manual checklist
for t in MSFT AAPL WMT JPM; do python3 -m fundamentals verify $t --out "$OUT" --sheet "$OUT/$t.md"; done
# 5. offline review report: coverage, tags used, warnings, missing fields, margins
python3 -m fundamentals review --out "$OUT" | less
# 6. forget the contact
unset SEC_USER_AGENT
```

Total traffic: 5 requests for the build and up to about 80 for the checks (one per distinct data tag per company), at 5 per second, well under the SEC's limit.

## Step 5: verify against the filings by hand (you, about 30 minutes)

Open each `<TICKER>.md` checklist. For each of the most recent three fiscal years it lists every figure with a link to the filing.
Compare revenue, net income, total assets and operating cash flow with the filing's statements, then tick the rows. Read
`coverage` and `checks` in each company file for gaps (expected: JPM has no gross profit and no operating income). Tell me about any
mismatch and I will fix the rule, not the number.

## Step 6: publish the data [needs your OK, together with the merge]

Only after Step 5 passes: I copy the four compact company files and `index.json` into `explorer/sec/`, run the whole test suite, and
commit them on the branch. They are small (a company file is well under 60 KB, enforced by a test). Raw SEC downloads are never committed.
They go live with the normal merge, using `docs/launch-checklist.md`.

## If something goes wrong

- `preflight` says NOT READY: the secret or variable is missing, or contains a placeholder or no address.
- HTTP 403 or 429 from the SEC: the contact was missing or the rate was too high. The client stops with a message that does not
  contain the contact; wait ten minutes and try once more.
- A company is skipped: it is not in the SEC ticker list or reports no annual US-GAAP facts. It is named in the build summary.
- To undo: delete `explorer/sec/company/*.json` and restore the empty `index.json`; nothing else depends on them.
