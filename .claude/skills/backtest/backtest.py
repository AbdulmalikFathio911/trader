#!/usr/bin/env python3
"""Backtest of the trade desk's mechanical rules on exported price bars.

It replays history bar by bar and applies a fixed, mechanical version of the /trade
gates: trend from swing highs and lows, entry at a support or resistance level, stop
beyond the next level, target at the next level in the trade direction, and a minimum
reward:risk. It answers one question: did these rules, applied blindly, have an edge on
this symbol and timeframe in the past?

What it is not: it does not test the chart reading done by the model, it does not know
news, and a past result is not a promise. Read the out-of-sample part and the random
baseline before anything else.

No look-ahead: a decision made after bar t uses only bars up to t, and a swing point is
used only once the bars that confirm it have closed.

Standard library only. Prints one JSON object.
Exit codes: 0 the test ran, 2 the input is wrong.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys

REQUIRED = ("open", "high", "low", "close")
MIN_BARS = 200
MIN_TRADES_FOR_A_READING = 30


class InputError(Exception):
    pass


# ------------------------------------------------------------------ reading bars
def _number(text, name, line):
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        raise InputError(f"line {line}: {name} is not a number: {text!r}") from None


def read_bars(text):
    """Parse exported bars. Accepts the MT5 export (tab separated, <DATE> <TIME> <OPEN> ...)
    and plain CSV with a header naming date, open, high, low and close."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise InputError("the file is empty")
    delimiter = max(("\t", ";", ","), key=lambda d: lines[0].count(d))
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    header = [cell.strip().strip("<>").lower() for cell in rows[0]]
    if not all(name in header for name in REQUIRED):
        raise InputError("the first line must name the columns: date, open, high, low, close")
    index = {name: header.index(name) for name in header}
    bars = []
    for number, row in enumerate(rows[1:], start=2):
        if len(row) < len(header):
            raise InputError(f"line {number}: expected {len(header)} columns, found {len(row)}")
        bar = {name: _number(row[index[name]], name, number) for name in REQUIRED}
        stamp = row[index["date"]].strip() if "date" in index else str(number - 1)
        if "time" in index:
            stamp += " " + row[index["time"]].strip()
        bar["time"] = stamp
        if bar["high"] < max(bar["open"], bar["close"]) or bar["low"] > min(bar["open"], bar["close"]):
            raise InputError(f"line {number}: the high or the low does not contain the open and the close")
        bars.append(bar)
    if len(bars) < MIN_BARS:
        raise InputError(f"at least {MIN_BARS} bars are needed, found {len(bars)}")
    return bars


# ------------------------------------------------------------------ the rules
def swings(bars, k):
    """Indexes of swing highs and swing lows: a bar higher (lower) than the k bars on
    each side. A swing at index i is only known once bar i + k has closed."""
    highs, lows = [], []
    for i in range(k, len(bars) - k):
        window = bars[i - k:i + k + 1]
        if bars[i]["high"] == max(b["high"] for b in window) and sum(b["high"] == bars[i]["high"] for b in window) == 1:
            highs.append(i)
        if bars[i]["low"] == min(b["low"] for b in window) and sum(b["low"] == bars[i]["low"] for b in window) == 1:
            lows.append(i)
    return highs, lows


def average_range(bars, t, length=14):
    window = bars[max(0, t - length + 1):t + 1]
    return sum(bar["high"] - bar["low"] for bar in window) / len(window)


