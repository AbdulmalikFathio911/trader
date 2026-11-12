# Third-party material

Two skills in this repository are copied from an open-source project. Everything else was
written for this repository.

## claude-trading-skills

- Source: https://github.com/tradermonty/claude-trading-skills
- Commit copied: `4251eaaeb05d720f5ffe8e899e3b6ec1cf48e96f`
- License: MIT, Copyright (c) 2026 TraderMonty (full text below)

### Files copied

| Source path | Path in this repository | Changed? |
|-------------|-------------------------|----------|
| `skills/technical-analyst/SKILL.md` | `.claude/skills/technical-analyst/SKILL.md` | yes, see below |
| `skills/technical-analyst/references/technical_analysis_framework.md` | `.claude/skills/technical-analyst/references/technical_analysis_framework.md` | no |
| `skills/technical-analyst/assets/analysis_template.md` | `.claude/skills/technical-analyst/assets/analysis_template.md` | no |
| `skills/position-sizer/SKILL.md` | `.claude/skills/position-sizer/SKILL.md` | yes, see below |
| `skills/position-sizer/scripts/position_sizer.py` | `.claude/skills/position-sizer/scripts/position_sizer.py` | no |
| `skills/position-sizer/references/sizing_methodologies.md` | `.claude/skills/position-sizer/references/sizing_methodologies.md` | no |

Nothing else from that repository was copied. In particular the technical-analyst data
scripts (`scripts/check_weekly_price_action.py`, `scripts/weekly_price_action.py`), their
tests, `references/contrarian-confirmation-checklist.md` and both `requirements.txt` files
were left out: the data scripts need a paid market-data API, and this project uses no
external services.

### Changes made here

`technical-analyst/SKILL.md`

- Added a local note at the top: the method is written for weekly charts; on any other
  timeframe say so and treat the result as weaker; the project's hard rules apply; report
  file naming for several timeframes.
- Removed the "Contrarian Confirmation Mode (Shapiro Step 3)" section.
- Removed the two entries in "Resources" that described files that were not copied
  (`references/contrarian-confirmation-checklist.md`, `scripts/check_weekly_price_action.py`).

`position-sizer/SKILL.md`

- Added a local note at the top: long stock trades only; for forex, gold, CFDs, sells,
  lots or margin use `mt5-lot-calculator`; the project's hard rules apply.
- Changed the command paths from `skills/position-sizer/...` to
  `.claude/skills/position-sizer/...`.

`position-sizer/references/sizing_methodologies.md` is unchanged, so the one command in it
still shows the original `skills/position-sizer/...` path.

### License

```
MIT License

Copyright (c) 2026 TraderMonty

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
