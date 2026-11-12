"""Tests for .claude/skills/mt5-lot-calculator/calc.py.

Run from the repository root:
    python3 -m unittest discover -s tests -v
"""

import json
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALC = ROOT / ".claude" / "skills" / "mt5-lot-calculator" / "calc.py"

EURUSD = ["--symbol", "EURUSD", "--contract-size", "100000", "--digits", "5"]
XAUUSD = ["--symbol", "XAUUSD", "--contract-size", "100", "--digits", "2"]


def run(*flags):
    """Run calc.py and return (exit_code, parsed_json)."""
    proc = subprocess.run(
        [sys.executable, str(CALC), *flags],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


def codes(items):
    return [item["code"] for item in items]


class CalcCase(unittest.TestCase):
    def assertNumber(self, out, field, expected):
        self.assertIsNotNone(out[field], f"{field} is missing")
        self.assertEqual(Decimal(out[field]), Decimal(expected), field)

    def assertShape(self, out):
        self.assertIn(out["verdict"], ("OK", "NO_TRADE", "INVALID"))
        self.assertIsInstance(out["errors"], list)
        self.assertIsInstance(out["warnings"], list)


class TestSpecCases(CalcCase):
    def test_a_eurusd_sell_limit_ok(self):
        code, out = run(
            *EURUSD, "--side", "sell", "--entry", "1.1098", "--stop", "1.1108",
            "--target", "1.1078", "--balance", "102", "--free-margin", "102",
            "--leverage", "15", "--current-price", "1.1057",
        )
        self.assertShape(out)
        self.assertEqual(code, 0)
        self.assertEqual(out["verdict"], "OK")
        self.assertEqual(out["errors"], [])
        self.assertNumber(out, "lots", "0.01")
        self.assertNumber(out, "risk", "1.00")
        self.assertNumber(out, "reward", "2.00")
        self.assertNumber(out, "reward_risk", "2.00")
        self.assertNumber(out, "breakeven_win_rate_pct", "33.3")
        self.assertNumber(out, "margin", "73.99")
        self.assertEqual(out["order_type"], "Sell Limit")
        self.assertEqual(
            out["ticket_text"],
            "Symbol:      EURUSD\n"
            "Type:        Sell Limit\n"
            "Volume:      0.01\n"
            "Price:       1.1098\n"
            "Stop Loss:   1.1108\n"
            "Take Profit: 1.1078",
        )

    def test_b_xauusd_below_min_lot(self):
        code, out = run(
            *XAUUSD, "--side", "sell", "--entry", "3987", "--stop", "4003",
            "--balance", "102",
        )
        self.assertShape(out)
        self.assertEqual(code, 1)
        self.assertEqual(out["verdict"], "NO_TRADE")
        self.assertIn("LOTS_BELOW_MIN", codes(out["errors"]))
        self.assertNumber(out, "min_lot_risk", "16.00")
        self.assertNumber(out, "min_lot_risk_pct", "15.7")
        self.assertNumber(out, "widest_stop_at_min_lot", "3988.02")
        self.assertIsNone(out["ticket"])

    def test_c_xauusd_cfd_leverage_no_trade(self):
        code, out = run(
            *XAUUSD, "--side", "sell", "--entry", "3900", "--stop", "3930",
            "--target", "3850", "--balance", "102", "--free-margin", "26.73",
            "--leverage", "20", "--calc-mode", "cfd_leverage",
        )
        self.assertShape(out)
        self.assertEqual(code, 1)
        self.assertEqual(out["verdict"], "NO_TRADE")
        self.assertNumber(out, "risk", "30.00")
        self.assertNumber(out, "margin", "195.00")
        self.assertNumber(out, "reward_risk", "1.67")
        self.assertNumber(out, "widest_stop_at_min_lot", "3901.02")
        self.assertIsNone(out["ticket"])

    def test_d_margin_blocks_then_passes(self):
        common = [
            *EURUSD, "--side", "sell", "--entry", "1.1100", "--stop", "1.1110",
            "--target", "1.1080", "--balance", "102", "--leverage", "15",
        ]
        code, out = run(*common, "--free-margin", "26.73")
        self.assertShape(out)
        self.assertEqual(code, 1)
        self.assertEqual(out["verdict"], "NO_TRADE")
        self.assertEqual(codes(out["errors"]), ["MARGIN_EXCEEDS_FREE_MARGIN"])
        self.assertNumber(out, "margin", "74.00")
        self.assertNumber(out, "free_margin_after", "-47.27")
        self.assertIsNone(out["ticket"])

        code, out = run(*common, "--free-margin", "102")
        self.assertShape(out)
        self.assertEqual(code, 0)
        self.assertEqual(out["verdict"], "OK")
        self.assertNumber(out, "free_margin_after", "28.00")

    def test_e_stop_derived_from_lots(self):
        code, out = run(
            *EURUSD, "--side", "buy", "--entry", "1.1050", "--lots", "0.01",
            "--rr", "2", "--balance", "102", "--leverage", "15",
        )
        self.assertShape(out)
        self.assertEqual(code, 0)
        self.assertEqual(out["stop_loss"], "1.10398")
        self.assertEqual(out["take_profit"], "1.10704")

    def test_f_buy_stop_above_entry_is_invalid(self):
        code, out = run(*EURUSD, "--side", "buy", "--entry", "1.1050", "--stop", "1.1060")
        self.assertShape(out)
        self.assertEqual(code, 2)
        self.assertEqual(out["verdict"], "INVALID")
        self.assertIn("STOP_WRONG_SIDE", codes(out["errors"]))


class TestRules(CalcCase):
    def test_sell_stop_below_entry_is_invalid(self):
        code, out = run(
            *EURUSD, "--side", "sell", "--entry", "1.1050", "--stop", "1.1040",
            "--balance", "102",
        )
        self.assertEqual((code, out["verdict"]), (2, "INVALID"))
        self.assertIn("STOP_WRONG_SIDE", codes(out["errors"]))

    def test_target_on_wrong_side_is_invalid(self):
        for side, stop, target in (("buy", "1.1040", "1.1045"), ("sell", "1.1060", "1.1055")):
            code, out = run(
                *EURUSD, "--side", side, "--entry", "1.1050", "--stop", stop,
                "--target", target, "--balance", "102",
            )
            self.assertEqual((code, out["verdict"]), (2, "INVALID"), side)
            self.assertIn("TARGET_WRONG_SIDE", codes(out["errors"]))

    def test_lots_round_down_to_step(self):
        # budget 10.00 / (0.0010 * 100000) = 0.1 lots exactly; 0.0007 stop gives 0.1428 -> 0.14
        code, out = run(
            *EURUSD, "--side", "buy", "--entry", "1.1050", "--stop", "1.1043",
            "--balance", "1000", "--free-margin", "1000", "--leverage", "30",
        )
        self.assertEqual(code, 0)
        self.assertNumber(out, "lots", "0.14")
        self.assertLessEqual(Decimal(out["risk"]), Decimal(out["budget"]))

    def test_given_lots_over_budget_warns(self):
        code, out = run(
            *EURUSD, "--side", "sell", "--entry", "1.1098", "--stop", "1.1108",
            "--lots", "0.05", "--balance", "102", "--free-margin", "1000",
            "--leverage", "15",
        )
        self.assertEqual(code, 0)
        self.assertNumber(out, "lots", "0.05")
        self.assertNumber(out, "risk", "5.00")
        self.assertIn("RISK_OVER_BUDGET", codes(out["warnings"]))

    def test_sell_stop_derived_rounds_toward_entry(self):
        # budget 1.00 / (0.03 * 100000) = 0.000333.. -> the stop must round down for a sell
        code, out = run(
            *EURUSD, "--side", "sell", "--entry", "1.1050", "--lots", "0.03",
            "--balance", "100",
        )
        self.assertEqual(code, 0)
        self.assertEqual(out["stop_loss"], "1.10533")
        self.assertLessEqual(Decimal(out["risk"]), Decimal(out["budget"]))

    def test_leverage_only_in_forex_and_cfd_leverage(self):
        base = [
            "--symbol", "F", "--side", "buy", "--entry", "12.00", "--stop", "11.50",
            "--lots", "2", "--balance", "102", "--free-margin", "102", "--leverage", "15",
            "--contract-size", "1", "--digits", "2", "--min-lot", "1", "--lot-step", "1",
        ]
        for mode, margin in (("stocks", "24.00"), ("cfd", "24.00"),
                             ("cfd_leverage", "1.60"), ("forex", "1.60")):
            code, out = run(*base, "--calc-mode", mode)
            self.assertEqual(code, 0, mode)
            self.assertNumber(out, "margin", margin)

    def test_stops_level_warning(self):
        code, out = run(
            *EURUSD, "--side", "sell", "--entry", "1.1098", "--stop", "1.1108",
            "--balance", "102", "--free-margin", "102", "--leverage", "15",
            "--stops-level", "150",
        )
        self.assertEqual(code, 0)
        self.assertIn("STOP_INSIDE_STOPS_LEVEL", codes(out["warnings"]))

    def test_order_types(self):
        base = ["--balance", "102", "--free-margin", "102", "--leverage", "15"]
        sell = [*EURUSD, "--side", "sell", "--entry", "1.1098", "--stop", "1.1108", *base]
        buy = [*EURUSD, "--side", "buy", "--entry", "1.1098", "--stop", "1.1088", *base]
        expected = (
            (sell, "1.1057", "Sell Limit"),
            (sell, "1.1120", "Sell Stop"),
            (sell, "1.1098", "Sell Market"),
            (buy, "1.1120", "Buy Limit"),
            (buy, "1.1057", "Buy Stop"),
            (buy, "1.1098", "Buy Market"),
        )
        for flags, price, order_type in expected:
            _, out = run(*flags, "--current-price", price)
            self.assertEqual(out["order_type"], order_type, price)

    def test_quote_to_account_scales_risk(self):
        # A JPY-quoted pair on a USD account, with one JPY worth 0.005 USD:
        # budget 100 / (0.300 * 100000 * 0.005) = 0.666.. -> 0.66 lots, risk 99.00
        code, out = run(
            "--symbol", "USDJPY", "--side", "buy", "--entry", "200.000", "--stop", "199.700",
            "--balance", "10000", "--free-margin", "10000", "--leverage", "30",
            "--contract-size", "100000", "--digits", "3", "--quote-to-account", "0.005",
        )
        self.assertEqual(code, 0)
        self.assertNumber(out, "lots", "0.66")
        self.assertNumber(out, "risk", "99.00")
        self.assertNumber(out, "margin", "2200.00")

    def test_bad_flags_still_print_json(self):
        code, out = run("--symbol", "EURUSD", "--side", "long", "--entry", "abc")
        self.assertShape(out)
        self.assertEqual((code, out["verdict"]), (2, "INVALID"))
        self.assertEqual(codes(out["errors"]), ["BAD_ARGUMENTS"])

    def test_missing_stop_and_lots_is_invalid(self):
        code, out = run(*EURUSD, "--side", "buy", "--entry", "1.1050", "--balance", "102")
        self.assertEqual((code, out["verdict"]), (2, "INVALID"))
        self.assertIn("NEED_STOP_OR_LOTS", codes(out["errors"]))

    def test_price_with_too_many_decimals_is_invalid(self):
        code, out = run(
            *XAUUSD, "--side", "sell", "--entry", "3987.123", "--stop", "4003",
            "--balance", "102",
        )
        self.assertEqual((code, out["verdict"]), (2, "INVALID"))
        self.assertIn("TOO_MANY_DECIMALS", codes(out["errors"]))


if __name__ == "__main__":
    unittest.main()
