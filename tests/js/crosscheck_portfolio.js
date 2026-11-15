// Reads {cases:[{portfolio, series}]} from the file in argv[2]; prints Portfolio.analyze results (or its errors) as JSON.
const fs = require('node:fs');
const P = require('../../assets/js/portfolio.js');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
process.stdout.write(JSON.stringify(input.cases.map(c => {
  const r = P.analyze(c.portfolio, c.series);
  return r.errors && r.errors.length ? { errors: r.errors } : r;
})));