def find_setup(bars, t, swing_highs, swing_lows, k, levels, min_rr, buffer, min_stop_ranges=0.5):
    """The setup the rules give after bar t has closed, or None. Uses bars up to t only."""
    known_highs = [i for i in swing_highs if i + k <= t][-levels:]
    known_lows = [i for i in swing_lows if i + k <= t][-levels:]
    if len(known_highs) < 2 or len(known_lows) < 2:
        return None
    h_old, h_new = bars[known_highs[-2]]["high"], bars[known_highs[-1]]["high"]
    l_old, l_new = bars[known_lows[-2]]["low"], bars[known_lows[-1]]["low"]
    price = bars[t]["close"]
    resistances = sorted(bars[i]["high"] for i in known_highs)
    supports = sorted(bars[i]["low"] for i in known_lows)

    if h_new < h_old and l_new < l_old:        # gate 1: lower highs and lower lows
        above = [level for level in resistances if level > price]
        below = [level for level in supports if level < price]
        if not above or not below:
            return None
        entry = above[0]                       # gate 3: the nearest resistance above the price
        beyond = [level for level in above if level > entry]
        if not beyond:
            return None                        # gate 4: no level to put the stop beyond
        stop = beyond[0] + buffer
        target = below[-1]                     # gate 5: the next support in the trade direction
        side = "sell"
    elif h_new > h_old and l_new > l_old:      # gate 1: higher highs and higher lows
        below = [level for level in supports if level < price]
        above = [level for level in resistances if level > price]
        if not above or not below:
            return None
        entry = below[-1]
        beyond = [level for level in below if level < entry]
        if not beyond:
            return None
        stop = beyond[-1] - buffer
        target = above[0]
        side = "buy"
    else:
        return None                            # gate 1: sideways, no direction

    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk < min_stop_ranges * average_range(bars, t):
        return None                            # bars cannot resolve a stop tighter than their own range
    if risk <= 0 or reward / risk < min_rr:    # gate 6
        return None
    return {"side": side, "entry": entry, "stop": stop, "target": target, "rr": reward / risk, "made_at": t}


def state_now(bars, k=3, levels=10, min_rr=1.5, spread=0.0, min_stop_ranges=0.5):
    """What the same rules say after the last closed bar: trend, known levels, and the
    setup if there is one. A number check to put next to the chart reading, not a ticket."""
    t = len(bars) - 1
    swing_highs, swing_lows = swings(bars, k)
    known_highs = [i for i in swing_highs if i + k <= t][-levels:]
    known_lows = [i for i in swing_lows if i + k <= t][-levels:]
    trend = "unknown"
    if len(known_highs) >= 2 and len(known_lows) >= 2:
        h_old, h_new = bars[known_highs[-2]]["high"], bars[known_highs[-1]]["high"]
        l_old, l_new = bars[known_lows[-2]]["low"], bars[known_lows[-1]]["low"]
        trend = "up" if h_new > h_old and l_new > l_old else "down" if h_new < h_old and l_new < l_old else "sideways"
    price = bars[t]["close"]
    setup = find_setup(bars, t, swing_highs, swing_lows, k, levels, min_rr, spread, min_stop_ranges)
    if setup:
        setup = {key: (round(value, 6) if isinstance(value, float) else value) for key, value in setup.items()}
        setup.pop("made_at")
    return {
        "verdict": "OK",
        "mode": "now",
        "bars": len(bars),
        "last_bar": bars[t]["time"],
        "last_close": price,
        "trend": trend,
        "resistances_above": sorted(bars[i]["high"] for i in known_highs if bars[i]["high"] > price),
        "supports_below": sorted((bars[i]["low"] for i in known_lows if bars[i]["low"] < price), reverse=True),
        "setup": setup,
        "settings": {"swing": k, "levels": levels, "min_reward_risk": min_rr, "spread": spread,
                     "min_stop_in_average_ranges": min_stop_ranges},
        "errors": [],
    }


def exit_of(bars, start, side, stop, target, rr):
    """Walk forward from bar `start` (the bar after the fill) until the stop or the target.
    When one bar touches both, the stop is counted: the cautious reading.
    Returns (result in R before costs, index of the exit bar), or (None, last index) if still open."""
    for i in range(start, len(bars)):
        bar = bars[i]
        if side == "sell":
            if bar["high"] >= stop:
                return -1.0, i
            if bar["low"] <= target:
                return rr, i
        else:
            if bar["low"] <= stop:
                return -1.0, i
            if bar["high"] >= target:
                return rr, i
    return None, len(bars) - 1


