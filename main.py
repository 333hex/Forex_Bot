from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from app.analysis.signal_engine import analyze_symbol
from app.config import Settings
from app.data.provider import DataUnavailable, TwelveDataProvider
from app.data.validation import validate_candles
from app.storage.database import Database
from app.utils.logging_setup import configure_logging
from app.notifications.telegram_bot import format_signal, send_telegram
from app.paper_trading.simulator import PaperSimulator

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="TradeAssist Forex: signal-only Forex analysis")
    parser.add_argument("command", nargs="?", choices=["scan", "run", "status"], default="scan")
    parser.add_argument("--once", action="store_true", help="Run one scan (default for scan)")
    args = parser.parse_args()
    settings = Settings.load()
    configure_logging(settings.log_path)
    db = Database(settings.database_path)
    paper = PaperSimulator(db)
    if args.command == "status":
        configured = "yes" if settings.twelve_data_api_key else "no"
        provider_name = "Twelve Data" if settings.provider in {"twelve_data", "twelvedata"} else settings.provider
        console.print(f"TradeAssist Forex | mode={settings.mode} | provider={provider_name} | api_key_configured={configured} | signals={db.signal_count()}")
        return 0
    try:
        provider = TwelveDataProvider.from_settings(settings)
    except DataUnavailable as exc:
        console.print(f"Market data configuration error: {exc}", style="red")
        return 2
    while True:
        failed_symbols = 0
        table = Table(title="TRADEASSIST FOREX | SIGNAL ONLY")
        for name in ("Pair", "H4", "H1", "M15", "M5", "Decision", "Reason"):
            table.add_column(name)
        for symbol in settings.symbols:
            try:
                age_limits = {"H4": 172800, "H1": 43200, "M15": 10800, "M5": 3600}
                frames = {tf: validate_candles(provider.fetch_candles(symbol, tf, 300), max_age_seconds=age_limits[tf]) for tf in age_limits}
                signal = analyze_symbol(symbol, frames, settings)
                is_new = db.save_signal(signal)
                if settings.mode == "paper" and signal.decision in {"BUY", "SELL"}:
                    paper.open_from_signal(signal)
                if is_new and signal.decision in {"BUY", "SELL"} and settings.telegram_token and settings.telegram_chat_id:
                    try:
                        send_telegram(settings.telegram_token, settings.telegram_chat_id, format_signal(signal))
                    except Exception:
                        logging.exception("Telegram notification failed for %s", symbol)
                table.add_row(symbol.replace("_", "/"), *(signal.timeframes.get(tf, "N/A") for tf in ("H4", "H1", "M15", "M5")), signal.decision, signal.reason[:100])
                logging.info("decision=%s symbol=%s id=%s", signal.decision, symbol, signal.signal_id)
            except Exception as exc:
                failed_symbols += 1
                logging.exception("scan failed for %s", symbol)
                table.add_row(symbol, "—", "—", "—", "—", "DATA UNAVAILABLE", str(exc)[:100])
        console.print(table)
        if args.command != "run":
            return 1 if failed_symbols else 0
        time.sleep(settings.scan_interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
