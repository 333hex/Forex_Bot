from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256

import pandas as pd

from app.config import Settings
from app.indicators.core import atr, ema, rsi
from app.analysis.support_resistance import market_structure
from app.analysis.candlestick_patterns import detect_patterns
from app.risk.calculations import stop_and_target
from app.risk.calculations import pip_size


@dataclass
class Signal:
    signal_id: str
    symbol: str
    timestamp: str
    decision: str
    direction: str
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    reward_risk: float | None
    timeframes: dict[str, str]
    reason: str
    patterns: list[str]


def _trend(frame: pd.DataFrame) -> str:
    if len(frame) < 200: return "INSUFFICIENT HISTORY"
    fast, slow = ema(frame.close, 50).iloc[-1], ema(frame.close, 200).iloc[-1]
    if pd.isna(fast) or pd.isna(slow): return "INSUFFICIENT HISTORY"
    return "BULLISH" if frame.close.iloc[-1] > fast > slow else "BEARISH" if frame.close.iloc[-1] < fast < slow else "RANGE"


def analyze_symbol(symbol: str, frames: dict[str, pd.DataFrame], settings: Settings) -> Signal:
    directions = {tf: _trend(frames[tf]) for tf in ("H4", "H1")}
    m15 = frames["M15"]
    m5 = frames["M5"]
    bias = "BUY" if all(directions[t] == "BULLISH" for t in directions) else "SELL" if all(directions[t] == "BEARISH" for t in directions) else "WAIT"
    directions["M15"] = market_structure(m15)
    pattern = detect_patterns(m5)
    directions["M5"] = "ENTRY CONFIRMED" if pattern else "WAIT"
    decision, entry, sl, tp, rr = "WAIT", None, None, None, None
    reason = "Higher-timeframe bias or completed-candle entry trigger is not aligned."
    if bias != "WAIT" and len(m15) >= 20 and len(m5) >= 20:
        current, previous = m5.iloc[-1], m5.iloc[-2]
        momentum = rsi(m15.close).iloc[-1]
        a = atr(m5).iloc[-1]
        setup_aligned = "BULLISH STRUCTURE" in directions["M15"] if bias == "BUY" else "BEARISH STRUCTURE" in directions["M15"]
        trigger = ("BULLISH" in " ".join(pattern) or current.close > previous.high) if bias == "BUY" else ("BEARISH" in " ".join(pattern) or current.close < previous.low)
        momentum_ok = (not pd.isna(momentum) and momentum >= 45) if bias == "BUY" else (not pd.isna(momentum) and momentum <= 55)
        has_spread = "bid_close" in m5.columns and "ask_close" in m5.columns
        spread = (float(current.ask_close)-float(current.bid_close))/pip_size(symbol) if has_spread else float("inf")
        spread_ok = has_spread and 0 <= spread <= settings.max_spread_pips
        if setup_aligned and trigger and momentum_ok and spread_ok and not pd.isna(a) and a > 0:
            entry = float(current.close)
            sl, tp = stop_and_target(symbol, bias, entry, float(a), rr=max(settings.min_reward_risk, 2.0))
            rr = abs(tp-entry)/abs(entry-sl)
            decision = bias
            directions["M5"] = "ENTRY CONFIRMED"
            reason = f"H4/H1 trend, M15 market structure, M5 completed-candle trigger, RSI {momentum:.1f}, and {spread:.2f}-pip spread agree. Risk/reward {rr:.2f}:1."
        elif trigger and momentum_ok and not spread_ok:
            reason = "Entry conditions aligned, but bid/ask spread is unavailable or exceeds the configured maximum; setup rejected."
    stamp = str(frames["M5"].timestamp.iloc[-1])
    raw_id = f"{symbol}|{stamp}|{decision}|{entry}"
    return Signal(sha256(raw_id.encode()).hexdigest()[:20], symbol, stamp, decision, bias if decision != "WAIT" else "NONE", entry, sl, tp, rr, directions, reason, pattern)
