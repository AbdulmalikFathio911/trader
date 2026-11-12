#!/usr/bin/env python3
"""Build ui/index.html: one self-contained page.

Inputs: ui/index.src.html, ui/vendor/decimal.js, ui/calc.js, ui/app.js and the
repository's skill files (SKILL_FILES below). The skill files are embedded verbatim, so
the page's image analysis reads the same rules and method as the /trade skill.

The build is deterministic: the same inputs give the same file. tests/test_ui.py fails
when ui/index.html is stale, so rebuild after changing any input, then republish the page.

Run from the repository root:
    python3 ui/build.py
Standard library only. The page loads nothing from the network.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPOSITORY = "github.com/AbdulmalikFathio911/trader"

# The brain of the image analysis, in the order it is given to the model.
SKILL_FILES = [
    "CLAUDE.md",
    ".claude/skills/trade/SKILL.md",
    ".claude/skills/account/SKILL.md",
    ".claude/skills/technical-analyst/SKILL.md",
    ".claude/skills/technical-analyst/references/technical_analysis_framework.md",
    ".claude/skills/technical-analyst/assets/analysis_template.md",
    ".claude/skills/mt5-lot-calculator/SKILL.md",
    ".claude/skills/position-sizer/SKILL.md",
    ".claude/skills/position-sizer/references/sizing_methodologies.md",
]
SCRIPTS = [
    ("/*__DECIMAL_JS__*/", "vendor/decimal.js"),
    ("/*__CALC_JS__*/", "calc.js"),
    ("/*__APP_JS__*/", "app.js"),
]
MAX_SKILL_BYTES = 200 * 1024   # the page may send at most 256 KiB of text to the model


def skills_json():
    files = []
    digest = hashlib.sha256()
    for name in SKILL_FILES:
        path = ROOT / name
        if not path.is_file():
            raise SystemExit(f"skill file missing: {name}")
        text = path.read_text(encoding="utf-8")
        digest.update(name.encode("utf-8") + b"\0" + text.encode("utf-8") + b"\0")
        files.append({"path": name, "text": text})
    total = sum(len(f["text"].encode("utf-8")) for f in files)
    if total > MAX_SKILL_BYTES:
        raise SystemExit(f"skill files are {total} bytes, over the {MAX_SKILL_BYTES} byte budget")
    data = {"repo": REPOSITORY, "skills_sha": digest.hexdigest()[:12], "files": files}
    # "<" is escaped so no file text can close the script element that carries the JSON.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def build():
    """Return the text of the built page."""
    page = (HERE / "index.src.html").read_text(encoding="utf-8")
    parts = [("/*__SKILLS_JSON__*/", skills_json())]
    for marker, name in SCRIPTS:
        source = (HERE / name).read_text(encoding="utf-8")
        if "</script" in source.lower():
            raise SystemExit(f"{name} contains a closing script tag and cannot be inlined")
        parts.append((marker, "\n" + source))
    for marker, _ in parts:
        if page.count(marker) != 1:
            raise SystemExit(f"marker {marker} must appear exactly once in index.src.html")
    for marker, text in parts:
        page = page.replace(marker, text)
    return page


def main():
    page = build()
    (HERE / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote ui/index.html ({len(page.encode('utf-8'))} bytes, {len(SKILL_FILES)} skill files)")


if __name__ == "__main__":
    main()
