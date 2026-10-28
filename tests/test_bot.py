from __future__ import annotations

import unittest
from datetime import date, datetime, time, timezone
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
import index_report
import notifier
import risk
import check_once
import weekly_report
import send_performance_report
from signals import Signal, _macd_confirms, confirm_timeframes, timeframe_vote


class DataFeedTests(unittest.TestCase):
    def test_m1_is_supported(self):
        self.assertEqual(data_feed._TIMEFRAME_MAP["M1"], ("1m", "7d"))
        self.assertEqual(data_feed._CANDLE_MINUTES["M1"], 1)

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
        self.assertEqual(data_feed.yahoo_ticker("DOW30"), "^DJI")
        self.assertEqual(data_feed.yahoo_ticker("FTSE100"), "^FTSE")
        self.assertEqual(data_feed.yahoo_ticker("DAX40"), "^GDAXI")
        self.assertEqual(data_feed.yahoo_ticker("HANGSENG"), "^HSI")
        self.assertEqual(data_feed.yahoo_ticker("ASX200"), "^AXJO")


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


class DiscordNotifierTests(unittest.TestCase):
    def test_telegram_html_is_converted_to_discord_markdown(self):
        self.assertEqual(
            notifier._discord_markdown("📈 <b>Performance</b>\nWin rate: <b>75%</b>"),
            "📈 **Performance**\nWin rate: **75%**",
        )

    def test_long_discord_reports_are_split_below_limit(self):
        chunks = notifier._discord_chunks("\n".join(["x" * 500] * 6))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 2000 for chunk in chunks))

    @patch("config.DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    @patch("notifier.requests.post")
    def test_discord_accepts_no_content_response(self, post):
        post.return_value.status_code = 204
        self.assertTrue(notifier._send_discord("hello"))
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["json"]["content"], "hello")

    @patch("config.DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    @patch("chart.render", return_value=b"png-bytes")
    @patch("notifier.requests.post")
    def test_discord_signal_includes_chart_attachment(self, post, render):
        post.return_value.status_code = 204
        signal = Signal(
            "EURUSD", "MA_CROSS", "BUY", "test trigger", price=1.1,
            candle_time="2026-10-26T01:00:00+00:00", sl=1.09, tp=1.12,
        )
        self.assertTrue(notifier._send_discord_signal(signal))
        render.assert_called_once_with(signal)
        self.assertIn("payload_json", post.call_args.kwargs["data"])
        filename, content, mime = post.call_args.kwargs["files"]["files[0]"]
        self.assertEqual(filename, "EURUSD_m15.png")
        self.assertEqual(content, b"png-bytes")
        self.assertEqual(mime, "image/png")

    @patch("config.DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    @patch("chart.render", return_value=None)
    @patch("notifier.requests.post")
    def test_discord_signal_falls_back_to_text_when_chart_unavailable(self, post, render):
        post.return_value.status_code = 204
        signal = Signal("EURUSD", "RSI", "SELL", "test")
        self.assertTrue(notifier._send_discord_signal(signal))
        self.assertIn("json", post.call_args.kwargs)


class WeeklyPerformanceTests(unittest.TestCase):
    def test_only_selected_symbols_receive_technical_signals(self):
        self.assertEqual(config.TECHNICAL_SIGNAL_SYMBOLS, ("XAUUSD", "BTCUSD"))

    def test_weekly_report_breaks_down_requested_dimensions(self):
        state = {"signal_journal": [
            {
                "id": "gold-win", "strategy_version": config.STRATEGY_VERSION,
                "symbol": "XAUUSD", "direction": "BUY", "signal_type": "MACD_CROSS",
                "opened_at": "2026-10-20T03:00:00+00:00",
                "closed_at": "2026-10-20T05:00:00+00:00",
                "status": "WIN", "r_multiple": 2.0,
            },
            {
                "id": "btc-loss", "strategy_version": config.STRATEGY_VERSION,
                "symbol": "BTCUSD", "direction": "SELL", "signal_type": "RSI",
                "opened_at": "2026-10-21T14:00:00+00:00",
                "closed_at": "2026-10-21T16:00:00+00:00",
                "status": "LOSS", "r_multiple": -1.0,
            },
        ]}
        report = weekly_report.build_report(
            state, datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc)
        )
        self.assertIn("Overall: <b>1W/1L | 50.0% | +1.0R</b>", report)
        self.assertIn("<b>By symbol</b>", report)
        self.assertIn("• XAUUSD: 1W/0L | 100.0% | +2.0R", report)
        self.assertIn("<b>BUY vs SELL</b>", report)
        self.assertIn("<b>By trigger</b>", report)
        self.assertIn("<b>By session</b>", report)
        self.assertIn("Evening 20:00–23:00", report)

    @patch("weekly_report.notifier.send_text", return_value=True)
    def test_weekly_report_is_sent_once_on_monday(self, send_text):
        state: dict = {}
        now = datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc)
        weekly_report.maybe_send(state, now)
        weekly_report.maybe_send(state, now)
        send_text.assert_called_once()
        self.assertIn("last_weekly_performance", state)


