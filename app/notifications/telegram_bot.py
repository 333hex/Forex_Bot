from __future__ import annotations

import httpx

from app.analysis.signal_engine import Signal


def format_signal(signal: Signal) -> str:
    lines=[f"TradeAssist Forex | {signal.decision}", f"Pair: {signal.symbol.replace('_','/')}", f"Time: {signal.timestamp} UTC", f"Reason: {signal.reason}"]
    if signal.entry is not None:
        lines.extend([f"Entry: {signal.entry:.5f}", f"Stop loss: {signal.stop_loss:.5f}", f"Take profit: {signal.take_profit:.5f}", f"Reward/risk: {signal.reward_risk:.2f}:1"])
    lines.append("Signal only. Not financial advice; verify data and manage risk.")
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id: raise ValueError("Telegram token and chat id are required")
    response=httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat_id,"text":text},timeout=15)
    response.raise_for_status()
    if not response.json().get("ok"): raise RuntimeError("Telegram API rejected the message")
