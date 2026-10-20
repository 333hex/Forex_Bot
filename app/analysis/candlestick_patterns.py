import pandas as pd


def detect_patterns(frame: pd.DataFrame) -> list[str]:
    if len(frame) < 3: return []
    a, b, c = (frame.iloc[-3], frame.iloc[-2], frame.iloc[-1])
    rng = max(float(c.high-c.low), 1e-12)
    body = abs(float(c.close-c.open))
    upper, lower = float(c.high-max(c.open,c.close)), float(min(c.open,c.close)-c.low)
    out=[]
    if b.close < b.open and c.close > c.open and c.open <= b.close and c.close >= b.open: out.append("BULLISH ENGULFING")
    if b.close > b.open and c.close < c.open and c.open >= b.close and c.close <= b.open: out.append("BEARISH ENGULFING")
    if body/rng < .1: out.append("DOJI")
    if lower >= 2*max(body, 1e-12) and upper <= body: out.append("HAMMER")
    if upper >= 2*max(body, 1e-12) and lower <= body: out.append("SHOOTING STAR")
    if body/rng >= .7 and c.close > c.open: out.append("STRONG BULLISH")
    if body/rng >= .7 and c.close < c.open: out.append("STRONG BEARISH")
    return out
