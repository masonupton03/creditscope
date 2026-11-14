// Reads {cases:[{series, bench, period}]} from the file given as argv[2], writes the Finance.summarize results as JSON.
const fs = require('node:fs');
const F = require('../../assets/js/finance.js');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = input.cases.map(c => F.summarize(c.series, c.period, c.bench || null));
process.stdout.write(JSON.stringify(out));
