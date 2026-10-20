from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


@dataclass(frozen=True)
class Settings:
    symbols: tuple[str, ...] = ("EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "AUD_USD", "NZD_USD", "USD_CAD")
    provider: str = "twelve_data"
    twelve_data_api_key: str = ""
    twelve_data_min_request_interval_seconds: float = 7.5
    telegram_token: str = ""
    telegram_chat_id: str = ""
    mode: str = "signal"
    risk_per_trade_percent: float = 0.5
    max_daily_loss_percent: float = 2.0
    max_open_paper_trades: int = 3
    max_trades_per_day: int = 5
    min_reward_risk: float = 1.5
    max_spread_pips: float = 2.5
    database_path: Path = Path("data/tradeassist.sqlite3")
    log_path: Path = Path("logs/tradeassist.log")
    scan_interval_seconds: int = 3600

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        symbols = tuple(s.strip().upper().replace("/", "_") for s in os.getenv("FOREX_SYMBOLS", "EUR_USD,GBP_USD,USD_JPY,USD_CHF,AUD_USD,NZD_USD,USD_CAD").split(",") if s.strip())
        if not symbols or any(len(s.split("_")) != 2 for s in symbols):
            raise ValueError("FOREX_SYMBOLS must be comma-separated BASE_QUOTE symbols")
        mode = os.getenv("TRADING_MODE", "signal").lower()
        if mode not in {"signal", "paper"}:
            raise ValueError("TRADING_MODE supports signal or paper only")
        result = cls(
            symbols=symbols,
            provider=os.getenv("MARKET_DATA_PROVIDER", "twelve_data").lower(),
            twelve_data_api_key=os.getenv("TWELVE_DATA_API_KEY", "").strip(),
            twelve_data_min_request_interval_seconds=max(0.0, float(os.getenv("TWELVE_DATA_MIN_REQUEST_INTERVAL_SECONDS", "7.5"))),
            telegram_token=_first_env("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"),
            telegram_chat_id=_first_env("TELEGRAM_CHAT_ID", "TELEGRAM_GROUP_ID"),
            mode=mode,
            risk_per_trade_percent=float(os.getenv("RISK_PER_TRADE_PERCENT", "0.5")),
            max_daily_loss_percent=float(os.getenv("MAX_DAILY_LOSS_PERCENT", "2")),
            max_open_paper_trades=int(os.getenv("MAX_OPEN_PAPER_TRADES", "3")),
            max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", "5")),
            min_reward_risk=float(os.getenv("MIN_REWARD_RISK", "1.5")),
            max_spread_pips=float(os.getenv("MAX_SPREAD_PIPS", "2.5")),
            scan_interval_seconds=max(10, int(os.getenv("SCAN_INTERVAL_SECONDS", "3600"))),
        )
        if not 0 < result.risk_per_trade_percent <= 2 or not 0 < result.max_daily_loss_percent <= 10 or result.min_reward_risk < 1:
            raise ValueError("Risk settings outside supported safe ranges")
        return result
