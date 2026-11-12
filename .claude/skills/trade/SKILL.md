---
name: trade
description: Trade desk run. Reads the attached MetaTrader 5 screenshots (charts, Trade tab, Specification) or the files in inbox/, analyses each chart, applies fixed gates, sizes the trade with the scripts and answers in Arabic with one ticket to copy into MT5 by hand, or a clear "no trade" with the reason. Use when the user types /trade.
argument-hint: "[optional note, e.g. a symbol to focus on]"
---

# /trade

Screenshots in, one ticket or "no trade" out. You do the reasoning; the scripts do the
arithmetic; the user places the order by hand.

## Hard rules (from `CLAUDE.md` - they override everything below)

1. No external APIs or services, no web search or fetch, no market data, no MT5 bridge.
   Inputs are only the user's screenshots and typed numbers. Python standard library only.
2. Never place, modify or close an order. Never ask for or store passwords or logins.
3. "No trade" is a valid result. Never loosen a gate or a risk rule to force a ticket.
   Never promise a win. Scenario probabilities are estimates, never measured statistics.
4. Demo account only. Not financial advice.
5. Answer in Arabic, short and simple. English identifiers, symbols, prices, numbers with
   units and commands go in code blocks on their own lines, never inside an Arabic sentence.
6. Separate evidence (read from screenshots, computed by scripts) from opinion (judgement).
7. Never guess a number you cannot read. Write that it is missing.

## Step 1 - Collect the inputs

- Use the images attached to the user's message. If there are none, use the image files in
  `inbox/` (ignore `inbox/processed/`). If there are no images at all, stop and say that at
  least one chart screenshot is required.
- Classify each image: **chart**, **Trade tab**, **Specification**, or unknown. Say which
  images you could not classify and do not use them.
- At least one chart is required. Best: the same symbol on W1, H4 and H1, plus the Trade tab.
- **Limits:** at most three symbols per run and one ticket per symbol. If more than three
  symbols are present, take the three with the most timeframes and list the ones skipped.
- If a Trade tab or Specification screenshot is included, follow the `/account` skill
  (`.claude/skills/account/SKILL.md`) **first**, so the data files are current, and show
  its before/after.
- Then read `data/account.json` and `data/symbols.json`.

## Step 2 - Read each image (evidence)

List what you read under the Arabic heading **ما قرأته من الصور**, one code block per image:

```
Image:        1 (chart)
Symbol:       EURUSD
Timeframe:    H4
Bid:          1.1057
Ask:          missing
Visible high: 1.1108
Visible low:  1.0990
Order lines:  none
```

For a Trade tab: balance, equity, margin, free margin, and every open position with its
symbol, side, volume, open price, stop loss and take profit.

Rules for reading:

- Copy numbers exactly as displayed. A number that is cut off, blurred or not shown is
  `missing`. Do not estimate a price from where a candle sits between two grid lines; use
  only printed labels (price scale labels, bid/ask labels, order lines, the OHLC line).
- If the symbol or the timeframe of a chart cannot be read, do not analyse that chart.
- If a screenshot shows its date or time, report it. Prices move: the ticket is only as
  fresh as the screenshot.

## Step 3 - Analyse each chart

Follow `.claude/skills/technical-analyst/SKILL.md` (read its framework and template) for
each chart, **highest timeframe first** (MN, W1, D1, H4, H1, M30, M15 ...).

- Save one report per chart:
  `reports/[SYMBOL]_[TIMEFRAME]_technical_analysis_[YYYY-MM-DD].md`.
- The method is written for weekly charts. For every chart that is not W1, write in the
  report and in the answer that the method is being used off its timeframe and that the
  result is weaker evidence. If no W1 chart was given, say so in the warnings.
- Every scenario needs an estimate in percent (summing to 100), target levels and one
  invalidation level, all as printed prices from the chart. Write "estimate" next to each
  percentage. Do not raise an estimate to pass a gate.