class ManualPerformanceReportTests(unittest.TestCase):
    @patch("send_performance_report.weekly_report.build_report", return_value="weekly")
    @patch("send_performance_report.journal.performance_table", return_value="table")
    @patch("send_performance_report.journal.summary", return_value="summary")
    @patch("send_performance_report.notifier.send_text", return_value=True)
    def test_manual_report_sends_summary_table_and_weekly_breakdown(
        self, send_text, summary, table, weekly
    ):
        self.assertTrue(send_performance_report.send_report({}))
        self.assertEqual(
            [call.args[0] for call in send_text.call_args_list],
            ["summary", "table", "weekly"],
        )


class IndexReportTests(unittest.TestCase):
    def test_top_ten_indices_are_price_reports(self):
        expected = {
            "THAISET", "US500", "NAS100", "DOW30", "FTSE100", "DAX40",
            "NIKKEI225", "SHANGHAI", "HANGSENG", "ASX200",
        }
        self.assertEqual(index_report.INDEX_SYMBOLS, expected)
        self.assertTrue(all(index_report.is_index(symbol) for symbol in expected))

    def test_session_event_windows(self):
        self.assertEqual(
            index_report.due_event(
                datetime(2026, 8, 21, 9, 45), time(9, 30), time(16, 0)
            ),
            "OPEN",
        )
        self.assertEqual(
            index_report.due_event(
                datetime(2026, 8, 21, 16, 15), time(9, 30), time(16, 0)
            ),
            "CLOSE",
        )
        self.assertIsNone(
            index_report.due_event(
                datetime(2026, 8, 22, 9, 45), time(9, 30), time(16, 0)
            )
        )

    def test_session_price_change_inputs(self):
        df = pd.DataFrame([
            {"time": "2026-08-20T19:55:00Z", "open": 100, "close": 100},
            {"time": "2026-08-21T13:30:00Z", "open": 102, "close": 102.5},
            {"time": "2026-08-21T13:35:00Z", "open": 102.5, "close": 103},
        ])
        self.assertEqual(
            index_report._session_stats(
                df, "America/New_York", date(2026, 8, 21)
            ),
            (102.0, 103.0, 100.0),
        )


