"""Tests for .claude/skills/backtest/backtest.py.

Run from the repository root:
    python3 -m unittest discover -s tests -v
"""

import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "skills" / "backtest" / "backtest.py"

spec = importlib.util.spec_from_file_location("backtest", SCRIPT)
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)


def synthetic(count=3000, seed=11, drift=0.0, ticks=12):
    """Bars from a seeded random walk, built tick by tick so the high and the low are real
    points on the path. (Wicks drawn outside the path would snap back by construction and
    hand every limit order a false edge.)"""
    rng = random.Random(seed)
    price = 1.1000
    step = 0.0008 / ticks ** 0.5
    bars = []
    for i in range(count):
        open_ = high = low = price
        for _ in range(ticks):
            price += rng.gauss(drift / ticks, step)
            high = max(high, price)
            low = min(low, price)
        bars.append({"time": f"bar {i}", "open": open_, "high": high, "low": low, "close": price})
    return bars


def bouncing(count=9000, seed=5, strength=0.35, ticks=12, k=3):
    """A random walk with one pattern put in on purpose: when the price reaches the level the
    rules would trade, it is pushed toward the rules' target for a while. Used to check that
    the backtest finds an edge that really is in the data."""
    rng = random.Random(seed)
    price = 1.1000
    step = 0.0008 / ticks ** 0.5
    bars, highs, lows = [], [], []
    setup, push, push_left = None, 0.0, 0
    for i in range(count):
        open_ = high = low = price
        for _ in range(ticks):
            price += rng.gauss(push if push_left else 0.0, step)
            push_left = max(0, push_left - 1)
            high = max(high, price)
            low = min(low, price)
            if setup and not push_left:
                touched = price <= setup["entry"] if setup["side"] == "buy" else price >= setup["entry"]
                if touched:
                    push = strength * step * (1 if setup["side"] == "buy" else -1)
                    push_left = 20 * ticks
                    setup = None
        bars.append({"time": f"bar {i}", "open": open_, "high": high, "low": low, "close": price})
        j = i - k
        if j >= k:
            window = bars[j - k:j + k + 1]
            if bars[j]["high"] == max(b["high"] for b in window) and sum(b["high"] == bars[j]["high"] for b in window) == 1:
                highs.append(j)
            if bars[j]["low"] == min(b["low"] for b in window) and sum(b["low"] == bars[j]["low"] for b in window) == 1:
                lows.append(j)
        if not push_left and i >= 2 * k:
            setup = bt.find_setup(bars, i, highs, lows, k, 10, 1.5, 0.0)
    return bars


def as_mt5_export(bars):
    lines = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"]
    for i, bar in enumerate(bars):
        lines.append(f"2026.01.{1 + i % 28:02d}\t{i % 24:02d}:00:00\t{bar['open']:.5f}\t{bar['high']:.5f}\t"
                     f"{bar['low']:.5f}\t{bar['close']:.5f}\t100\t0\t2")
    return "\n".join(lines) + "\n"


class TestReadingBars(unittest.TestCase):
    def test_reads_the_mt5_export(self):
        bars = bt.read_bars(as_mt5_export(synthetic(250)))
        self.assertEqual(len(bars), 250)
        self.assertEqual(bars[0]["time"], "2026.01.01 00:00:00")
        self.assertAlmostEqual(bars[0]["open"], 1.1, places=5)

    def test_reads_plain_csv(self):
        rows = ["date,open,high,low,close"] + [f"d{i},1.0,1.2,0.9,1.1" for i in range(200)]
        self.assertEqual(len(bt.read_bars("\n".join(rows))), 200)

    def test_rejects_bad_input(self):
        with self.assertRaises(bt.InputError):
            bt.read_bars("")
        with self.assertRaises(bt.InputError):
            bt.read_bars("a,b,c\n1,2,3\n")
        with self.assertRaises(bt.InputError):                       # too few bars
            bt.read_bars("date,open,high,low,close\n" + "d,1.0,1.2,0.9,1.1\n" * 50)
        with self.assertRaises(bt.InputError):                       # high below the close
            bt.read_bars("date,open,high,low,close\n" + "d,1.0,1.05,0.9,1.1\n" * 200)
        with self.assertRaises(bt.InputError):
            bt.read_bars("date,open,high,low,close\n" + "d,x,1.2,0.9,1.1\n" * 200)


