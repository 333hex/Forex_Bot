from __future__ import annotations

import pandas as pd


def swing_levels(frame: pd.DataFrame, lookback: int = 3, max_levels: int = 12) -> dict[str, list[float]]:
    """Confirmed pivots: a level is available only after `lookback` right bars exist."""
    highs, lows = [], []
    for i in range(lookback, len(frame)-lookback):
        h = frame.high.iloc[i-lookback:i+lookback+1]
        l = frame.low.iloc[i-lookback:i+lookback+1]
        if frame.high.iloc[i] == h.max() and (h == frame.high.iloc[i]).sum() == 1: highs.append(float(frame.high.iloc[i]))
        if frame.low.iloc[i] == l.min() and (l == frame.low.iloc[i]).sum() == 1: lows.append(float(frame.low.iloc[i]))
    return {"resistance": highs[-max_levels:], "support": lows[-max_levels:]}


def market_structure(frame: pd.DataFrame, lookback: int = 3) -> str:
    levels = swing_levels(frame, lookback)
    highs, lows = levels["resistance"], levels["support"]
    if len(highs) < 2 or len(lows) < 2: return "INSUFFICIENT HISTORY"
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]: return "BULLISH STRUCTURE"
    if highs[-1] < highs[-2] and lows[-1] < lows[-2]: return "BEARISH STRUCTURE"
    return "RANGE / MIXED"