def run(bars, k=3, levels=10, min_rr=1.5, expiry=24, spread=0.0, min_stop_ranges=0.5):
    """Replay the bars. One order or one position at a time. Returns the closed trades."""
    swing_highs, swing_lows = swings(bars, k)
    trades = []
    t = 2 * k
    last = len(bars) - 1
    while t < last:
        setup = find_setup(bars, t, swing_highs, swing_lows, k, levels, min_rr, spread, min_stop_ranges)
        if not setup:
            t += 1
            continue
        side, entry, stop, target = setup["side"], setup["entry"], setup["stop"], setup["target"]
        filled_at = None
        for i in range(t + 1, min(t + 1 + expiry, len(bars))):     # the pending order waits
            bar = bars[i]
            if (side == "sell" and bar["high"] >= entry) or (side == "buy" and bar["low"] <= entry):
                filled_at = i
                break
            if (side == "sell" and bar["close"] <= target) or (side == "buy" and bar["close"] >= target):
                break                                              # the move happened without us
        if filled_at is None:
            t += 1
            continue
        bar = bars[filled_at]
        hit_stop_same_bar = (side == "sell" and bar["high"] >= stop) or (side == "buy" and bar["low"] <= stop)
        if hit_stop_same_bar:
            result, exit_at = -1.0, filled_at
        else:
            result, exit_at = exit_of(bars, filled_at + 1, side, stop, target, setup["rr"])
        if result is None:
            break                                                  # still open when the data ends
        cost = spread / abs(entry - stop)
        trades.append({
            "made_at": setup["made_at"], "filled_at": filled_at, "exit_at": exit_at,
            "time": bars[filled_at]["time"], "side": side,
            "entry": entry, "stop": stop, "target": target,
            "rr": setup["rr"], "result_r": result - cost,
        })
        t = exit_at + 1
    return trades


# ------------------------------------------------------------------ measuring
def measure(trades):
    count = len(trades)
    if not count:
        return {"trades": 0}
    results = [trade["result_r"] for trade in trades]
    wins = sum(1 for r in results if r > 0)
    average_rr = sum(trade["rr"] for trade in trades) / count
    running = peak = drawdown = 0.0
    streak = longest = 0
    for r in results:
        running += r
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
        streak = streak + 1 if r <= 0 else 0
        longest = max(longest, streak)
    return {
        "trades": count,
        "wins": wins,
        "win_rate_pct": round(wins / count * 100, 1),
        "average_reward_risk": round(average_rr, 2),
        "breakeven_win_rate_pct": round(100 / (1 + average_rr), 1),
        "expectancy_r": round(sum(results) / count, 3),
        "total_r": round(sum(results), 2),
        "max_drawdown_r": round(drawdown, 2),
        "longest_losing_streak": longest,
    }


def random_baseline(bars, trades, runs, seed, spread):
    """The same trades with the direction chosen by a coin: entered at the close of the
    same fill bar, with the same stop distance and the same reward:risk. Shows what the
    rules add over chance."""
    if not trades:
        return None
    rng = random.Random(seed)
    expectancies = []
    for _ in range(runs):
        total = 0.0
        counted = 0
        for trade in trades:
            distance = abs(trade["entry"] - trade["stop"])
            side = rng.choice(("buy", "sell"))
            entry = bars[trade["filled_at"]]["close"]          # a price that could really be traded
            stop = entry - distance if side == "buy" else entry + distance
            target = entry + distance * trade["rr"] if side == "buy" else entry - distance * trade["rr"]
            result, _ = exit_of(bars, trade["filled_at"] + 1, side, stop, target, trade["rr"])
            if result is None:
                continue
            total += result - spread / distance
            counted += 1
        if counted:
            expectancies.append(total / counted)
    if not expectancies:
        return None
    expectancies.sort()
    strategy = sum(trade["result_r"] for trade in trades) / len(trades)
    at_least = sum(1 for e in expectancies if e >= strategy)
    return {
        "runs": len(expectancies),
        "mean_expectancy_r": round(sum(expectancies) / len(expectancies), 3),
        "p5_expectancy_r": round(expectancies[int(0.05 * (len(expectancies) - 1))], 3),
        "p95_expectancy_r": round(expectancies[int(0.95 * (len(expectancies) - 1))], 3),
        "share_of_random_runs_at_least_as_good_pct": round(at_least / len(expectancies) * 100, 1),
    }