class TestRules(unittest.TestCase):
    def test_exit_counts_the_stop_when_one_bar_touches_both(self):
        bars = [{"open": 1.0, "high": 1.05, "low": 0.90, "close": 1.0, "time": "t"}]
        self.assertEqual(bt.exit_of(bars, 0, "sell", 1.04, 0.92, 2.0), (-1.0, 0))
        self.assertEqual(bt.exit_of(bars, 0, "buy", 0.92, 1.04, 2.0), (-1.0, 0))

    def test_exit_takes_the_target(self):
        bars = [{"open": 1.0, "high": 1.01, "low": 0.99, "close": 1.0, "time": "a"},
                {"open": 1.0, "high": 1.00, "low": 0.90, "close": 0.91, "time": "b"}]
        self.assertEqual(bt.exit_of(bars, 0, "sell", 1.04, 0.92, 2.0), (2.0, 1))
        self.assertEqual(bt.exit_of(bars[:1], 0, "sell", 1.04, 0.92, 2.0), (None, 0))

    def test_every_trade_obeys_the_gates(self):
        bars = synthetic()
        trades = bt.run(bars, min_rr=1.5)
        self.assertGreater(len(trades), 20)
        for trade in trades:
            self.assertGreaterEqual(trade["rr"], 1.5)
            self.assertLess(trade["made_at"], trade["filled_at"])
            self.assertLessEqual(trade["filled_at"], trade["exit_at"])
            if trade["side"] == "sell":
                self.assertGreater(trade["stop"], trade["entry"])
                self.assertLess(trade["target"], trade["entry"])
            else:
                self.assertLess(trade["stop"], trade["entry"])
                self.assertGreater(trade["target"], trade["entry"])
            self.assertTrue(trade["result_r"] == -1.0 or abs(trade["result_r"] - trade["rr"]) < 1e-9)

    def test_one_position_at_a_time(self):
        trades = bt.run(synthetic())
        for earlier, later in zip(trades, trades[1:]):
            self.assertGreater(later["made_at"], earlier["exit_at"])

    def test_no_look_ahead(self):
        """Trades closed early must not change when later bars are added."""
        bars = synthetic(3000)
        short = bt.run(bars[:1500])
        full = bt.run(bars)
        settled = [t for t in short if t["exit_at"] < 1400]
        self.assertGreater(len(settled), 5)
        self.assertEqual(settled, full[:len(settled)])

    def test_costs_reduce_every_result(self):
        """Every trade pays the spread, as a share of its own risk."""
        bars = synthetic()
        for trade in bt.run(bars):
            self.assertIn(round(trade["result_r"], 9), (-1.0, round(trade["rr"], 9)))
        paid = bt.run(bars, spread=0.0001)
        self.assertGreater(len(paid), 0)
        for trade in paid:
            cost = 0.0001 / abs(trade["entry"] - trade["stop"])
            self.assertGreater(cost, 0)
            self.assertIn(round(trade["result_r"], 9), (round(-1.0 - cost, 9), round(trade["rr"] - cost, 9)))


class TestNow(unittest.TestCase):
    def test_now_matches_the_replay(self):
        """--now must say exactly what the replay would decide on the same last bar."""
        bars = synthetic(1500)
        seen = 0
        for cut in range(400, 1500, 37):
            part = bars[:cut]
            highs, lows = bt.swings(part, 3)
            expected = bt.find_setup(part, cut - 1, highs, lows, 3, 10, 1.5, 0.0)
            got = bt.state_now(part)
            self.assertEqual(got["last_bar"], part[-1]["time"])
            self.assertIn(got["trend"], ("up", "down", "sideways"))
            if expected is None:
                self.assertIsNone(got["setup"])
            else:
                seen += 1
                self.assertEqual(got["setup"]["side"], expected["side"])
                self.assertAlmostEqual(got["setup"]["entry"], expected["entry"], places=6)
                self.assertEqual(got["trend"], "up" if expected["side"] == "buy" else "down")
            for level in got["resistances_above"]:
                self.assertGreater(level, got["last_close"])
            for level in got["supports_below"]:
                self.assertLess(level, got["last_close"])
        self.assertGreater(seen, 0)


