---
name: mt5-lot-calculator
description: Compute MT5 lots, stop, risk, reward, breakeven win rate and margin for a manual order with calc.py. Use for forex, gold, CFDs, sells, anything sized in lots, any margin check, and whenever /trade needs a ticket. Arithmetic only; it never places an order.
---

# MT5 lot calculator

`calc.py` turns an entry, a stop and the account numbers into a volume, the money at risk,
the margin and a verdict. It is arithmetic only: `Decimal` math, JSON on stdout, no network,
no files, no orders.

## Hard rules (from `CLAUDE.md`)

- No external APIs or services. Inputs are the user's screenshots and typed numbers only.
- Never place, modify or close an order. Never ask for or store passwords.
- `NO_TRADE` is a valid result. Never change `--risk-pct`, the stop or the lots to turn a
  `NO_TRADE` into an `OK`. `--risk-pct` always comes from `data/account.json`.
- Demo account only. Not financial advice.
- Reply in Arabic; put symbols, prices and commands in code blocks on their own lines.
- Report the script's numbers as evidence and your judgement as opinion.
- Never guess a number. If a flag's value was not read from a screenshot, typed by the
  user, or stored in `data/`, say it is missing and stop.

## Run it

```bash
python3 .claude/skills/mt5-lot-calculator/calc.py \
  --symbol EURUSD --side sell \
  --entry 1.1098 --stop 1.1108 --target 1.1078 \
  --balance 102 --risk-pct 1 --free-margin 102 --leverage 15 \
  --contract-size 100000 --min-lot 0.01 --lot-step 0.01 --digits 5 \
  --calc-mode forex --current-price 1.1057
```

## Flags

| Flag | Meaning | Default | Comes from |
|------|---------|---------|------------|
| `--symbol` | Symbol name as MT5 shows it | required | chart screenshot |
| `--side` | `buy` or `sell` | required | the setup |
| `--entry` | Entry price | required | the setup |
| `--stop` | Stop loss price | - | the setup |
| `--target` | Take profit price | - | the setup |
| `--rr` | Reward:risk used to derive the target when `--target` is absent | - | typed |
| `--lots` | Fixed volume (see the modes below) | - | typed |
| `--balance` | Account balance | - | `data/account.json` |
| `--risk-pct` | Percent of the balance risked on the trade | `1` | `data/account.json` |
| `--free-margin` | Free margin | - | `data/account.json` |
| `--leverage` | Leverage for this symbol (`15` means 1:15) | `1` | symbol leverage if set, else account leverage |
| `--contract-size` | Units per 1.0 lot | required | `data/symbols.json` |
| `--min-lot` | Minimal volume | `0.01` | `data/symbols.json` |
| `--lot-step` | Volume step | `0.01` | `data/symbols.json` |
| `--digits` | Price decimals | required | `data/symbols.json` |
| `--stops-level` | Minimum stop distance, in points | `0` | `data/symbols.json` |
| `--calc-mode` | `forex`, `cfd_leverage`, `cfd` or `stocks` | `forex` | `data/symbols.json` |
| `--quote-to-account` | Value of 1 unit of the quote (profit) currency in the account currency | `1` | typed by the user when the two currencies differ |
| `--current-price` | Current price: the bid for a sell, the ask for a buy | - | chart screenshot |

Give either `--stop` or `--lots` (or both). `--contract-size` and `--digits` have no
default on purpose: the calculator never assumes a symbol specification.

## MT5 Specification screen -> flags

Open the symbol in Market Watch and choose Specification.

| MT5 field | Flag |
|-----------|------|
| Digits | `--digits` |
| Contract size | `--contract-size` |
| Minimal volume | `--min-lot` |
| Volume step | `--lot-step` |
| Stops level | `--stops-level` |
| Calculation: Forex | `--calc-mode forex` |
| Calculation: CFD Leverage | `--calc-mode cfd_leverage` |
| Calculation: CFD | `--calc-mode cfd` |
| Calculation: Exchange Stocks | `--calc-mode stocks` |
| Profit currency | if it is not the account currency, the user must type `--quote-to-account` |

