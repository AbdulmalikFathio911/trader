"""Tests for .claude/skills/result/journal.py (uses a temporary journal file)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / ".claude" / "skills" / "result" / "journal.py"
HEADER = ("id,time,symbol,side,type,entry,stop,target,lots,risk,reward_risk,"
          "scenario_estimate,verdict,result,pnl")


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "journal.csv"
        self.file.write_text(HEADER + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_journal(self, *flags):
        proc = subprocess.run(
            [sys.executable, str(JOURNAL), "--file", str(self.file), *flags],
            capture_output=True, text=True, check=False,
        )
        return proc.returncode, json.loads(proc.stdout)

    def add_ok(self, reward_risk="2.00"):
        code, out = self.run_journal(
            "add", "--symbol", "EURUSD", "--verdict", "OK", "--side", "sell",
            "--type", "Sell Limit", "--entry", "1.1098", "--stop", "1.1108",
            "--target", "1.1078", "--lots", "0.01", "--risk", "1.00",
            "--reward-risk", reward_risk, "--scenario-estimate", "55",
            "--time", "2026-11-12 21:30",
        )
        self.assertEqual(code, 0)
        return out

    def test_repo_journal_has_the_expected_header(self):
        first_line = (ROOT / "journal.csv").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, HEADER)

    def test_add_assigns_ids_and_ticket_file(self):
        first = self.add_ok()
        second = self.add_ok()
        self.assertEqual((first["id"], second["id"]), (1, 2))
        self.assertEqual(first["ticket_file"], "tickets/2026-11-12_2130_EURUSD.md")
        lines = self.file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], HEADER)
        self.assertEqual(
            lines[1],
            "1,2026-11-12 21:30,EURUSD,sell,Sell Limit,1.1098,1.1108,1.1078,0.01,1.00,2.00,55,OK,,",
        )

    def test_result_and_stats(self):
        for _ in range(4):
            self.add_ok()
        self.run_journal("result", "--id", "1", "--result", "win", "--pnl", "2.00")
        self.run_journal("result", "--id", "2", "--result", "loss", "--pnl", "-1.00")
        self.run_journal("result", "--id", "3", "--result", "loss", "--pnl", "1.00")
        code, out = self.run_journal("result", "--id", "4", "--result", "cancelled")
        self.assertEqual(code, 0)
        stats = out["stats"]
        self.assertEqual(stats["closed_trades"], 3)
        self.assertEqual((stats["wins"], stats["losses"], stats["cancelled"]), (1, 2, 1))
        self.assertEqual(stats["win_rate_pct"], "33.3")
        self.assertEqual(stats["avg_reward_risk"], "2.00")
        self.assertEqual(stats["breakeven_win_rate_pct"], "33.3")
        self.assertEqual(stats["total_pnl"], "0.00")
        self.assertTrue(stats["sample_too_small"])

    def test_sample_is_large_enough_at_thirty_closed_trades(self):
        for index in range(1, 31):
            self.add_ok()
            self.run_journal("result", "--id", str(index), "--result", "win", "--pnl", "2")
        _, out = self.run_journal("stats")
        self.assertEqual(out["stats"]["closed_trades"], 30)
        self.assertFalse(out["stats"]["sample_too_small"])

    def test_no_trade_row_cannot_get_a_result(self):
        self.run_journal("add", "--symbol", "XAUUSD", "--verdict", "NO_TRADE")
        code, out = self.run_journal("result", "--id", "1", "--result", "win", "--pnl", "5")
        self.assertEqual(code, 2)
        self.assertFalse(out["ok"])

    def test_unknown_id_and_bad_win_amount_fail(self):
        self.add_ok()
        code, _ = self.run_journal("result", "--id", "9", "--result", "win", "--pnl", "1")
        self.assertEqual(code, 2)
        code, _ = self.run_journal("result", "--id", "1", "--result", "win", "--pnl", "-1")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
