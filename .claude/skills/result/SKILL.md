---
name: result
description: Record the outcome of a trade desk ticket by id (win, loss or cancelled, with the profit or loss) in journal.csv, then print the statistics - closed trades, win rate, average reward:risk, total profit or loss, and win rate next to the breakeven rate. Use when the user types /result.
argument-hint: "<id> win|loss|cancelled [profit or loss]"
---

# /result

Record what happened to a ticket, then show the numbers. All arithmetic is done by
`journal.py`.

## Hard rules (from `CLAUDE.md` - they override everything below)

1. No external APIs or services. The only inputs are what the user types or shows.
2. Never place, modify or close an order. Never ask for or store passwords.
3. Never promise a win and never read a trend into a small sample. The statistics describe
   past tickets only.
4. Demo account only. Not financial advice.
5. Answer in Arabic, short and simple. Ids, symbols, numbers and commands go in code
   blocks on their own lines, never inside an Arabic sentence.
6. The statistics are evidence (computed by the script). Any comment on them is opinion
   and must be labelled as opinion.
7. Never guess the profit or loss. If the user did not type it, or it cannot be read from
   a screenshot they attached, say it is missing and record nothing.

## Usage

```
/result 7 win 2.00
/result 8 loss -1.00
/result 9 cancelled
/result
```

- `win`: the profit, a positive number. `loss`: the loss (stored as a negative number).
  `cancelled`: the pending order was removed before it filled; no amount.
- With no arguments: only print the statistics.
- If the id is missing or not in `journal.csv`, show the open tickets (rows with verdict
  `OK` and an empty result) and record nothing.

## Steps

1. Record the outcome:

   ```bash
   python3 .claude/skills/result/journal.py result --id 7 --result win --pnl 2.00
   ```

   For statistics only:

   ```bash
   python3 .claude/skills/result/journal.py stats
   ```

2. If the script prints `"ok": false`, show its error message and stop. Do not edit
   `journal.csv` by hand.
3. Answer with the template. Copy the numbers from the script's `stats` object.

## Answer template

````markdown
**تم تسجيل النتيجة.**

```
Ticket id:  7
Symbol:     EURUSD
Result:     win
P/L:        2.00
```

**الإحصاءات (محسوبة بالسكربت):**

```
Closed trades:       3
Wins / Losses:       1 / 2
Cancelled:           1
Win rate:            33.3%
Breakeven win rate:  33.3%
Average reward:risk: 2.00
Total P/L:           0.00
```

**ملاحظة:** العيّنة أقل من ثلاثين صفقة مغلقة، فهي أصغر من أن تدلّ على شيء.

**تذكير:** حساب تجريبي فقط، وهذه ليست نصيحة مالية.
````

Rules for the answer:

- Show the win rate next to the breakeven win rate, as in the template. The breakeven
  rate is `100 / (1 + average reward:risk)` of the closed trades.
- When `sample_too_small` is `true` (fewer than 30 closed trades), always include the
  small-sample note and draw no conclusion from the numbers.
- When there are no closed trades, the rates are `n/a`.
- Closed trades are tickets with result `win` or `loss`. Cancelled tickets and "no trade"
  rows are not counted in the rates.