**Out of scope:** Calculation types Futures, Exchange Futures, CFD Index, Forex No Leverage
and any other type not in the table. Their margin and profit formulas differ. Do not run
the calculator for them: answer "no trade: this symbol type is not supported".

## Rules the script applies

- `budget = balance * risk_pct / 100` and `unit = contract_size * quote_to_account`.
- The stop must be below the entry for a buy and above it for a sell; the target must be
  on the other side. Otherwise the verdict is `INVALID`.
- **With `--stop`:** `lots = budget / (distance * unit)`, rounded **down** to the lot step.
  If `--lots` is also given, it is used as is, with a `RISK_OVER_BUDGET` warning when its
  risk is over the budget.
- **With `--lots` and no `--stop`:** `stop = entry -/+ budget / (lots * unit)`, rounded
  **toward** the entry at the symbol's digits.
- **Below the minimum lot:** verdict `NO_TRADE`, with `min_lot_risk`, `min_lot_risk_pct`
  and `widest_stop_at_min_lot`. In this case `risk`, `reward` and `margin` are shown at the
  minimum lot (`figures_at_lots`), only to explain the refusal.
- **Target:** `--target`, or `entry +/- rr * distance`. Reports `reward`, `reward_risk`
  and `breakeven_win_rate_pct = 100 / (1 + reward_risk)`.
- **Margin:** `lots * contract_size * entry * quote_to_account`, divided by the leverage
  only in `forex` and `cfd_leverage` modes. If the margin is more than the free margin the
  verdict is `NO_TRADE`. Reports `free_margin_after`.
- **Stops level:** a warning when the stop distance in points is under `--stops-level`.
- **Order type** from `--current-price`: equal -> Market; a sell above the price or a buy
  below it -> Limit; otherwise -> Stop.

## Output

One JSON object. It always has `verdict`, `errors[]` and `warnings[]`; each error and
warning is `{"code", "message"}`. Prices and money are strings so no digit is lost.

| Verdict | Exit code | Meaning |
|---------|-----------|---------|
| `OK` | 0 | every rule passed; `ticket` and `ticket_text` are filled |
| `NO_TRADE` | 1 | valid inputs, but a rule blocks the trade; `ticket` is `null` |
| `INVALID` | 2 | wrong or missing inputs |

Main fields: `order_type`, `lots`, `entry`, `stop_loss`, `take_profit`, `budget`, `risk`,
`risk_pct`, `reward`, `reward_risk`, `reward_risk_raw` (4 decimals, rounded down; use it
for the 1.5 gate), `breakeven_win_rate_pct`, `margin`, `free_margin_after`, `stop_points`,
`min_lot_risk`, `min_lot_risk_pct`, `widest_stop_at_min_lot`, `sizing_basis`.

## Ticket format

When the verdict is `OK`, show `ticket_text` exactly as printed, in a code block:

```
Symbol:      EURUSD
Type:        Sell Limit
Volume:      0.01
Price:       1.1098
Stop Loss:   1.1108
Take Profit: 1.1078
```

Then, in a second code block, the numbers: risk in money and percent, reward, reward:risk,
breakeven win rate, margin and free margin after. Then every warning. Never show a ticket
for `NO_TRADE` or `INVALID`: show the error messages with their numbers instead, and what
would have to change (the free margin needed, or `widest_stop_at_min_lot`).

End with the two reminders: a stop can fill at a worse price than its level, and nothing
was placed - the user enters the order by hand.

## Notes

- The risk covers the price distance only. Spread, commission, swap and slippage are not
  included; say so when the user asks why a real loss differed.
- For the open-risk check, the risk of an existing position is the same arithmetic:
  run the script with that position's `--entry`, `--stop` and `--lots` and read `risk`.
- Long exchange stocks are sized with `position-sizer` first; the calculator is then run
  with `--calc-mode stocks --lots <shares>` for the margin check and the ticket.
