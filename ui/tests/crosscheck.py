#!/usr/bin/env python3
"""Cross-check ui/calc.js against calc.py, and its share count against position_sizer.py.

The page must give the same numbers as the /trade skill. This feeds the same inputs to
both calculators and compares every output field (error and warning codes included).
Needs `node`; no npm packages. Standard library only.

Run from the repository root:
    python3 ui/tests/crosscheck.py            # 400 random cases plus the fixed ones
tests/test_ui.py runs a smaller sample as part of the normal test suite.
"""
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CALC = REPO / ".claude" / "skills" / "mt5-lot-calculator" / "calc.py"
SIZER = REPO / ".claude" / "skills" / "position-sizer" / "scripts" / "position_sizer.py"
RUN_JS = HERE / "run_js.js"

SYMBOLS = {
    'EURUSD': dict(contract_size='100000', digits=5, base=1.10, span=0.02, mode='forex'),
    'XAUUSD': dict(contract_size='100', digits=2, base=3900, span=150, mode='cfd_leverage'),
    'USDJPY': dict(contract_size='100000', digits=3, base=155, span=3, mode='forex', q2a='0.00645'),
    'F': dict(contract_size='1', digits=2, base=12, span=2, mode='stocks', min_lot='1', lot_step='1'),
    'SPOT': dict(contract_size='10', digits=1, base=75, span=10, mode='cfd'),
}

FIXED = [
    dict(symbol='EURUSD', side='sell', entry='1.1098', stop='1.1108', target='1.1078', balance='102',
         free_margin='102', leverage='15', contract_size='100000', digits=5, current_price='1.1057'),
    dict(symbol='XAUUSD', side='sell', entry='3987', stop='4003', balance='102', contract_size='100', digits=2),
    dict(symbol='XAUUSD', side='sell', entry='3900', stop='3930', target='3850', balance='102',
         free_margin='26.73', leverage='20', calc_mode='cfd_leverage', contract_size='100', digits=2),
    dict(symbol='EURUSD', side='sell', entry='1.1100', stop='1.1110', target='1.1080', balance='102',
         free_margin='26.73', leverage='15', contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='sell', entry='1.1100', stop='1.1110', target='1.1080', balance='102',
         free_margin='102', leverage='15', contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='buy', entry='1.1050', lots='0.01', rr='2', balance='102', leverage='15',
         contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='buy', entry='1.1050', stop='1.1060', contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='buy', entry='1.105012', stop='1.1040', balance='102', contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='sell', entry='1.1050', contract_size='100000', digits=5),
    dict(symbol='F', side='buy', entry='11.93', stop='11.42', target='12.95', lots='2', balance='102',
         free_margin='26.73', contract_size='1', min_lot='1', lot_step='1', digits=2, calc_mode='stocks',
         current_price='11.93'),
    dict(symbol='EURUSD', side='buy', entry='1.1050', lots='0.015', balance='102', contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='buy', entry='1.1050', lots='0.01', stop='1.1000', contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='buy', entry='1.1050', lots='5', rr='2', balance='10', contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='buy', entry='-1', stop='1.1', balance='100', contract_size='100000', digits=5),
    dict(symbol='EURUSD', side='buy', entry='1.1050', stop='1.1040', target='1.1070', rr='3', balance='5000',
         free_margin='5000', leverage='30', stops_level='150', current_price='1.1049', contract_size='100000', digits=5),
]


def price(rng, base, span, digits):
    return f'{base + rng.uniform(-span, span):.{rng.choice([digits, digits, max(digits - 1, 0)])}f}'


