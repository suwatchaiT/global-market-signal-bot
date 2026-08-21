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
sys.modules.setdefault(
    "requests",
    types.SimpleNamespace(
        get=None,
        post=None,
        RequestException=Exception,
        exceptions=types.SimpleNamespace(RequestException=Exception),
    ),
)

import data_feed
import config
import journal
import risk
import check_once
from signals import Signal


class DataFeedTests(unittest.TestCase):
    def test_incomplete_candle_is_removed(self):
        now = pd.Timestamp(datetime.now(timezone.utc)).floor("h")
        df = pd.DataFrame({"time": [now - pd.Timedelta(hours=1), now], "close": [1, 2]})
        self.assertEqual(len(data_feed._closed_only(df, "H1")), 1)

    def test_requested_index_mappings(self):
        self.assertEqual(data_feed.yahoo_ticker("THAISET"), "^SET.BK")
        self.assertEqual(data_feed.yahoo_ticker("US500"), "^GSPC")
        self.assertEqual(data_feed.yahoo_ticker("NAS100"), "^NDX")
        self.assertEqual(data_feed.yahoo_ticker("NIKKEI225"), "^N225")
        self.assertEqual(data_feed.yahoo_ticker("SHANGHAI"), "000001.SS")


class AlertWindowTests(unittest.TestCase):
    def test_default_active_market_windows(self):
        self.assertEqual(
            (config.ALERT_START_HOUR, config.ALERT_START_MINUTE,
             config.ALERT_END_HOUR, config.ALERT_END_MINUTE),
            (8, 30, 17, 0),
        )
        self.assertEqual(
            (config.US_ALERT_START_HOUR, config.US_ALERT_START_MINUTE,
             config.US_ALERT_END_HOUR, config.US_ALERT_END_MINUTE),
            (20, 0, 23, 0),
        )

    def test_daytime_window(self):
        self.assertFalse(check_once._minute_in_window(8 * 60 + 29, 8 * 60 + 30, 17 * 60))
        self.assertTrue(check_once._minute_in_window(8 * 60 + 30, 8 * 60 + 30, 17 * 60))
        self.assertTrue(check_once._minute_in_window(17 * 60, 8 * 60 + 30, 17 * 60))
        self.assertFalse(check_once._minute_in_window(17 * 60 + 1, 8 * 60 + 30, 17 * 60))

    def test_overnight_window_wraps_midnight(self):
        self.assertTrue(check_once._minute_in_window(22 * 60, 20 * 60, 4 * 60))
        self.assertTrue(check_once._minute_in_window(2 * 60, 20 * 60, 4 * 60))
        self.assertFalse(check_once._minute_in_window(12 * 60, 20 * 60, 4 * 60))


class RiskTests(unittest.TestCase):
    @patch("config.ACCOUNT_BALANCE", 10_000)
    @patch("config.RISK_PERCENT", 1)
    def test_eurusd_one_percent_risk(self):
        money, units, lots = risk.estimate("EURUSD", 1.1000, 1.0950)
        self.assertAlmostEqual(money, 100)
        self.assertAlmostEqual(units, 20_000)
        self.assertAlmostEqual(lots, 0.2)

    def test_index_lot_size_is_suppressed(self):
        money, units, lots = risk.estimate("US500", 6000, 5950)
        self.assertGreater(money, 0)
        self.assertEqual(units, 0)
        self.assertEqual(lots, 0)


class JournalTests(unittest.TestCase):
    def test_duplicate_signal_ids_are_recorded_once(self):
        state: dict = {}
        signal = Signal(
            "THAISET", "RSI", "SELL", "test", price=1200,
            candle_time="2026-08-07T16:00:00+07:00", sl=1210, tp=1180,
            stars=2,
        )
        journal.record(state, signal)
        journal.record(state, signal)
        self.assertEqual(len(journal.records(state)), 1)
        self.assertTrue(journal.contains(state, signal))
        self.assertEqual(journal.records(state)[0]["stars"], 2)

    def test_existing_duplicate_rows_are_compacted(self):
        row = {"id": "EURUSD|BUY|same-candle", "status": "LOSS"}
        state = {"signal_journal": [dict(row), dict(row), dict(row)]}
        self.assertEqual(journal.deduplicate(state), 2)
        self.assertEqual(len(journal.records(state)), 1)

    def test_performance_table_contains_signal_details(self):
        state = {"signal_journal": [{
            "symbol": "EURUSD", "direction": "BUY", "signal_type": "MA_CROSS",
            "opened_at": "2026-01-01T00:00:00+00:00", "closed_at": "2026-01-01T02:00:00+00:00",
            "entry": 1.1, "sl": 1.09, "tp": 1.12, "status": "WIN", "r_multiple": 2.0,
        }]}
        table = journal.performance_table(state)
        self.assertIn("EURUSD BUY", table)
        self.assertIn("WIN (+2.0R)", table)
        self.assertIn("Entry 1.10000", table)
        self.assertIn("Closed 01/01 09:00", table)

    def test_performance_table_caps_rows_at_twenty(self):
        row = {
            "symbol": "BTCUSD", "direction": "BUY", "signal_type": "RSI",
            "opened_at": "2026-01-01T00:00:00+00:00", "entry": 1,
            "sl": 0.9, "tp": 1.2, "status": "OPEN",
        }
        table = journal.performance_table({"signal_journal": [dict(row) for _ in range(25)]}, 99)
        self.assertIn("newest 20", table)
        self.assertNotIn("<b>21.", table)

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
