const fs = require('node:fs'); const C = require('../../assets/js/compare-calc.js');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
process.stdout.write(JSON.stringify(input.cases.map(c => { const r = C.compare(c.list, c.period, c.benchmark || null); return r.errors && r.errors.length ? { errors: r.errors } : { basis: r.basis, startDate: r.startDate, endDate: r.endDate, nReturns: r.nReturns, stats: r.stats, correlation: r.correlation, warnings: r.warnings.map(w => w.code) }; })));
