---
name: account
description: Update data/account.json from an MT5 Trade tab screenshot or typed numbers, and data/symbols.json from a symbol's Specification screenshot, then show before and after. Use when the user types /account, or when /trade receives a Trade tab or Specification screenshot.
argument-hint: "[typed numbers, e.g. balance 150 free margin 150]"
---

# /account

Keep the two data files in step with what MT5 shows. Nothing else is touched.

## Hard rules (from `CLAUDE.md` - they override everything below)

1. No external APIs or services. Inputs are only the user's screenshots and typed numbers.
2. Never place, modify or close an order. **Never ask for, read out or store a password,
   login, account number or server name**, even if one is visible in a screenshot.
3. Never loosen a risk rule. `risk_pct`, `max_open_risk_pct`, `max_position_pct`,
   `max_daily_losses` and `news_lock_until` change only when the user types the new value
   in this message. Never suggest raising a limit or clearing the news lock.
4. Demo account only. Not financial advice.
5. Answer in Arabic, short and simple. Field names, symbols, numbers and commands go in
   code blocks on their own lines, never inside an Arabic sentence.
6. Say for each value whether it was read from a screenshot or typed by the user.
7. Never guess a number you cannot read. Keep the old value and say the field is missing.

## Inputs

- A **Trade tab** screenshot, and/or typed numbers -> `data/account.json`.
- A **Specification** screenshot of one symbol -> `data/symbols.json`.
- Images attached to the message, or image files in `inbox/`.

If there is neither a usable screenshot nor a typed number, show the current files and
say what is needed.

## Steps

1. Read `data/account.json` and `data/symbols.json` and keep the old values.
2. Read each screenshot. Copy numbers exactly as displayed; anything cut off or blurred is
   missing.
3. Update only the fields you actually read or the user typed.
4. Write the files with 2-space indentation and check them:

   ```bash
   python3 -m json.tool data/account.json > /dev/null && python3 -m json.tool data/symbols.json > /dev/null && echo valid
   ```

5. Answer with the template below.

### `data/account.json` from the Trade tab

| MT5 Trade tab | Field |
|---------------|-------|
| Balance | `balance` |
| Free margin | `free_margin` |
| Account currency shown next to the balance | `currency` |
| Each open position | one item in `open_positions` |

- Each `open_positions` item: `symbol`, `side`, `lots`, `open_price`, `stop` (or `null`
  when the position has no stop), `target` (or `null`). If the tab shows no positions,
  write an empty list `[]`. Only write `[]` when the whole positions area is visible.
- Equity, margin and margin level may be shown to the user but are not stored.
- The Trade tab does not show leverage. `leverage` changes only when the user types it.
- Set `updated_at` to the current UTC time and `source` to `"Trade tab screenshot"`,
  `"typed by the user"` or both.
- If the screenshot is from a real (non-demo) account, do not change `account_type`; say
  that this desk is for a demo account only.
- List every open position that has no stop as a warning.

### `data/symbols.json` from a Specification screenshot

| MT5 Specification | Field |
|-------------------|-------|
| Symbol name (title) | the key |
| Digits | `digits` |
| Contract size | `contract_size` |
| Minimal volume | `min_lot` |
| Volume step | `lot_step` |
| Stops level | `stops_level` |
| Calculation: Forex | `calc_mode`: `forex` |
| Calculation: CFD Leverage | `calc_mode`: `cfd_leverage` |
| Calculation: CFD | `calc_mode`: `cfd` |
| Calculation: Exchange Stocks | `calc_mode`: `stocks` |
| Profit currency | `quote_currency` |

- Any other Calculation type (Futures, Exchange Futures, CFD Index, Forex No Leverage ...)
  is out of scope: store `"calc_mode": null` and `"supported": false`, and say that
  `/trade` will refuse this symbol.
- `"confirmed": true` only when the symbol name, Digits, Contract size, Minimal volume,
  Volume step and Calculation were **all read from the Specification screenshot** in this
  run. Then set `source` to `"Specification screenshot"` and `updated_at` to the current
  UTC time.
- Typed numbers may update a symbol, but they never set `"confirmed": true`.
- If the profit currency differs from the account currency, set `quote_to_account` to
  `null` and say that the user must type the conversion rate; `/trade` cannot size that
  symbol without it.
- `leverage` for a symbol is stored only if the user types it or the screenshot states it
  as a leverage ratio. Do not convert margin percentages yourself.

## Answer template

````markdown
**تم تحديث بيانات الحساب.** (أو: لم يتغيّر شيء.)

**قبل:**

```
balance:      102
free_margin:  26.73
```

**بعد:**

```
balance:      150
free_margin:  150
```

**المصدر:** (من لقطة الشاشة / كتبه المستخدم)

**ناقص:** (الحقول التي لم أستطع قراءتها. إن لم يوجد: لا شيء.)

**تحذيرات:** (مثال: مركز مفتوح بلا وقف، أو رمز غير مدعوم)
````

Show only the fields that changed, plus every field that was requested but is missing.
For a symbol, show the whole entry before and after, and its `confirmed` state.