def random_case(rng):
    name = rng.choice(list(SYMBOLS))
    spec = SYMBOLS[name]
    digits = spec['digits']
    side = rng.choice(['buy', 'sell'])
    entry = float(price(rng, spec['base'], spec['span'], digits))
    step = spec['span'] * rng.choice([0.002, 0.01, 0.05, 0.3])
    sign = 1 if side == 'buy' else -1
    wrong = rng.random() < 0.06
    case = dict(symbol=name, side=side, entry=f'{entry:.{digits}f}', contract_size=spec['contract_size'],
                digits=digits, calc_mode=spec['mode'])
    if 'q2a' in spec:
        case['quote_to_account'] = spec['q2a']
    if 'min_lot' in spec:
        case['min_lot'] = spec['min_lot']
        case['lot_step'] = spec['lot_step']
    style = rng.random()
    stop_value = entry - sign * step * (-1 if wrong else 1)
    if style < 0.7:
        case['stop'] = f'{stop_value:.{digits}f}'
    elif style < 0.85:
        case['lots'] = rng.choice(['0.01', '0.02', '0.1', '1', '3', '0.005'])
    else:
        case['stop'] = f'{stop_value:.{digits}f}'
        case['lots'] = rng.choice(['0.01', '0.05', '1', '2'])
    goal = rng.random()
    if goal < 0.55:
        case['target'] = f'{entry + sign * step * rng.choice([0.5, 1.5, 2, 3.3]):.{digits}f}'
    elif goal < 0.8:
        case['rr'] = rng.choice(['1', '1.5', '2', '2.75'])
    if rng.random() < 0.92:
        case['balance'] = rng.choice(['102', '100', '1000', '3000', '25000.50'])
    if rng.random() < 0.7:
        case['free_margin'] = rng.choice(['26.73', '102', '950', '3000', '0.5'])
    if rng.random() < 0.8:
        case['leverage'] = rng.choice(['15', '20', '30', '100', '1'])
    if rng.random() < 0.4:
        case['risk_pct'] = rng.choice(['0.5', '1', '2', '1.25'])
    if rng.random() < 0.3:
        case['stops_level'] = rng.choice(['0', '10', '50', '300'])
    if rng.random() < 0.7:
        case['current_price'] = rng.choice([case['entry'], price(rng, spec['base'], spec['span'], digits)])
    return case


def run_python(case):
    flags = []
    for key, value in case.items():
        flags += ['--' + key.replace('_', '-'), str(value)]
    proc = subprocess.run([sys.executable, str(CALC), *flags], capture_output=True, text=True)
    return json.loads(proc.stdout)


def compare(random_cases=400, seed=20261113):
    """Return (number of cases, list of mismatch descriptions)."""
    rng = random.Random(seed)
    cases = FIXED + [random_case(rng) for _ in range(random_cases)]
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        cases_file = Path(tmp) / "cases.json"
        cases_file.write_text(json.dumps(cases))
        node = subprocess.run(["node", str(RUN_JS), str(cases_file)], capture_output=True, text=True)
        if node.returncode:
            return len(cases), ["node failed: " + node.stderr.strip()]
        js_results = json.loads(node.stdout)
        for index, (case, js) in enumerate(zip(cases, js_results)):
            py = run_python(case)
            for key in sorted(set(py) | set(js)):
                if key in ("errors", "warnings"):
                    a = [item["code"] for item in py.get(key, [])]
                    b = [item["code"] for item in js.get(key, [])]
                else:
                    a, b = py.get(key, "<absent>"), js.get(key, "<absent>")
                if a != b:
                    problems.append(f"case {index} {case}: {key}: calc.py={a!r} calc.js={b!r}")
    return len(cases), problems


SHARE_ROWS = [("102", "11.93", "11.42", "25"), ("102", "15.75", "14.73", "25"), ("102", "13.42", "12.40", "25"),
              ("102", "22.20", "21.18", "25"), ("5000", "155", "148.50", "10"), ("100000", "155", "148.50", "10"),
              ("3000", "42.10", "40.05", "25"), ("800", "9.87", "9.31", "50")]


def compare_shares():
    """Return a list of mismatches between shareCount() and position_sizer.py."""
    problems = []
    node = subprocess.run(["node", str(RUN_JS), "--shares", json.dumps(SHARE_ROWS)], capture_output=True, text=True)
    if node.returncode:
        return ["node failed: " + node.stderr.strip()]
    for row, js in zip(SHARE_ROWS, json.loads(node.stdout)):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(SIZER), "--account-size", row[0], "--entry", row[1],
                            "--stop", row[2], "--risk-pct", "1.0", "--max-position-pct", row[3],
                            "--output-dir", tmp], capture_output=True, text=True)
            reports = list(Path(tmp).glob("*.json"))
            if not reports:
                problems.append(f"{row}: position_sizer.py wrote no report")
                continue
            expected = str(json.loads(reports[0].read_text())["final_recommended_shares"])
        if js is None or expected != js["shares"]:
            problems.append(f"{row}: position_sizer.py={expected} calc.js={js}")
    return problems


def main():
    count, problems = compare()
    share_problems = compare_shares()
    for line in (problems + share_problems)[:12]:
        print(line)
    print(f"cases: {count}  mismatches: {len(problems)}")
    print(f"share-count rows: {len(SHARE_ROWS)}  mismatches: {len(share_problems)}")
    sys.exit(1 if problems or share_problems else 0)


if __name__ == "__main__":
    main()
