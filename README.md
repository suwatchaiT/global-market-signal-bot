# Global Market Signal Bot

[![Signal check](https://github.com/suwatchaiT/global-market-signal-bot/actions/workflows/signal-check.yml/badge.svg)](https://github.com/suwatchaiT/global-market-signal-bot/actions/workflows/signal-check.yml)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue)

A GitHub-hosted technical-analysis bot that monitors global forex, metals, cryptocurrency, and stock-index markets, then sends Telegram alerts and performance reports. It uses Yahoo Finance data and GitHub Actions, so no MT5 terminal, broker account, server, or always-awake computer is required.

## Strategy and features
- EMA crossover (fast/slow configurable)
- RSI overbought / oversold zones
- MACD signal-line crossover
- Closed-candle evaluation with higher-timeframe trend confirmation
- ATR stop/target and risk-based position-size estimates
- Signal journal with `/performance` win-rate and R-multiple summary
- Per-signal Telegram table with `/performance` or `/performance 20`
- Daily Telegram health heartbeat

## Setup

Requires Python 3.9+.

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env with your Telegram credentials
python main.py
```

## Configuration

All settings live in `.env` — see `.env.example` for every option.

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | — | BotFather token |
| `TELEGRAM_CHAT_ID` | — | Your chat or channel ID |
| `SYMBOLS` | Forex, metals, crypto, and five indices | Comma-separated symbols |
| `TIMEFRAME` | `H1` | M5 M15 M30 H1 H4 D1 |
| `MA_FAST` / `MA_SLOW` | `9` / `21` | EMA periods |
| `RSI_PERIOD` | `14` | RSI lookback |
| `RSI_OVERBOUGHT` / `RSI_OVERSOLD` | `70` / `30` | RSI thresholds |\n| `MIN_STARS` | `2` | Minimum agreeing indicators required for an alert |
| `MACD_FAST` / `MACD_SLOW` / `MACD_SIGNAL` | `12` / `26` / `9` | MACD periods |
| `POLL_INTERVAL` | `60` | Seconds between checks |
| `HIGHER_TIMEFRAME` | `H4` | Trend-confirmation timeframe |
| `REQUIRE_HTF_CONFIRMATION` | `true` | Reject signals against the higher-timeframe EMA trend |
| `ACCOUNT_BALANCE` | `10000` | Balance used only for position-size estimates |
| `RISK_PERCENT` | `1` | Estimated account risk per signal |
| `ALERT_START_HOUR` / `ALERT_START_MINUTE` | `8` / `30` | Daytime-window start (Thailand time) |
| `ALERT_END_HOUR` / `ALERT_END_MINUTE` | `17` / `0` | Daytime-window end |
| `US_ALERT_START_HOUR` / `US_ALERT_START_MINUTE` | `20` / `0` | Evening-window start |
| `US_ALERT_END_HOUR` / `US_ALERT_END_MINUTE` | `23` / `0` | Evening-window end |

## Default watchlist

| Market | Symbols |
|---|---|
| Forex | EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF |
| Metals | XAUUSD |
| Cryptocurrency | BTCUSD |
| Indices | THAISET, US500, NAS100, NIKKEI225, SHANGHAI |

Other supported symbols include USDCAD, NZDUSD, XAGUSD, and ETHUSD. Yahoo Finance tickers can also be used directly.

## Telegram setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token to `TELEGRAM_TOKEN`
3. Message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat_id`

For GitHub Actions, add `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` as repository
secrets. Add `SYMBOLS`, `ACCOUNT_BALANCE`, `RISK_PERCENT`, `HIGHER_TIMEFRAME`, and
`REQUIRE_HTF_CONFIRMATION` under **Settings → Secrets and variables → Actions →
Variables** when you want values other than the defaults above.

## Telegram commands

| Command | Result |
|---|---|
| `/status` | Current prices, EMA trend, and RSI for every monitored symbol |
| `/performance` | Overall result plus the latest 15 recorded signals |
| `/performance 20` | Overall result plus the latest 20 recorded signals |

## Important limitations

- Yahoo Finance intraday data is slightly delayed (~1–15 min depending on market); fine for indicator alerts, not for HFT.
- Identical alerts are rate-limited to once per hour.
- Position sizes are estimates. Confirm contract size, spread, currency conversion,
  and execution price with your broker before trading.
- Index alerts intentionally omit lot-size estimates because CFD contract sizes vary by broker.
- GitHub checks every 15 minutes during the user-selected 08:30-17:00 and
  20:00-23:00 Thailand-time windows.
- `/performance` measures later closed-candle SL/TP touches, not actual broker fills.
- A monthly maintenance workflow rotates a GitHub issue to keep public-repository
  scheduled workflows active and visible.
- Signals are informational and are not financial advice. Test the strategy and manage risk before using real money.
- Logs are written to `bot.log`.

## License

This repository currently has no license file. All rights remain with the repository owner unless a license is added.
