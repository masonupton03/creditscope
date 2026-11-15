const fs = require('node:fs'); const C = require('../../assets/js/fundamentals-calc.js');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
process.stdout.write(JSON.stringify(input.companies.map(c => { const r = C.analyze(c); return { years: r.years, ratios: r.ratios, cagr: r.cagr, latestFiscalYear: r.latestFiscalYear, warnings: r.warnings.map(w => w.code) }; })));
