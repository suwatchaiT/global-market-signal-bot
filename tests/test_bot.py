from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import sys
import types

import pandas as pd

# Unit tests exercise feed transformations without making Yahoo network calls.
sys.modules.setdefault("yfinance", types.SimpleNamespace(download=None))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

import data_feed
import journal
import risk
from signals import Signal


class DataFeedTests(unittest.TestCase):
    def test_incomplete_candle_is_removed(self):
        now = pd.Timestamp(datetime.now(timezone.utc)).floor("h")
        df = pd.DataFrame({"time": [now - pd.Timedelta(hours=1), now], "close": [1, 2]})
        self.assertEqual(len(data_feed._closed_only(df, "H1")), 1)


class RiskTests(unittest.TestCase):
    @patch("config.ACCOUNT_BALANCE", 10_000)
    @patch("config.RISK_PERCENT", 1)
    def test_eurusd_one_percent_risk(self):
        money, units, lots = risk.estimate("EURUSD", 1.1000, 1.0950)
        self.assertAlmostEqual(money, 100)
        self.assertAlmostEqual(units, 20_000)
        self.assertAlmostEqual(lots, 0.2)


class JournalTests(unittest.TestCase):
    def test_take_profit_records_win(self):
        state: dict = {}
        signal = Signal(
            "EURUSD", "MA_CROSS", "BUY", "test", price=1.1,
            candle_time="2026-01-01T00:00:00+00:00", sl=1.09, tp=1.12, rr=2,
        )
        journal.record(state, signal)
        df = pd.DataFrame([{
            "time": "2026-01-01T01:00:00+00:00", "open": 1.1,
            "high": 1.121, "low": 1.099, "close": 1.12,
        }])
        journal.evaluate(state, "EURUSD", df)
        self.assertEqual(state["signal_journal"][0]["status"], "WIN")
        self.assertAlmostEqual(state["signal_journal"][0]["r_multiple"], 2)

    def test_both_levels_in_one_candle_is_conservative_loss(self):
        state: dict = {}
        signal = Signal(
            "EURUSD", "MA_CROSS", "BUY", "test", price=1.1,
            candle_time="2026-01-01T00:00:00+00:00", sl=1.09, tp=1.12,
        )
        journal.record(state, signal)
        df = pd.DataFrame([{
            "time": "2026-01-01T01:00:00+00:00", "open": 1.1,
            "high": 1.13, "low": 1.08, "close": 1.11,
        }])
        journal.evaluate(state, "EURUSD", df)
        self.assertEqual(state["signal_journal"][0]["status"], "LOSS")


if __name__ == "__main__":
    unittest.main()