def reading_of(out_of_sample, baseline):
    """A plain label for the result. It describes the sample; it promises nothing."""
    if out_of_sample.get("trades", 0) < MIN_TRADES_FOR_A_READING:
        return "TOO_FEW_TRADES"
    if out_of_sample["expectancy_r"] <= 0:
        return "NO_EDGE_SHOWN"
    if baseline is None or baseline["share_of_random_runs_at_least_as_good_pct"] >= 5:
        return "NOT_BETTER_THAN_CHANCE"
    return "POSITIVE_IN_THIS_SAMPLE"


def backtest(bars, k=3, levels=10, min_rr=1.5, expiry=24, spread=0.0, split=0.7, runs=200, seed=7,
             min_stop_ranges=0.5):
    trades = run(bars, k=k, levels=levels, min_rr=min_rr, expiry=expiry, spread=spread,
                 min_stop_ranges=min_stop_ranges)
    cut = int(len(bars) * split)
    inside = [trade for trade in trades if trade["filled_at"] < cut]
    outside = [trade for trade in trades if trade["filled_at"] >= cut]
    out_of_sample = measure(outside)
    baseline = random_baseline(bars, outside, runs, seed, spread)
    return {
        "verdict": "OK",
        "bars": len(bars),
        "from": bars[0]["time"],
        "to": bars[-1]["time"],
        "settings": {"swing": k, "levels": levels, "min_reward_risk": min_rr, "expiry_bars": expiry,
                     "spread": spread, "split": split, "random_runs": runs, "seed": seed,
                     "min_stop_in_average_ranges": min_stop_ranges},
        "all": measure(trades),
        "in_sample": measure(inside),
        "out_of_sample": out_of_sample,
        "random_direction_baseline_out_of_sample": baseline,
        "reading": reading_of(out_of_sample, baseline),
        "trades": [{key: (round(value, 6) if isinstance(value, float) else value) for key, value in trade.items()}
                   for trade in trades],
        "errors": [],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backtest the trade desk's mechanical rules. Prints JSON.")
    parser.add_argument("--csv", required=True, help="exported bars: date, open, high, low, close")
    parser.add_argument("--swing", type=int, default=3, help="bars on each side that define a swing point")
    parser.add_argument("--levels", type=int, default=10, help="how many recent swing levels to keep")
    parser.add_argument("--min-rr", type=float, default=1.5)
    parser.add_argument("--expiry", type=int, default=24, help="bars a pending order waits")
    parser.add_argument("--spread", type=float, default=0.0, help="cost per trade, in price units")
    parser.add_argument("--split", type=float, default=0.7, help="share of the bars used as in-sample")
    parser.add_argument("--runs", type=int, default=200, help="random-direction runs for the baseline")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--min-stop-ranges", type=float, default=0.5,
                        help="skip setups whose stop is closer than this many average bar ranges")
    parser.add_argument("--no-trades", action="store_true", help="leave the trade list out of the output")
    parser.add_argument("--now", action="store_true",
                        help="no test: print what the rules say after the last bar of the file")
    args = parser.parse_args(argv)
    try:
        if not (1 <= args.swing <= 20 and args.levels >= 2 and args.min_rr > 0 and args.expiry >= 1
                and args.spread >= 0 and 0.1 <= args.split <= 0.9 and args.runs >= 1
                and args.min_stop_ranges >= 0):
            raise InputError("a setting is out of range")
        with open(args.csv, encoding="utf-8-sig") as handle:
            bars = read_bars(handle.read())
        if args.now:
            print(json.dumps(state_now(bars, k=args.swing, levels=args.levels, min_rr=args.min_rr,
                                       spread=args.spread, min_stop_ranges=args.min_stop_ranges), indent=2))
            return 0
        result = backtest(bars, k=args.swing, levels=args.levels, min_rr=args.min_rr, expiry=args.expiry,
                          spread=args.spread, split=args.split, runs=args.runs, seed=args.seed,
                          min_stop_ranges=args.min_stop_ranges)
    except (InputError, OSError) as problem:
        print(json.dumps({"verdict": "INVALID", "errors": [str(problem)]}, indent=2))
        return 2
    if args.no_trades:
        result.pop("trades")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
