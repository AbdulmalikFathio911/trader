---
name: backtest
description: Replay the trade desk's mechanical rules on price bars exported from MetaTrader 5 and report, in Arabic, whether they showed an edge in the past - trades, win rate against the breakeven rate, expectancy in R, drawdown, an out-of-sample part and a coin-flip comparison. Also prints what the rules say after the last bar. Use when the user types /backtest, attaches or drops an exported bars file, or asks whether the method has been tested on history.
argument-hint: "[file in inbox/] [now]"
---

# /backtest

Exported bars in, a measured answer out. `backtest.py` does all the arithmetic. It reads a
file the user exported by hand: there is no data feed.

## Hard rules (from `CLAUDE.md` - they override everything below)

1. No external APIs or services and no market-data download. The only input is the bars
   file the user exported from MetaTrader 5. Python standard library only.
2. Never place, modify or close an order. Never ask for or store passwords or logins.
3. A past result is not a promise. Never call a result proof that the method wins, never
   turn it into a win probability for the next trade, and never change the settings until
   the result looks good: that is fitting the test to the past.
4. Demo account only. Not financial advice.
5. Answer in Arabic, short and simple. English identifiers, symbols, numbers with units
   and commands go in code blocks on their own lines, never inside an Arabic sentence.
6. The script's output is evidence. Any comment on it is opinion and is labelled as opinion.
7. Never guess a number. If the file cannot be read, say what is wrong and stop.

## What it tests, and what it does not

It tests a fixed, mechanical version of the `/trade` gates:

| Gate | In `/trade` | In the backtest |
|------|-------------|-----------------|
| 1 Direction | Base scenario of the highest timeframe | Last two swing highs and last two swing lows: both higher is up, both lower is down, anything else is no trade |
| 3 Entry | A support or resistance named in the analysis | Pending order at the nearest swing level against the price |
| 4 Stop | Beyond the invalidation level | Beyond the next swing level, plus the spread |
| 5 Target | Next level in the trade direction | Nearest swing level in the trade direction |
| 6 Reward:risk | 1.5 or more | The same number (`--min-rr`) |

It does **not** test gate 2 (the model's estimate), the model's reading of a chart, more
than one timeframe, or news. So the result describes the rule skeleton on one timeframe,
not the full `/trade` answer. Say this in every answer.

## Step 1 - Get the bars

The user exports them from MetaTrader 5 on a computer (the phone app cannot export):

```
View > Symbols > Bars
```

Choose the symbol, the timeframe and the dates, press `Request`, then `Export Bars`. The
file is tab separated and starts with `<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE>`.

- Use the file attached to the message, or the newest `.csv` in `inbox/`.
- At least 200 bars are needed. For a reading the out-of-sample part needs 30 trades or
  more, which usually means several thousand bars. If the label is `TOO_FEW_TRADES`, ask
  for a longer export instead of lowering a setting.
- The symbol and the timeframe are not inside the file. Take them from the file name or
  ask; do not guess.

## Step 2 - Run it

```bash
python3 .claude/skills/backtest/backtest.py --csv inbox/EURUSD_H1.csv --spread 0.00010 --no-trades
```

- `--spread`: the cost of one trade in price units, from the symbol's Specification or a
  quote the user typed. With `0` the result is before costs: say so.
- Leave the other settings at their defaults. Run the test **once** per file. Do not try
  several settings and report the best one.
- Show the command. Exit code `2` means the file is wrong: report `errors` and stop.

What the rules say after the last bar of the same file (no test):

```bash
python3 .claude/skills/backtest/backtest.py --csv inbox/EURUSD_H1.csv --now
```

`/trade` may show this next to its chart reading as a number check. It is never a ticket,
and it is only as fresh as the last bar in the file: show `last_bar`.

## Step 3 - Read the result

`reading` is the label to report. It describes this sample only.

| `reading` | Meaning | Say |
|-----------|---------|-----|
| `TOO_FEW_TRADES` | Under 30 trades in the out-of-sample part | No conclusion. A longer export is needed. |
| `NO_EDGE_SHOWN` | Out-of-sample expectancy is zero or negative | The rules lost or broke even after costs in this sample. |
| `NOT_BETTER_THAN_CHANCE` | Positive, but 5 percent or more of coin-flip runs did as well | The profit can be explained by luck. |
| `POSITIVE_IN_THIS_SAMPLE` | Positive, and under 5 percent of coin-flip runs did as well | Positive in this sample. On pure noise this label still appears about 1 time in 20, so one positive test is weak evidence. |

How to read the numbers:

- `expectancy_r`: average result per trade in units of risk. `0.20` means 0.20 of the
  risked amount per trade on average, before any promise about the future.
- `win_rate_pct` against `breakeven_win_rate_pct`: winning less often than the breakeven
  rate loses money whatever the win rate looks like.
- `in_sample` against `out_of_sample`: the first 70 percent of the bars and the last 30
  percent. A good first part with a bad last part is a warning.
- `random_direction_baseline_out_of_sample`: the same trades at the same times with the
  direction chosen by a coin, entered at the close of the fill bar.
- When one bar touches the stop and the target, the stop is counted.

## Step 4 - Answer

Save the JSON as `reports/backtest_[SYMBOL]_[TIMEFRAME]_[YYYY-MM-DD].json`, then answer:

````markdown
**النتيجة:** وصف من سطر واحد حسب التصنيف. هذا اختبار على الماضي وليس وعداً.

**الدليل (من السكربت):**

```
File:           EURUSD_H1.csv
Bars:           9000
From:           2025.01.02 00:00
To:             2026.06.30 23:00
Reading:        NO_EDGE_SHOWN
```

الجزء الأخير من البيانات (خارج العينة):

```
Trades:         49
Win rate:       30.6 %
Breakeven rate: 21.4 %
Expectancy:     -0.12 R
Max drawdown:   7.44 R
Coin flip:      44.0 % of runs as good
```

كل البيانات:

```
Trades:         171
Expectancy:     0.03 R
```

**ما الذي لم يُختبر:** قراءة النموذج للشارت، تقدير السيناريو، تعدد الفريمات، والأخبار.

**رأيي (ليس دليلاً):** جملة أو جملتان.

**الأمر الذي شُغّل:**

```
python3 .claude/skills/backtest/backtest.py --csv inbox/EURUSD_H1.csv --spread 0.00010 --no-trades
```

حساب تجريبي فقط. ليست نصيحة مالية.
````