- Indicators that are not visible on the chart (moving averages, volume) are "not visible".

## Step 4 - Decide the setup: fixed gates

Check the gates in this order for each symbol. **If any gate fails, the answer for that
symbol is no trade.** Do not adjust levels or estimates after seeing a gate fail.

| # | Gate | Passes when |
|---|------|-------------|
| 1 | Direction | The base scenario of the **highest** timeframe points up (buy) or down (sell), and **no lower timeframe's base scenario points the other way**. A sideways base scenario on the highest timeframe has no direction: fail. A sideways lower timeframe is not a contradiction, but mention it. |
| 2 | Estimate | The base scenario estimate of the highest timeframe is **50 percent or more**. |
| 3 | Entry | The entry is a support or resistance level named in the analysis. Use a **pending order at the level**. Use a market order only when the price is already there: the current price (ask for a buy, bid for a sell) equals the level, or the level lies between the bid and the ask. The current price must be readable; if it is missing, fail. |
| 4 | Stop | The stop is **beyond the invalidation level** of the base scenario: above it for a sell, below it for a buy. Use the first printed price beyond that level (for example the high of the wick that defines it). Never place the stop at an arbitrary distance, and never work it backwards from the money budget. |
| 5 | Target | The target is the **next** support or resistance level in the trade direction, from the analysis. |
| 6 | Reward:risk | `reward_risk_raw` from the calculator is **1.5 or more**. |

Gates 1-5 are judged from the analysis; gate 6 is checked with the script in step 5.

### Candidate entries

Gate 3 can be met by more than one level. List up to **three** candidate entries, nearest
to the current price first. The stop is the same for all of them (gate 4). Each candidate
has its own target: the next support or resistance level beyond that entry in the trade
direction (gate 5).

Fix this list **before** sizing. In step 5 size the candidates in order: the first one
that passes every check is the ticket. If none passes, the answer is no trade and the
reason shown is the first candidate's. Never add or move a level after seeing a sizing
result, and never change the stop to make a candidate pass.

### Check the setup against the analysis

Before sizing, check the setup against what the analysis itself says. Any mismatch is a
failed gate, not something to patch:

- The side matches the direction of the highest timeframe's base scenario, and no lower
  timeframe's base scenario points the other way (gate 1).
- The base scenario has the largest estimate of its chart, the estimates of that chart
  sum to 100, and the base estimate is 50 or more (gate 2).
- Every candidate entry and every target is a price listed as a support or resistance
  in the analysis of that symbol (gates 3 and 5).
- The stop is strictly beyond the base scenario's invalidation level (gate 4).

### Guards

A ticket is given only when all of these hold. They never turn a no trade into a ticket.

- **News lock.** If `news_lock_until` in `data/account.json` is a time in the future: no
  trade. The user sets it when an important release is near; there is no news feed.
- **Daily loss limit.** Count today's rows in `journal.csv` whose `result` is `loss`. If
  the count is `max_daily_losses` in `data/account.json` or more: no trade for the rest of
  the day.
- **Second reading.** Before giving a ticket, read the charts a second time from scratch,
  without looking at the first analysis. If the second reading finds no setup, or its
  side differs from the first: no trade. If it agrees on the side but names other levels,
  keep the first reading's levels and say so in the warnings.
- **Order lines.** If a chart shows an order line or an open position for the ticket's
  symbol, list those lines in the warnings: an old pending order may conflict with the
  ticket.
- **Fresh price.** A ticket older than ten minutes is checked again against the current
  price before it is used. If the order type would change (the price has crossed the
  entry, the stop or the target), the ticket is no longer valid.

## Step 5 - Size it (scripts only)

Take every number from `data/account.json`, `data/symbols.json` and the setup. Show each
command you run. Do not do this arithmetic in your head.

With several candidate entries, size them in the order listed and stop at the first one
that passes (see "Candidate entries").

