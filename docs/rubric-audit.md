# Assignment rubric audit: "Data Tracker Project" (Financial Data Analytics)

Audit of every requirement in the assignment PDF against the code and outputs of **`main`** (the submitted work), re-checked on
**2026-11-15 (UTC)**. The Stock Explorer / personal edition / fundamentals work lives only on `feature/stock-explorer`; it is not
part of the submission and is not deployed (`https://masonupton03.github.io/creditscope/explorer.html` returns 404).

How to read the columns: **Evidence** is what I actually ran or observed, with the date; **Still to verify** is what only time or
the owner can confirm. The pipeline code (`creditscope/`) and the three workflow files are
byte-identical between `main` and the development branch (`git diff main --stat -- creditscope .github` is empty). The branch's
`data/` is simply *behind* `main`, which has gained the daily-run commits since the branch was cut; merging must bring them in
(see `docs/launch-checklist.md`).

## Zero-credit conditions (each can zero a whole component)

| Condition in the PDF | Status | Evidence / what remains |
|---|---|---|
| Fewer than **7 different days** with a successful run, or last successful run **> 48 h before the due date** (zero for Pipeline) | **Not yet satisfied: 2 of 7 days** | `data/status.json` on `main`: `days_with_success: 2` (2026-11-14 and 2026-11-15). The cron has fired **by itself** once (run created 2026-11-15T01:19Z, success, Issue #2 opened, site redeployed). **Needs 5 more distinct UTC dates and a successful run no earlier than Dec 1 (due date Dec 3, 2026 as recorded in the project notes; confirm on Blackboard).** |
| History file not reproduced by the build from the raw files (zero for Data) | Satisfied | 2026-11-15: exported `main`'s `data/` into a new empty folder, ran `python -m creditscope --root <folder> build`: output `history.csv` is **byte-identical** (SHA-256 `5813c875…f7837`) to the committed file; 24 rows. Also `tests/test_build.py::test_build_twice_gives_identical_bytes`, `test_history_rebuilds_from_scratch_in_a_new_folder`. |
| Trends numbers not matching the history file (zero for Trends) | Satisfied (tested) | All Trends numbers are computed in the browser by `assets/js/stats.js` from `data/history.csv`; `tests/js/stats.test.js` (14 tests) and `tests/ref_stats.py` (independent Python implementation) agree; browser check on 2026-11-15: the page's day count and row count equal the file's (`scripts/browser-audit/required-pages.js`). Re-run after more days accumulate. |
| Site not working at the site URL (zero for Site) | Satisfied | 2026-11-15: `https://masonupton03.github.io/creditscope/` → 200; `browse.html`, `trends.html`, `sw.js`, `manifest.webmanifest` → 200; live `data/status.json` shows the 2026-11-15T01:19:49Z run. |

## Items (the data)

| # | Requirement | Where satisfied | Evidence |
|---|---|---|---|
| 1 | At least ten items the source reports every day | 12 ETFs in `creditscope/config.py` (`ETFS`): SPY QQQ IWM EFA EEM XLF SHY IEF TLT AGG LQD HYG | `status.json`: `items: 12`, 12 sources `ok: true` on both days |
| 2 | At least two numeric values per item | `price`, `volume`, `net_change`, `pct_change` | columns in `data/history.csv` |
| 3 | A key that identifies each item | `item_id` = ticker (e.g. `SPY`) | `data/history.csv`; sort/join logic in `creditscope/build.py` |
| 4 | Source downloadable from a runner with no login; secrets never in the repo | Nasdaq public quote JSON (`creditscope/sources.py`), no key | runs succeed on GitHub runners; `tests/test_personal.py` secret-pattern scan of tracked files; no secret is used by the pipeline |
| – | If a source returns more than you track, keep only the tracked part; README says what is kept | `creditscope/convert.py` keeps listed fields only | README section "Data source"; `tests/test_convert.py` (30 tests) |

## Pipeline (daily, `.github/workflows/daily.yml` + `creditscope/run.py`)

| # | Requirement | Where satisfied | Evidence |
|---|---|---|---|
| 1 | Call every source; save raw, compressed, in original format at `data/raw/<date>/<source>.<format>.gz`; one failure does not stop the run; failed source writes no raw file; every result recorded | `creditscope/raw.py`, `run.py`; `data/raw/2026-11-14/nasdaq-SPY.json.gz` etc.; per-day log `data/runs/<date>.json` | `tests/test_run.py` (11): `test_failed_download_does_not_stop_the_run`, `test_failure_is_recorded_in_the_run_log`, `test_unusable_response_counts_as_failure_and_is_not_saved`, `test_run_survives_every_source_failing`; `test_build.py::test_raw_files_are_compressed_and_hold_the_original_bytes` |
| 2 | Build history from the raw files alone | `creditscope/build.py` | rebuild byte-identical (above); `test_history_depends_on_raw_files_only`, `test_changed_rule_applies_to_every_day` |
| 3 | Write the status file | `creditscope/status.py` → `data/status.json` | keys verified 2026-11-15: `days_with_success, first_run_date, gone_today, items, new_today, run_time, sources`; each source `{name, ok, count}` |
| 4 | Issue titled with the date: biggest moves with old/new values, appeared/disappeared, close the previous day's issue, open every day even with no changes | `creditscope/issues.py` (uses `gh`), `moves.py`; rule in README "The move rule" | live: Issue #2 "CreditScope daily update: 2026-11-15" open, Issue #1 "…2026-11-14" **closed** by the next run; body says "No item changed price since the previous run" (a no-change day still produces an issue); `tests/test_issues.py` (9), `tests/test_moves.py` (14) |
| 5 | Commit raw, history, status | `daily.yml` commit step | `git log origin/main`: "Daily run 2026-11-14 …", "Daily run 2026-11-15: 12/12 sources ok" |
| – | Successful run = finishes and commits even if sources failed; **second run the same day replaces that day's raw files, rebuilds, updates that day's issue, counted once** | `run.py`, `issues.py` | `test_second_run_same_day_counts_once_and_replaces_raw`, `test_rerun_where_a_source_fails_keeps_the_earlier_raw_file`, `test_rerun_updates_todays_issue_instead_of_creating_another`; several manual re-dispatches on 2026-11-14 (the workflow-run list shows at least four) left a single day in history |
| – | UTC date of the moment of the run | `run.py` | `test_utc_date_comes_from_the_moment_of_the_run`. **Observation:** the cron is set for 21:45 UTC but GitHub started the first scheduled run at 01:19 UTC the next day (~3.5 h late), so its date was 2026-11-15. Late starts can shift or skip a UTC date; see risks. |

## Build and data files

| Requirement | Where satisfied | Evidence |
|---|---|---|
| One common set of columns per day; rows sorted by date then `item_id`; day with no raw file for a source has no rows from it | `creditscope/convert.py`, `build.py` | `test_rows_sorted_by_date_then_item_id`, `test_day_without_a_raw_file_for_a_source_has_no_row_from_it`, `test_sort_does_not_depend_on_raw_file_order` |
| `data/history.csv`: first four columns `date,item_id,item,source`; UTC dates `YYYY-MM-DD`; unreported value left empty | `build.py` | header verified 2026-11-15: `date,item_id,item,source,asset_class,category,price,volume,net_change,pct_change,price_date,market_status`; `test_header_starts_with_the_four_fixed_columns`, `test_missing_values_are_left_empty` |
| `data/status.json` keys exactly as specified (`run_time` UTC, `first_run_date` = earliest raw file, `days_with_success` = distinct dates with a raw file, `items`, `new_today`, `gone_today`, `sources`) | `status.py` | keys verified; `test_multiple_days_status_counts_and_appeared_disappeared` |

## Site (`index.html`, `browse.html`, `trends.html`)

Browser check run 2026-11-15 against the current branch (which adds only a nav link, a skip link and a light-theme colour change to
these pages): `scripts/browser-audit/required-pages.js`, **22 of 22 checks passed**; offline check passed (below).

| Requirement | Where satisfied | Evidence |
|---|---|---|
| Three pages load the two data files in the browser and calculate there | `assets/js/{common,stats,today,browse,trends}.js` | pages read `data/history.csv` and `data/status.json`; no server code |
| **Today**: time of last run, status of every source, status-file counts, latest values with change since previous run, biggest moves | `index.html`, `today.js` | check: 12 sources, items count and days count from `status.json`, every item's latest row, moves section present |
| **Browse**: filters on ≥ 2 columns, search on names, sort by every numeric column up and down, star → shortlist stored in the browser and kept after reload | `browse.html`, `browse.js` (asset class, category, direction filters; `creditscope.shortlist` in localStorage) | check: search narrows; asset-class and category filters; **order verified against `history.csv` values for price, volume, net_change, pct_change, ascending and descending**; a starred item survives a reload and the shortlist filter shows it |
| **Trends**: chart of each numeric value over the days with a control that picks items; ≥ 4 sections each with a finding heading, explanatory paragraph with numbers and how they are computed, and a chart | `trends.html`, `trends.js` | check: ≥ 4 finding sections, ≥ 5 charts, a value selector and item picker; numbers agree with the history file (above) |
| Installable: manifest + service worker; online loads data from network; offline still opens and shows last data | `manifest.webmanifest`, `sw.js` (network-first for data, stale-while-revalidate for the shell) | check: manifest has name, start_url, standalone display, 192 and 512 icons; service worker activates; **offline test 2026-11-15: after one online visit the web server was stopped and all three pages reopened from cache with data and an offline notice**. **Still to verify by the owner:** the browser's actual "Install app" prompt on their own machine and phone (cannot be confirmed from automation). |
| One navigation bar, one set of fonts and colours | `assets/css/site.css` | check: identical link list on the three pages; `tests/test_site.py` |

## Tests

| Requirement | Evidence |
|---|---|
| pytest suite covering conversion of each source, the move rule, history logic incl. second run the same day | `tests/test_convert.py` (30), `test_moves.py` (14), `test_build.py` (14), `test_run.py` (11), `test_issues.py` (9) |
| GitHub Actions runs the tests on every push; README shows the badge | `.github/workflows/tests.yml` (`on: push`, `pull_request`); badge on README line 3; latest run on `main` and on the branch **success** (2026-11-15). The whole suite is currently **310 pytest + 71 Node tests**, all passing locally. |

## Repository

| Requirement | Evidence |
|---|---|
| Project in its own folder under the home folder, not in `~/fda-python` | `~/creditscope` |
| Public repo with GitHub Pages enabled | `github.com/masonupton03/creditscope`; Pages API reports the site URL; site returns 200 |
| README lists every file, every source with format, every column with meaning and unit, the move rule, the command that rebuilds the history | `README.md` sections "Files", "Data source", "Columns of `data/history.csv`", "The move rule", "Rebuild the history from the raw files" (`python -m creditscope build`) |
| Pipeline, tests, workflows, data files, site files | present (`creditscope/`, `tests/`, `.github/workflows/`, `data/`, `*.html`, `assets/`) |
| Commit history that shows the work as it was done, including daily pipeline commits | 22 commits on `main`, 5 of them "Daily run …" commits by the pipeline |
| Issues | #1 (closed), #2 (open) |
| Using AI tools (Claude Code) | built with Claude Code |

## Submission

| Item | Status |
|---|---|
| One `.txt`/`.md` file with four lines: name, student ID, repository URL, site URL | **Not created: the student ID is needed from the owner.** Repository URL and site URL are known. |
| First successful run by the first-run date (posted on Blackboard) | Completed 2026-11-14; confirm the posted date on Blackboard. |

## Risks and what remains

1. **Days:** 5 more distinct successful UTC dates are needed; the last must be within 48 h of the due date. Do not let the schedule lapse (GitHub disables scheduled workflows after 60 days without repository activity; not a risk at this horizon). Manual `workflow_dispatch` runs on a day that already has data do not add a day.
2. **Late scheduled start:** the first scheduled run started ~3.5 h late. A run delayed past 00:00 UTC lands on the next date, and a very late one could skip a date. Check the run list every few days; a manual dispatch fixes a missed day.
3. **Nasdaq terms:** the source is a public quote endpoint; its terms are restrictive for redistribution (see `docs/explorer-data-sources.md`). The site states that prices are delayed and for information only.
4. **Install prompt** must be confirmed by the owner on a real device.
5. **Merging the development branch** must re-run this audit (checklist in `docs/launch-checklist.md`).
