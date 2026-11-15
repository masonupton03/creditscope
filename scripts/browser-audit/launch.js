// Shared browser launcher for the audit scripts. Choose the engine with BROWSER=chrome (default) | firefox | webkit.
// "webkit" is Playwright's WebKit build, not Safari: it shares the engine, not the iOS/macOS Safari shell, so it is a smoke
// test and not proof of iPhone Safari compatibility (see docs/browser-compatibility.md).
const pw = require('playwright');
const NAME = (process.env.BROWSER || 'chrome').toLowerCase();
if (!['chrome', 'firefox', 'webkit'].includes(NAME)) throw new Error('BROWSER must be chrome, firefox or webkit');
const type = NAME === 'chrome' ? pw.chromium : pw[NAME];
const extra = NAME === 'chrome' ? { channel: 'chrome' } : {};
module.exports = {
  NAME,
  launch: (o) => type.launch(Object.assign({}, extra, o || {})),
  launchPersistentContext: (dir, o) => type.launchPersistentContext(dir, Object.assign({}, extra, o || {})),
};
