#!/usr/bin/env python3
"""Journal helper for the trade desk.

Reads and writes journal.csv only. Prints one JSON object. It never touches
the network and never places, modifies or closes an order.

    journal.py add    ...   append a ticket row and print its id
    journal.py result ...   record the outcome of a ticket, then print stats
    journal.py stats        print the statistics
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

COLUMNS = [
    "id", "time", "symbol", "side", "type", "entry", "stop", "target", "lots",
    "risk", "reward_risk", "scenario_estimate", "verdict", "result", "pnl",
]
RESULTS = ("win", "loss", "cancelled")
MIN_SAMPLE = 30
DEFAULT_FILE = Path(__file__).resolve().parents[3] / "journal.csv"


def fail(message):
    print(json.dumps({"ok": False, "error": message}, indent=2))
    sys.exit(2)


def number(text, name):
    try:
        value = Decimal(text)
    except InvalidOperation:
        fail(f"{name} is not a number: {text!r}")
    if not value.is_finite():
        fail(f"{name} is not a finite number: {text!r}")
    return value


def read_rows(path):
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            fail(f"{path.name} has unexpected columns: {reader.fieldnames}")
        return list(reader)


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rounded(value, places="0.01"):
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def stats(rows):
    closed = [r for r in rows if r["verdict"] == "OK" and r["result"] in ("win", "loss")]
    wins = [r for r in closed if r["result"] == "win"]
    cancelled = [r for r in rows if r["result"] == "cancelled"]
    open_tickets = [r for r in rows if r["verdict"] == "OK" and not r["result"]]
    out = {
        "closed_trades": len(closed),
        "wins": len(wins),
        "losses": len(closed) - len(wins),
        "cancelled": len(cancelled),
        "open_tickets": len(open_tickets),
        "no_trade_rows": sum(1 for r in rows if r["verdict"] != "OK"),
        "win_rate_pct": None,
        "avg_reward_risk": None,
        "breakeven_win_rate_pct": None,
        "total_pnl": "0.00",
        "sample_too_small": len(closed) < MIN_SAMPLE,
        "min_sample": MIN_SAMPLE,
    }
    if closed:
        out["win_rate_pct"] = rounded(Decimal(len(wins)) / len(closed) * 100, "0.1")
        out["total_pnl"] = rounded(sum(Decimal(r["pnl"] or "0") for r in closed))
        ratios = [Decimal(r["reward_risk"]) for r in closed if r["reward_risk"]]
        if ratios:
            average = sum(ratios) / len(ratios)
            out["avg_reward_risk"] = rounded(average)
            out["breakeven_win_rate_pct"] = rounded(Decimal(100) / (1 + average), "0.1")
    return out


def cmd_add(args, path):
    rows = read_rows(path)
    when = datetime.strptime(args.time, "%Y-%m-%d %H:%M") if args.time else datetime.now()
    next_id = max((int(r["id"]) for r in rows), default=0) + 1
    for name in ("entry", "stop", "target", "lots", "risk", "reward_risk", "scenario_estimate"):
        value = getattr(args, name)
        if value:
            number(value, f"--{name.replace('_', '-')}")
    row = {
        "id": str(next_id),
        "time": when.strftime("%Y-%m-%d %H:%M"),
        "symbol": args.symbol,
        "side": args.side or "",
        "type": args.type or "",
        "entry": args.entry or "",
        "stop": args.stop or "",
        "target": args.target or "",
        "lots": args.lots or "",
        "risk": args.risk or "",
        "reward_risk": args.reward_risk or "",
        "scenario_estimate": args.scenario_estimate or "",
        "verdict": args.verdict,
        "result": "",
        "pnl": "",
    }
    rows.append(row)
    write_rows(path, rows)
    ticket_file = f"tickets/{when.strftime('%Y-%m-%d_%H%M')}_{args.symbol}.md"
    print(json.dumps({"ok": True, "id": next_id, "time": row["time"],
                      "ticket_file": ticket_file, "row": row}, indent=2))


def cmd_result(args, path):
    rows = read_rows(path)
    row = next((r for r in rows if r["id"] == str(args.id)), None)
    if row is None:
        fail(f"no ticket with id {args.id}")
    if row["verdict"] != "OK":
        fail(f"ticket {args.id} was a {row['verdict']}: there is no order to record")
    warnings = []
    if row["result"]:
        warnings.append(f"ticket {args.id} already had result {row['result']} "
                        f"(pnl {row['pnl']}); it was replaced")
    if args.result == "cancelled":
        pnl = number(args.pnl, "--pnl") if args.pnl is not None else Decimal(0)
        if pnl != 0:
            fail("a cancelled ticket has no profit or loss; use win or loss instead")
    else:
        if args.pnl is None:
            fail("--pnl is required for win and loss")
        pnl = number(args.pnl, "--pnl")
        if args.result == "win" and pnl <= 0:
            fail(f"a win needs a profit above zero, got {args.pnl}")
        if args.result == "loss" and pnl == 0:
            fail("a loss needs an amount other than zero")
        if args.result == "loss" and pnl > 0:
            pnl = -pnl
            warnings.append(f"the loss was typed as {args.pnl}; it is stored as {rounded(pnl)}")
    row["result"] = args.result
    row["pnl"] = rounded(pnl)
    write_rows(path, rows)
    print(json.dumps({"ok": True, "row": row, "warnings": warnings,
                      "stats": stats(rows)}, indent=2))


def cmd_stats(args, path):
    print(json.dumps({"ok": True, "stats": stats(read_rows(path))}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trade desk journal. Prints JSON.")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="append a ticket row")
    add.add_argument("--symbol", required=True)
    add.add_argument("--verdict", required=True, choices=("OK", "NO_TRADE"))
    add.add_argument("--side", choices=("buy", "sell"))
    add.add_argument("--type")
    for flag in ("--entry", "--stop", "--target", "--lots", "--risk",
                 "--reward-risk", "--scenario-estimate"):
        add.add_argument(flag)
    add.add_argument("--time", help="YYYY-MM-DD HH:MM (default: now)")
    add.set_defaults(func=cmd_add)

    res = sub.add_parser("result", help="record the outcome of a ticket")
    res.add_argument("--id", required=True, type=int)
    res.add_argument("--result", required=True, choices=RESULTS)
    res.add_argument("--pnl", help="profit as a positive number, loss as a negative one")
    res.set_defaults(func=cmd_result)

    sub.add_parser("stats", help="print statistics").set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    args.func(args, args.file)


if __name__ == "__main__":
    main()
