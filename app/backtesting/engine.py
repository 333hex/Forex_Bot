from __future__ import annotations

import pandas as pd


def simulate_bracket_entries(frame: pd.DataFrame, entries: list[dict]) -> dict:
    """Run precomputed bracket entries against subsequent candles; ambiguous bars exit at stop."""
    outcomes=[]
    for trade in entries:
        side, entry_i = trade["direction"], int(trade["index"])
        result={"result":"OPEN","r_multiple":0.0}
        risk=abs(trade["entry"]-trade["stop_loss"])
        if risk <= 0: raise ValueError("stop distance must be positive")
        for _, candle in frame.iloc[entry_i+1:].iterrows():
            stop = candle.low <= trade["stop_loss"] if side=="BUY" else candle.high >= trade["stop_loss"]
            target = candle.high >= trade["take_profit"] if side=="BUY" else candle.low <= trade["take_profit"]
            if stop or target:
                win=target and not stop
                result={"result":"WIN" if win else "LOSS","r_multiple":abs(trade["take_profit"]-trade["entry"])/risk if win else -1.0}
                break
        outcomes.append(result)
    returns=[x["r_multiple"] for x in outcomes]
    return {"trades":len(outcomes),"wins":sum(x["result"]=="WIN" for x in outcomes),"losses":sum(x["result"]=="LOSS" for x in outcomes),"open":sum(x["result"]=="OPEN" for x in outcomes),"net_r":sum(returns),"win_rate":sum(x["result"]=="WIN" for x in outcomes)/max(len(outcomes),1),"outcomes":outcomes,"limitations":"Precomputed entries; no spread, slippage, swaps, financing, or intrabar tick ordering. Same-bar stop/target ambiguity resolves to stop."}