**If the symbol is missing from `data/symbols.json`, or its `calc_mode` is not one of
`forex`, `cfd_leverage`, `cfd`, `stocks`:** no trade. Ask for a Specification screenshot.

**If the symbol's `quote_to_account` is `null`** (its profit currency is not the account
currency and the user has not typed the rate): no trade. Ask the user to type the rate.

**If the symbol's `"confirmed"` is `false`:** continue, but the answer must say that the
specification is unconfirmed (not read from a Specification screenshot) and that the
volume, risk and margin depend on it.

### 5a. Sells, and every leveraged symbol (`forex`, `cfd_leverage`, `cfd`)

```bash
python3 .claude/skills/mt5-lot-calculator/calc.py \
  --symbol SYMBOL --side buy|sell \
  --entry ENTRY --stop STOP --target TARGET \
  --balance BALANCE --risk-pct RISK_PCT --free-margin FREE_MARGIN \
  --leverage LEVERAGE --contract-size CONTRACT --min-lot MIN_LOT --lot-step LOT_STEP \
  --digits DIGITS --calc-mode CALC_MODE --quote-to-account QUOTE_TO_ACCOUNT \
  --stops-level STOPS_LEVEL --current-price CURRENT
```

- `--leverage`: the symbol's `leverage` if it is set, otherwise the account's.
- `--stops-level`: omit the flag when the stored value is `null`, and say it is unknown.
- `--current-price`: the bid for a sell, the ask for a buy. If only one of the two is
  readable, use it and add a warning.
- Never pass `--lots` here, and never pass a `--risk-pct` other than the stored one.

### 5b. Long exchange stocks (`calc_mode` is `stocks` and the side is buy)

1. Share count from the third-party sizer (it writes its report into `reports/`):

   ```bash
   python3 .claude/skills/position-sizer/scripts/position_sizer.py \
     --account-size BALANCE --entry ENTRY --stop STOP \
     --risk-pct RISK_PCT --max-position-pct MAX_POSITION_PCT --output-dir reports/
   ```

   Read `final_recommended_shares` from the JSON report. Zero shares means no trade.

2. Cost against free margin, reward:risk and the ticket, with the calculator:

   ```bash
   python3 .claude/skills/mt5-lot-calculator/calc.py \
     --symbol SYMBOL --side buy --entry ENTRY --stop STOP --target TARGET \
     --lots SHARES --balance BALANCE --risk-pct RISK_PCT --free-margin FREE_MARGIN \
     --contract-size 1 --min-lot 1 --lot-step 1 --digits DIGITS \
     --calc-mode stocks --current-price CURRENT
   ```

A stock **sell** goes through 5a.

### 5c. Read the verdict

- `INVALID` or `NO_TRADE` -> no trade. Report each error message with its numbers.
- `OK` with a `RISK_OVER_BUDGET`, `FREE_MARGIN_NOT_GIVEN` or `NO_CURRENT_PRICE` warning
  -> no trade (the check is incomplete).
- `OK` but `reward_risk_raw` under `1.5` -> no trade (gate 6).
- Any other warning (for example the stops level) is shown with the ticket.

### 5d. Open risk

- Open positions come from the Trade tab in this run, or from `open_positions` in
  `data/account.json` (say how old that data is).
- If `open_positions` is `null` (never read) and the user has not said there are none:
  the open risk is unknown -> no trade. Ask for the Trade tab.
- For each open position with a stop, its risk is `risk` from
  `calc.py --symbol .. --side .. --entry OPEN_PRICE --stop STOP --lots VOLUME`
  plus that symbol's specification flags. A position whose stop is already on the profit
  side of its open price has zero risk.
- **List every open position that has no stop**, as a warning. Its risk is not bounded and
  is not in the sum; say that the sum is therefore a lower bound.
- The check: `open risk + new risk <= balance * max_open_risk_pct / 100`. Compute it with
  `python3 -c` using `decimal.Decimal`, and show the numbers. If it fails -> no trade.

## Step 6 - Save, then answer

