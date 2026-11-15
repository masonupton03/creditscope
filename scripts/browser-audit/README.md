# Browser audits (optional, run by hand)

These scripts drive Chrome, Firefox or WebKit with Playwright (choose with `BROWSER=chrome|firefox|webkit`, default `chrome`; install the two extra engines once with `npx playwright install firefox webkit`). WebKit here is the Safari engine on a Mac, not iPhone Safari: see `docs/browser-compatibility.md`. They are **not** part of CI (CI runs pytest and the Node unit tests), and nothing
here is needed to use or deploy the site. Run them before a release.

```bash
cd scripts/browser-audit && npm install          # playwright + axe-core, installed locally only
```

| Script | What it proves | How to run |
|---|---|---|
| `regression.js` | Navigation between Explorer / Fundamentals / Compare keeps the ticker; loading, error ("Try again") and empty states; no horizontal overflow at 320, 360, 390 and 768 px on all 8 pages; zero axe-core violations (WCAG 2.1 A/AA + best practices) in dark and light themes; the Fundamentals table shows six years on a phone with a Show all toggle; chart canvases paint; light is the first-visit default, the toggle is remembered on every page, no flash, and it works with storage blocked | `python3 -m http.server 8801` in the repo root, then `node regression.js http://127.0.0.1:8801/` |
| `privacy.js` | The portfolio "hide tickers, names, shares and dollar amounts" view exposes none of them in the visible text, element attributes, chart data, tab title, address bar, or in **OCR of real screenshots** (including one with a chart tooltip open), while risk statistics still show. A control checks that OCR can read the un-hidden screenshot | see below |
| `required-pages.js`, `offline.js` | The three assignment pages (data, filters, sorts, shortlist, Trends, manifest, service worker) and offline behaviour with the server stopped | see the header of each file |
| `screenshots.js` | Full-page JPEGs of the five main pages, desktop and phone, light and dark (`node screenshots.js http://127.0.0.1:8801/ ../../docs/visual-review`) | |
| `ocr.swift` | macOS Vision OCR used by `privacy.js` (`swiftc -O ocr.swift -o /tmp/cs-ocr`) | |

## Running the privacy audit safely

`privacy.js` **overwrites the portfolio file of the server it talks to**, so give it a throwaway home with synthetic data only:

1. create a new empty folder (`mktemp -d`) and copy a synced `data/` folder into it (or run `python3 -m personal sync SPY AAPL TSLA KO` against a mock provider);
2. start `CREDITSCOPE_HOME=<that folder> python3 -m personal serve --port 8766`;
3. `node privacy.js http://localhost:8766/ <that folder> /tmp/cs-ocr`;
4. stop the server and delete the folder (check its path first).

Never point it at your real `~/.creditscope`.
