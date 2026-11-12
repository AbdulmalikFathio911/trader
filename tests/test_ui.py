"""Tests for the page in ui/.

Run from the repository root:
    python3 -m unittest discover -s tests -v
"""

import importlib.util
import json
import re
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load("ui_build", UI / "build.py")


class TestBuiltPage(unittest.TestCase):
    def test_index_html_is_up_to_date(self):
        """A stale page means the analysis reads old skill files: rebuild with ui/build.py."""
        self.assertEqual(
            (UI / "index.html").read_text(encoding="utf-8"),
            build.build(),
            "ui/index.html is stale: run python3 ui/build.py, then republish the page",
        )

    def test_page_embeds_every_skill_file_verbatim(self):
        page = (UI / "index.html").read_text(encoding="utf-8")
        match = re.search(r'<script type="application/json" id="skill-files">(.*?)</script>', page, re.S)
        self.assertIsNotNone(match, "the embedded skill files are missing")
        data = json.loads(match.group(1))
        embedded = {item["path"]: item["text"] for item in data["files"]}
        self.assertEqual(list(embedded), build.SKILL_FILES)
        for name in build.SKILL_FILES:
            self.assertEqual(embedded[name], (ROOT / name).read_text(encoding="utf-8"), name)

    def test_page_sources_load_nothing_from_the_network(self):
        for name in ("index.src.html", "calc.js", "app.js"):
            text = (UI / name).read_text(encoding="utf-8")
            for needle in ("http://", "https://", "fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon"):
                self.assertNotIn(needle, text, f"{name} contains {needle}")

    def test_page_has_no_login_or_order_sending(self):
        """The page only calculates: no password field, no broker or order-sending code."""
        markup = (UI / "index.src.html").read_text(encoding="utf-8").lower()
        self.assertNotIn('type="password"', markup)
        code = (UI / "app.js").read_text(encoding="utf-8").lower()
        for needle in ("ordersend", "order_send", "metatrader5", "mt5.initialize"):
            self.assertFalse(needle in code, f"app.js contains {needle}")


class TestInstalledApp(unittest.TestCase):
    """The files that let the page be installed as an app when it is served on its own."""

    def test_manifest_icons_exist(self):
        manifest = json.loads((UI / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["display"], "standalone")
        self.assertTrue(manifest["icons"])
        for icon in manifest["icons"]:
            self.assertTrue((UI / icon["src"]).is_file(), icon["src"])

    def test_page_links_the_manifest_and_icons(self):
        page = (UI / "index.html").read_text(encoding="utf-8")
        for name in ("manifest.json", "icons/icon-192.png", "icons/apple-touch-icon-180.png"):
            self.assertIn(f'href="{name}"', page)
            self.assertTrue((UI / name).is_file(), name)

    def test_offline_worker_saves_only_files_that_exist(self):
        worker = (UI / "sw.js").read_text(encoding="utf-8")
        files = re.search(r"const FILES = \[(.*?)\];", worker, re.S).group(1)
        for name in re.findall(r"'([^']+)'", files):
            if name != "./":
                self.assertTrue((UI / name).is_file(), name)
        self.assertNotIn("http", worker.replace("https:", ""))


@unittest.skipUnless(shutil.which("node"), "node is not installed: calc.js parity not checked")
class TestCalcParity(unittest.TestCase):
    """ui/calc.js must give the same numbers as calc.py."""

    @classmethod
    def setUpClass(cls):
        cls.crosscheck = load("ui_crosscheck", UI / "tests" / "crosscheck.py")

    def test_calc_js_matches_calc_py(self):
        count, problems = self.crosscheck.compare(random_cases=120)
        self.assertGreater(count, 120)
        self.assertEqual(problems, [], "\n".join(problems[:5]))

    def test_share_count_matches_position_sizer(self):
        self.assertEqual(self.crosscheck.compare_shares(), [])


if __name__ == "__main__":
    unittest.main()
