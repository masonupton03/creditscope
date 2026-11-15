# Browser compatibility

Last run: 2026-11-15, on the final code of `feature/stock-explorer`, macOS, against a local static server with simulated data.

## What was tested

The same browser audit scripts (`scripts/browser-audit/`, selected with `BROWSER=chrome|firefox|webkit`) ran in three engines:

| Engine | Version | Notes |
|---|---|---|
| Google Chrome | 157 | the installed desktop browser |
| Firefox | 159 | Playwright's Firefox build |
| WebKit | 27.2 | Playwright's WebKit build on macOS. **This is the Safari engine, not Safari.** |

| Check | Chrome | Firefox | WebKit |
|---|---|---|---|
| Browser regression (86 checks: navigation round-trips that keep the ticker, loading / error / empty states, theme default and persistence on all 8 pages, no horizontal overflow at 320 / 360 / 390 / 768 px, Fundamentals six-year phone table, charts painting pixels, axe-core in both themes) | 86 / 86 | 86 / 86 | 86 / 86 |
| Assignment pages (Today, Browse, Trends: data, filters, sorts, shortlist persistence, manifest, service worker) | 22 / 22 | 22 / 22 | 22 / 22 |
| Offline (prime online, stop the server, reopen the three assignment pages from the service-worker cache) | pass | pass | pass |
| Portfolio privacy (hidden view: page text, attributes, chart data, tab title, URL, and OCR of the browser's own screenshots) | pass | pass | pass |

## What this does not show

- **No real iPhone, iPad or Android device was used.** Headless WebKit on a Mac shares Safari's rendering and JavaScript engine but
  not its iOS shell. Do not read these results as "works on iPhone Safari". That needs a real device (checklist below).
- Touch gestures, on-screen keyboards, the iOS address-bar resize, safe-area insets and pinch zoom are not exercised.
- Playwright's Chrome-family browser is the only one tested with the **Install app** prompt flow. Installation was not tested in Firefox or WebKit.
- Only the newest version of each engine was tested. Older browsers were not.
- Accessibility (axe-core) was run in all three engines, but no screen reader (VoiceOver, NVDA, TalkBack) was used.

## Known browser-specific limitations (by design of the browsers, not bugs we can fix)

| Browser | Limitation | What CreditScope does |
|---|---|---|
| Safari on iPhone / iPad | Pages are installed through Share, then Add to Home Screen. There is no install prompt, so the site's **Install app** button never appears there | the page works as an ordinary website; install is optional |
| Safari (iOS and macOS) | Intelligent Tracking Prevention can delete a site's stored data (localStorage, caches, service-worker registration) after about 7 days without a visit, unless the site is added to the Home Screen | the theme choice and starred items may reset, and the offline copy may need one online visit to be rebuilt. Nothing is lost on the server |
| Safari on iPhone | Focusing a text field smaller than 16px makes the page zoom | fields are 16px on phones. This follows Apple's documented behaviour and has not been checked on a device |
| Firefox desktop | Does not install web apps and has no install prompt | works as a website; service worker and offline copy still work (tested) |
| All | Private / incognito windows may block or clear storage | the theme toggle, stars and the offline copy degrade quietly; the pages still work (a storage-blocked case is tested) |
| All | Offline: the first visit must be online so the service worker can store the pages | documented in the README |

## Before telling anyone "works on iPhone"

1. Open the live site on a real iPhone in Safari. Check Today, Trends (long page), Explorer search, Fundamentals (six-year table and **Show all**), and Portfolio (hide mode).
2. Tap into a search field and confirm the page does not zoom.
3. Share, then Add to Home Screen. Open it, switch to airplane mode, reopen: Today should still show data with an offline notice.
4. Switch the theme and confirm it survives a reload.
5. Repeat on one Android phone (Chrome) if available, where the Install app button should appear.