class TestMeasuring(unittest.TestCase):
    def test_measures(self):
        trades = [{"rr": 2.0, "result_r": 2.0}, {"rr": 2.0, "result_r": -1.0}, {"rr": 2.0, "result_r": -1.0},
                  {"rr": 2.0, "result_r": 2.0}]
        m = bt.measure(trades)
        self.assertEqual((m["trades"], m["wins"], m["win_rate_pct"]), (4, 2, 50.0))
        self.assertEqual(m["breakeven_win_rate_pct"], 33.3)
        self.assertEqual(m["expectancy_r"], 0.5)
        self.assertEqual(m["total_r"], 2.0)
        self.assertEqual(m["max_drawdown_r"], 2.0)
        self.assertEqual(m["longest_losing_streak"], 2)
        self.assertEqual(bt.measure([]), {"trades": 0})

    def test_reading_labels(self):
        self.assertEqual(bt.reading_of({"trades": 5, "expectancy_r": 1.0}, None), "TOO_FEW_TRADES")
        self.assertEqual(bt.reading_of({"trades": 40, "expectancy_r": -0.1}, None), "NO_EDGE_SHOWN")
        chance = {"share_of_random_runs_at_least_as_good_pct": 30.0}
        self.assertEqual(bt.reading_of({"trades": 40, "expectancy_r": 0.2}, chance), "NOT_BETTER_THAN_CHANCE")
        rare = {"share_of_random_runs_at_least_as_good_pct": 1.0}
        self.assertEqual(bt.reading_of({"trades": 40, "expectancy_r": 0.2}, rare), "POSITIVE_IN_THIS_SAMPLE")

    def test_a_random_walk_is_not_called_an_edge(self):
        """On noise the rules must not be reported as a proven edge."""
        for seed in (11, 12, 13):
            result = bt.backtest(synthetic(4000, seed=seed))
            self.assertNotEqual(result["reading"], "POSITIVE_IN_THIS_SAMPLE", seed)
            self.assertEqual(result["all"]["trades"], result["in_sample"].get("trades", 0) + result["out_of_sample"].get("trades", 0))

    def test_coin_flip_baseline_is_near_zero_on_noise(self):
        """A coin flip on a random walk must not look profitable: that would mean the test is biased."""
        means = []
        for seed in (11, 12, 13, 14, 15):
            result = bt.backtest(synthetic(4000, seed=seed))
            baseline = result["random_direction_baseline_out_of_sample"]
            if baseline:
                means.append(baseline["mean_expectancy_r"])
        self.assertGreaterEqual(len(means), 3)
        self.assertLess(abs(sum(means) / len(means)), 0.25, means)

    def test_an_edge_that_is_in_the_data_is_found(self):
        """The other side of the check: with the pattern put in, the result must be positive."""
        readings = []
        for seed in range(1, 7):
            result = bt.backtest(bouncing(9000, seed=seed, strength=0.25), runs=60)
            self.assertGreater(result["out_of_sample"]["expectancy_r"], 0.3)
            readings.append(result["reading"])
        self.assertNotIn("NO_EDGE_SHOWN", readings)
        self.assertGreaterEqual(readings.count("POSITIVE_IN_THIS_SAMPLE"), 2, readings)

    def test_noise_is_rarely_called_an_edge(self):
        """On random walks the label POSITIVE_IN_THIS_SAMPLE must stay rare (about 1 in 20 by design)."""
        positives = sum(bt.backtest(synthetic(9000, seed=seed), runs=60)["reading"] == "POSITIVE_IN_THIS_SAMPLE"
                        for seed in range(100, 120))
        self.assertLessEqual(positives, 3)

    def test_stop_is_never_tighter_than_the_bars_resolve(self):
        bars = synthetic()
        for trade in bt.run(bars, min_stop_ranges=0.5):
            self.assertGreaterEqual(abs(trade["entry"] - trade["stop"]), 0.5 * bt.average_range(bars, trade["made_at"]) - 1e-12)

    def test_same_seed_same_baseline(self):
        bars = synthetic()
        self.assertEqual(bt.backtest(bars)["random_direction_baseline_out_of_sample"],
                         bt.backtest(bars)["random_direction_baseline_out_of_sample"])


class TestCommandLine(unittest.TestCase):
    def run_cli(self, text, *flags):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            path.write_text(text, encoding="utf-8")
            proc = subprocess.run([sys.executable, str(SCRIPT), "--csv", str(path), *flags], capture_output=True, text=True)
        return proc.returncode, json.loads(proc.stdout)

    def test_runs_on_an_export(self):
        code, out = self.run_cli(as_mt5_export(synthetic(1500)), "--no-trades")
        self.assertEqual(code, 0)
        self.assertEqual(out["verdict"], "OK")
        self.assertEqual(out["bars"], 1500)
        self.assertNotIn("trades", out)
        self.assertIn(out["reading"], ("TOO_FEW_TRADES", "NO_EDGE_SHOWN", "NOT_BETTER_THAN_CHANCE", "POSITIVE_IN_THIS_SAMPLE"))

    def test_bad_file_is_invalid(self):
        code, out = self.run_cli("nothing useful\n")
        self.assertEqual(code, 2)
        self.assertEqual(out["verdict"], "INVALID")
        self.assertTrue(out["errors"])

    def test_bad_setting_is_invalid(self):
        code, out = self.run_cli(as_mt5_export(synthetic(300)), "--split", "2")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