class SignalFilterTests(unittest.TestCase):
    @staticmethod
    def _rising_frame() -> pd.DataFrame:
        values = [100 + i * 0.2 for i in range(60)]
        return pd.DataFrame({"close": values})

    @patch("config.MIN_TIMEFRAME_CONFIRMATIONS", 4)
    @patch("config.CONFIRMATION_TIMEFRAMES", ("M1", "M5", "M15", "M30", "H1"))
    def test_four_of_five_timeframes_confirm(self):
        frame = self._rising_frame()
        signal = Signal("EURUSD", "MA_CROSS", "BUY", "test")
        frames = {name: frame for name in ("M1", "M5", "M15", "M30")}
        frames["H1"] = None
        self.assertTrue(confirm_timeframes(signal, frames))
        self.assertIn("4/5 aligned", signal.context[-1])

    @patch("config.MIN_TIMEFRAME_CONFIRMATIONS", 4)
    @patch("config.CONFIRMATION_TIMEFRAMES", ("M1", "M5", "M15", "M30", "H1"))
    def test_three_of_five_timeframes_are_rejected(self):
        frame = self._rising_frame()
        signal = Signal("EURUSD", "MA_CROSS", "BUY", "test")
        frames = {"M1": frame, "M5": frame, "M15": frame, "M30": None, "H1": None}
        self.assertFalse(confirm_timeframes(signal, frames))

    @patch("config.REQUIRE_MACD_CONFIRMATION", True)
    def test_macd_must_agree_when_confirmation_enabled(self):
        self.assertTrue(_macd_confirms("BUY", "BUY"))
        self.assertTrue(_macd_confirms("SELL", "SELL"))
        self.assertFalse(_macd_confirms("BUY", "SELL"))
        self.assertFalse(_macd_confirms("SELL", "BUY"))

    @patch("config.REQUIRE_MACD_CONFIRMATION", False)
    def test_macd_filter_can_be_disabled(self):
        self.assertTrue(_macd_confirms("BUY", "SELL"))


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

    @patch("config.INDEX_REPORT_SYMBOLS", ("THAISET", "US500"))
    def test_indices_are_excluded_from_performance(self):
        state = {"signal_journal": [
            {"id": "THAISET|BUY|1", "symbol": "THAISET", "status": "LOSS"},
            {"id": "EURUSD|BUY|2", "symbol": "EURUSD", "status": "WIN",
             "strategy_version": config.STRATEGY_VERSION,
             "direction": "BUY", "signal_type": "RSI", "opened_at": "2026-01-01",
             "entry": 1.1, "sl": 1.0, "tp": 1.3, "r_multiple": 2.0},
        ]}
        self.assertNotIn("THAISET", journal.performance_table(state))
        self.assertIn("1 wins / 0 losses", journal.summary(state))

    def test_performance_table_contains_signal_details(self):
        state = {"signal_journal": [{
            "symbol": "EURUSD", "direction": "BUY", "signal_type": "MA_CROSS",
            "strategy_version": config.STRATEGY_VERSION,
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
            "strategy_version": config.STRATEGY_VERSION,
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

    def test_performance_only_uses_current_strategy_version(self):
        common = {
            "symbol": "EURUSD", "direction": "BUY", "signal_type": "RSI",
            "opened_at": "2026-01-01T00:00:00+00:00", "entry": 1.1,
            "sl": 1.0, "tp": 1.3, "status": "WIN", "r_multiple": 2.0,
        }
        current = dict(common, id="current", strategy_version=config.STRATEGY_VERSION)
        legacy = dict(common, id="legacy")
        text = journal.summary({"signal_journal": [legacy, current]})
        self.assertIn("Analyzed: <b>1</b>", text)
        self.assertIn(config.STRATEGY_VERSION, text)

    def test_trigger_time_is_the_journal_identity(self):
        state: dict = {}
        first = Signal("EURUSD", "RSI", "BUY", "test", price=1.1,
                       candle_time="2026-01-01T02:00:00Z", trigger_price=1.09,
                       trigger_time="2026-01-01T01:00:00Z", sl=1.0, tp=1.3)
        later_snapshot = Signal("EURUSD", "RSI", "BUY", "test", price=1.11,
                                candle_time="2026-01-01T03:00:00Z", trigger_price=1.09,
                                trigger_time="2026-01-01T01:00:00Z", sl=1.0, tp=1.3)
        journal.record(state, first)
        journal.record(state, later_snapshot)
        self.assertEqual(len(journal.records(state)), 1)
        self.assertEqual(journal.records(state)[0]["trigger_price"], 1.09)

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