1. Append the journal row (for `OK` and for no trade). The script prints the ticket id and
   the ticket file name:

   ```bash
   python3 .claude/skills/result/journal.py add \
     --symbol EURUSD --verdict OK --side sell --type "Sell Limit" \
     --entry 1.1098 --stop 1.1108 --target 1.1078 --lots 0.01 \
     --risk 1.00 --reward-risk 2.00 --scenario-estimate 55
   ```

   For no trade use `--verdict NO_TRADE` and pass only the values that exist.

2. Write the ticket file named by the script (`tickets/YYYY-MM-DD_HHMM_SYMBOL.md`): the
   same content as the answer, plus the commands that were run and the report file names.
3. If the images came from `inbox/`, move them to `inbox/processed/YYYY-MM-DD_HHMM/`.
4. Answer in Arabic with the matching template below. One block per symbol.

### Template - ticket (`OK`)

````markdown
**القرار:** توجد صفقة مقترحة للحساب التجريبي. لم يُنفَّذ أي أمر.

**التذكرة (تُنسخ يدوياً):**

```
Symbol:      EURUSD
Type:        Sell Limit
Volume:      0.01
Price:       1.1098
Stop Loss:   1.1108
Take Profit: 1.1078
```

**الأرقام (محسوبة بالسكربت):**

```
Ticket id:          7
Risk:               1.00 USD (0.98%)
Reward:             2.00 USD
Reward:Risk:        2.00
Breakeven win rate: 33.3%
Margin:             73.99 USD
Free margin after:  28.01 USD
Open risk after:    1.00 USD of 6.12 USD allowed
```

**تحذيرات:**
- (كل تحذير في سطر. إن لم يوجد: لا توجد.)

**دليل: ما قرأته من الصور**

(القوائم من الخطوة الثانية)

**دليل: ما حسبه السكربت**

(الأمر الذي نُفِّذ في مربع كود)

**رأي: تقديري وليس قياساً**

(سطران أو ثلاثة: الاتجاه، مستوى الدخول، مستوى الإبطال، ثم التقدير في مربع كود)

```
Base scenario estimate: 55% (an estimate, not a measured statistic)
```

**تذكير:**
- أمر الوقف قد يُنفَّذ بسعر أسوأ من سعره.
- لم أضع أي أمر. أنت من يُدخل الأمر بيدك.
- حساب تجريبي فقط، وهذه ليست نصيحة مالية.
````

### Template - no trade

````markdown
**القرار:** لا صفقة.

**السبب:**
(البوابة التي فشلت أو خطأ الحاسبة، بجملة عربية قصيرة، ثم الأرقام في مربع كود)

```
Failed:             MARGIN_EXCEEDS_FREE_MARGIN
Margin needed:      74.00 USD
Free margin:        26.73 USD
Free margin after:  -47.27 USD
```

**ما الذي يجب أن يتغيّر:**
(مثال: الهامش الحر المطلوب، أو أبعد وقف ممكن عند أصغر حجم، في مربع كود)

```
Free margin needed:      74.00 USD
Widest stop at min lot:  3988.02
```

**دليل: ما قرأته من الصور**

**دليل: ما حسبه السكربت**

**رأي: تقديري وليس قياساً**

**تذكير:**
- "لا صفقة" نتيجة صحيحة. لن أرفع نسبة المخاطرة لإخراج تذكرة.
- لم أضع أي أمر. حساب تجريبي فقط، وهذه ليست نصيحة مالية.
````

Rules for the answer:

- `widest_stop_at_min_lot` is information for the user. Do not move the stop to it
  yourself: a stop inside the invalidation level fails gate 4.
- Never raise the risk percent, and never suggest a number to raise it to.
- Keep Arabic sentences free of Latin letters and prices. If a sentence needs a symbol or
  a price, end the sentence and put the value in a code block on its own line.
- If the specification is unconfirmed, or the highest timeframe is not W1, the warning
  list must say so.
