#!/usr/bin/env python3
"""MT5 lot calculator.

Arithmetic only. Reads its flags, prints one JSON object, exits.
It never touches the network, never reads account credentials and never
places, modifies or closes an order. Python standard library only.

Verdicts and exit codes:
    OK        0   the numbers fit every rule
    NO_TRADE  1   the inputs are valid but a risk rule blocks the trade
    INVALID   2   the inputs are wrong or incomplete
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
)

EXIT_CODES = {"OK": 0, "NO_TRADE": 1, "INVALID": 2}
LEVERAGED_MODES = ("forex", "cfd_leverage")
CENT = Decimal("0.01")
TENTH = Decimal("0.1")
HUNDRED = Decimal(100)


class JsonArgumentParser(argparse.ArgumentParser):
    """An argument parser that reports bad flags as an INVALID JSON result."""

    def error(self, message):
        emit(
            {
                "verdict": "INVALID",
                "errors": [{"code": "BAD_ARGUMENTS", "message": message}],
                "warnings": [],
            }
        )


def emit(result):
    print(json.dumps(result, indent=2))
    sys.exit(EXIT_CODES[result["verdict"]])


def decimal_arg(text):
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not value.is_finite():
        raise argparse.ArgumentTypeError(f"not a finite number: {text!r}")
    return value


def build_parser():
    p = JsonArgumentParser(description="MT5 lot, risk and margin arithmetic. Prints JSON.")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", required=True, choices=("buy", "sell"))
    p.add_argument("--entry", required=True, type=decimal_arg)
    p.add_argument("--stop", type=decimal_arg)
    p.add_argument("--target", type=decimal_arg)
    p.add_argument("--rr", type=decimal_arg, help="reward:risk used when --target is absent")
    p.add_argument("--lots", type=decimal_arg)
    p.add_argument("--balance", type=decimal_arg)
    p.add_argument("--risk-pct", type=decimal_arg, default=Decimal("1"))
    p.add_argument("--free-margin", type=decimal_arg)
    p.add_argument("--leverage", type=decimal_arg, default=Decimal("1"))
    p.add_argument("--contract-size", required=True, type=decimal_arg)
    p.add_argument("--min-lot", type=decimal_arg, default=Decimal("0.01"))
    p.add_argument("--lot-step", type=decimal_arg, default=Decimal("0.01"))
    p.add_argument("--digits", required=True, type=int)
    p.add_argument("--stops-level", type=decimal_arg, default=Decimal("0"), help="in points")
    p.add_argument(
        "--calc-mode",
        choices=("forex", "cfd_leverage", "cfd", "stocks"),
        default="forex",
    )
    p.add_argument("--quote-to-account", type=decimal_arg, default=Decimal("1"))
    p.add_argument("--current-price", type=decimal_arg)
    return p


def decimals_of(value):
    exponent = value.as_tuple().exponent
    return -exponent if exponent < 0 else 0


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def one_decimal(value):
    return str(value.quantize(TENTH, rounding=ROUND_HALF_UP))


def plain(value):
    """Text of a number exactly as it was typed, without exponent notation."""
    return format(value, "f")


def calculate(a):
    """Return the result dictionary for parsed arguments ``a``."""
    invalid = []  # wrong or missing inputs  -> INVALID
    blocked = []  # valid inputs, rule fails -> NO_TRADE
    warnings = []

    def bad(code, message):
        invalid.append({"code": code, "message": message})

    def block(code, message):
        blocked.append({"code": code, "message": message})

    def warn(code, message):
        warnings.append({"code": code, "message": message})

    buy = a.side == "buy"
    sign = Decimal(1) if buy else Decimal(-1)  # direction in which the trade profits

    out = {
        "verdict": None,
        "symbol": a.symbol,
        "side": a.side,
        "calc_mode": a.calc_mode,
        "order_type": None,
        "lots": None,
        "figures_at_lots": None,
        "sizing_basis": None,
        "entry": plain(a.entry),
        "stop_loss": plain(a.stop) if a.stop is not None else None,
        "stop_derived": False,
        "take_profit": plain(a.target) if a.target is not None else None,
        "target_derived": False,
        "stop_distance": None,
        "stop_points": None,
        "budget": None,
        "risk": None,
        "risk_pct": None,
        "reward": None,
        "reward_risk": None,
        "reward_risk_raw": None,
        "breakeven_win_rate_pct": None,
        "margin": None,
        "free_margin": plain(a.free_margin) if a.free_margin is not None else None,
        "free_margin_after": None,
        "min_lot_risk": None,
        "min_lot_risk_pct": None,
        "widest_stop_at_min_lot": None,
        "ticket": None,
        "ticket_text": None,
        "errors": [],
        "warnings": warnings,
    }

    def finish():
        out["errors"] = invalid + blocked
        out["verdict"] = "INVALID" if invalid else ("NO_TRADE" if blocked else "OK")
        if out["verdict"] == "OK":
            ticket = {
                "Symbol": a.symbol,
                "Type": out["order_type"] or "UNKNOWN (pass --current-price)",
                "Volume": out["lots"],
                "Price": out["entry"],
                "Stop Loss": out["stop_loss"],
                "Take Profit": out["take_profit"] or "-",
            }
            out["ticket"] = ticket
            out["ticket_text"] = "\n".join(
                f"{label + ':':<13}{value}" for label, value in ticket.items()
            )
        return out

    # ---- input validation -------------------------------------------------
    positive = {
        "--entry": a.entry,
        "--stop": a.stop,
        "--target": a.target,
        "--rr": a.rr,
        "--lots": a.lots,
        "--balance": a.balance,
        "--risk-pct": a.risk_pct,
        "--leverage": a.leverage,
        "--contract-size": a.contract_size,
        "--min-lot": a.min_lot,
        "--lot-step": a.lot_step,
        "--quote-to-account": a.quote_to_account,
        "--current-price": a.current_price,
    }
    for flag, value in positive.items():
        if value is not None and value <= 0:
            bad("NOT_POSITIVE", f"{flag} must be greater than zero, got {plain(value)}")
    if a.stops_level < 0:
        bad("NOT_POSITIVE", f"--stops-level cannot be negative, got {plain(a.stops_level)}")
    if not 0 <= a.digits <= 10:
        bad("BAD_DIGITS", f"--digits must be between 0 and 10, got {a.digits}")
    if invalid:
        return finish()

    for flag, value in (
        ("--entry", a.entry),
        ("--stop", a.stop),
        ("--target", a.target),
        ("--current-price", a.current_price),
    ):
        if value is not None and decimals_of(value) > a.digits:
            bad(
                "TOO_MANY_DECIMALS",
                f"{flag} {plain(value)} has more decimals than the symbol's digits ({a.digits})",
            )

    if a.stop is None and a.lots is None:
        bad("NEED_STOP_OR_LOTS", "give --stop (to size the lots) or --lots (to derive the stop)")

    if a.stop is not None:
        if buy and a.stop >= a.entry:
            bad(
                "STOP_WRONG_SIDE",
                f"buy: the stop {plain(a.stop)} must be below the entry {plain(a.entry)}",
            )
        if not buy and a.stop <= a.entry:
            bad(
                "STOP_WRONG_SIDE",
                f"sell: the stop {plain(a.stop)} must be above the entry {plain(a.entry)}",
            )

    if a.target is not None:
        if buy and a.target <= a.entry:
            bad(
                "TARGET_WRONG_SIDE",
                f"buy: the target {plain(a.target)} must be above the entry {plain(a.entry)}",
            )
        if not buy and a.target >= a.entry:
            bad(
                "TARGET_WRONG_SIDE",
                f"sell: the target {plain(a.target)} must be below the entry {plain(a.entry)}",
            )

    lot_quantum = Decimal(1).scaleb(-decimals_of(a.lot_step))

    def lots_text(value):
        return str(value.quantize(lot_quantum, rounding=ROUND_DOWN))

    if a.lots is not None and a.lots % a.lot_step != 0:
        bad(
            "LOTS_NOT_ON_STEP",
            f"--lots {plain(a.lots)} is not a multiple of the lot step {plain(a.lot_step)}",
        )

    budget = None
    if a.balance is not None:
        budget = a.balance * a.risk_pct / HUNDRED
        out["budget"] = money(budget)
    elif a.stop is None or a.lots is None:
        bad("MISSING_BALANCE", "--balance is required to compute the risk budget")

    if invalid:
        return finish()

    unit = a.contract_size * a.quote_to_account  # account money per 1.0 price move per lot
    point = Decimal(1).scaleb(-a.digits)

    def toward_entry(price):
        """Round a stop price to the symbol's digits, toward the entry."""
        return price.quantize(point, rounding=ROUND_CEILING if buy else ROUND_FLOOR)

    def price_text(price):
        return str(price.quantize(point))

    def widest_stop(lots):
        return toward_entry(a.entry - sign * budget / (lots * unit))

    # ---- lots and stop ------------------------------------------------------
    stop = a.stop
    if a.lots is not None:
        lots = a.lots
        out["sizing_basis"] = "given_lots"
        if lots < a.min_lot:
            block(
                "LOTS_BELOW_MIN",
                f"--lots {plain(lots)} is below the minimum lot {plain(a.min_lot)}",
            )
            if budget is not None:
                out["widest_stop_at_min_lot"] = price_text(widest_stop(a.min_lot))
        if stop is None and not blocked:
            stop = widest_stop(lots)
            out["stop_derived"] = True
            out["stop_loss"] = price_text(stop)
            if stop == a.entry:
                block(
                    "STOP_AT_ENTRY",
                    f"the budget {money(budget)} is too small for {plain(lots)} lots: "
                    "the stop would sit on the entry price",
                )
            elif stop <= 0:
                bad("STOP_NOT_POSITIVE", "the derived stop price is not above zero")
    else:
        distance = abs(a.entry - stop)
        raw_lots = budget / (distance * unit)
        lots = (raw_lots / a.lot_step).to_integral_value(rounding=ROUND_FLOOR) * a.lot_step
        out["sizing_basis"] = "risk_sized"

    out["lots"] = lots_text(lots)
    if invalid or stop is None or stop == a.entry:
        return finish()

    distance = abs(a.entry - stop)
    out["stop_distance"] = plain(distance)
    out["stop_points"] = plain((distance / point).quantize(Decimal(1), rounding=ROUND_DOWN))

    figures_lots = lots
    if a.lots is None and lots < a.min_lot:
        figures_lots = a.min_lot
        out["sizing_basis"] = "min_lot"
        min_lot_risk = a.min_lot * unit * distance
        out["min_lot_risk"] = money(min_lot_risk)
        out["min_lot_risk_pct"] = one_decimal(min_lot_risk / a.balance * HUNDRED)
        out["widest_stop_at_min_lot"] = price_text(widest_stop(a.min_lot))
        block(
            "LOTS_BELOW_MIN",
            f"the budget {money(budget)} buys {lots_text(lots)} lots at this stop; the minimum "
            f"lot is {plain(a.min_lot)} and would risk {out['min_lot_risk']} "
            f"({out['min_lot_risk_pct']}% of the balance). The widest stop that fits the "
            f"budget at the minimum lot is {out['widest_stop_at_min_lot']}. "
            "Risk, reward and margin below are shown at the minimum lot.",
        )
    out["figures_at_lots"] = lots_text(figures_lots)

    # ---- risk ---------------------------------------------------------------
    risk = figures_lots * unit * distance
    out["risk"] = money(risk)
    if a.balance is not None:
        out["risk_pct"] = money(risk / a.balance * HUNDRED)
    if a.lots is not None and budget is not None and risk > budget:
        warn(
            "RISK_OVER_BUDGET",
            f"the given lots risk {money(risk)}, over the budget {money(budget)} "
            f"({plain(a.risk_pct)}% of the balance)",
        )
    if a.lots is not None and budget is None:
        warn("NO_BUDGET_CHECK", "--balance was not given, so the risk was not checked against a budget")

    # ---- target and reward --------------------------------------------------
    target = a.target
    if target is not None and a.rr is not None:
        warn("RR_IGNORED", "--target was given, so --rr was ignored")
    if target is None and a.rr is not None:
        target = (a.entry + sign * a.rr * distance).quantize(point, rounding=ROUND_HALF_UP)
        out["target_derived"] = True
        out["take_profit"] = price_text(target)
        if target <= 0:
            bad("TARGET_NOT_POSITIVE", "the derived target price is not above zero")
            return finish()
    if target is None:
        warn("NO_TARGET", "no --target or --rr: reward and reward:risk were not computed")
    else:
        target_distance = abs(target - a.entry)
        reward = figures_lots * unit * target_distance
        ratio = reward / risk
        out["reward"] = money(reward)
        out["reward_risk"] = money(ratio)
        out["reward_risk_raw"] = str(ratio.quantize(Decimal("0.0001"), rounding=ROUND_DOWN))
        out["breakeven_win_rate_pct"] = one_decimal(HUNDRED / (1 + ratio))
        if a.stops_level > 0 and target_distance / point < a.stops_level:
            warn(
                "TARGET_INSIDE_STOPS_LEVEL",
                f"the target is {plain((target_distance / point).quantize(Decimal(1)))} points "
                f"from the entry, under the stops level of {plain(a.stops_level)} points",
            )

    # ---- margin -------------------------------------------------------------
    margin = figures_lots * a.contract_size * a.entry * a.quote_to_account
    if a.calc_mode in LEVERAGED_MODES:
        margin = margin / a.leverage
    elif a.leverage != 1:
        warn("LEVERAGE_IGNORED", f"leverage is not applied in {a.calc_mode} mode")
    out["margin"] = money(margin)
    if a.free_margin is None:
        warn("FREE_MARGIN_NOT_GIVEN", "--free-margin was not given, so the margin was not checked")
    else:
        out["free_margin_after"] = money(a.free_margin - margin)
        if margin > a.free_margin:
            block(
                "MARGIN_EXCEEDS_FREE_MARGIN",
                f"the margin {money(margin)} for {lots_text(figures_lots)} lots is more than "
                f"the free margin {plain(a.free_margin)}; at least {money(margin)} is needed",
            )

    # ---- stops level --------------------------------------------------------
    if a.stops_level > 0 and distance / point < a.stops_level:
        warn(
            "STOP_INSIDE_STOPS_LEVEL",
            f"the stop is {out['stop_points']} points from the entry, under the stops level "
            f"of {plain(a.stops_level)} points: MT5 may reject it",
        )

    # ---- order type ---------------------------------------------------------
    if a.current_price is None:
        warn("NO_CURRENT_PRICE", "--current-price was not given, so the order type is unknown")
    else:
        word = "Buy" if buy else "Sell"
        if a.entry == a.current_price:
            out["order_type"] = f"{word} Market"
        else:
            entry_above = a.entry > a.current_price
            limit = entry_above != buy  # sell above the price, or buy below it
            out["order_type"] = f"{word} {'Limit' if limit else 'Stop'}"
            gap = abs(a.entry - a.current_price) / point
            if a.stops_level > 0 and gap < a.stops_level:
                warn(
                    "ENTRY_INSIDE_STOPS_LEVEL",
                    f"the pending entry is {plain(gap.quantize(Decimal(1)))} points from the "
                    f"current price, under the stops level of {plain(a.stops_level)} points",
                )

    return finish()


def main(argv=None):
    args = build_parser().parse_args(argv)
    emit(calculate(args))


if __name__ == "__main__":
    main()
