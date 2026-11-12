// Runs ui/calc.js under Node with the vendored decimal.js. No npm packages needed.
// Usage: node run_js.js cases.json        -> JSON array of calculate() results
//        node run_js.js --shares '[...]'  -> JSON array of shareCount() results
const fs = require('fs');
const path = require('path');
globalThis.Decimal = require(path.join(__dirname, '..', 'vendor', 'decimal.js'));
const calc = require(path.join(__dirname, '..', 'calc.js'));

if (process.argv[2] === '--shares') {
  const rows = JSON.parse(process.argv[3]);
  process.stdout.write(JSON.stringify(rows.map((r) => calc.shareCount({
    balance: r[0], entry: r[1], stop: r[2], risk_pct: '1', max_position_pct: r[3],
  }))));
} else {
  const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  process.stdout.write(JSON.stringify(cases.map((c) => calc.calculate(c))));
}
