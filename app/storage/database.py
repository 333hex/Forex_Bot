from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS signals(signal_id TEXT PRIMARY KEY, symbol TEXT, timestamp TEXT, decision TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS paper_trades(id INTEGER PRIMARY KEY, signal_id TEXT UNIQUE, symbol TEXT, direction TEXT, entry REAL, stop_loss REAL, take_profit REAL, status TEXT, opened_at TEXT, closed_at TEXT, exit_price REAL, pnl REAL);
            CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, symbol TEXT, decision TEXT, reason TEXT);
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def save_signal(self, signal) -> bool:
        with self.connect() as db:
            cur = db.execute("INSERT OR IGNORE INTO signals VALUES(?,?,?,?,?)", (signal.signal_id, signal.symbol, signal.timestamp, signal.decision, json.dumps(asdict(signal))))
            db.execute("INSERT INTO decisions(symbol,decision,reason) VALUES(?,?,?)", (signal.symbol, signal.decision, signal.reason))
            return cur.rowcount == 1

    def signal_count(self) -> int:
        with self.connect() as db: return int(db.execute("SELECT count(*) FROM signals").fetchone()[0])

    def open_paper_trade(self, signal) -> bool:
        if signal.decision not in {"BUY", "SELL"} or signal.entry is None: return False
        with self.connect() as db:
            cur = db.execute("INSERT OR IGNORE INTO paper_trades(signal_id,symbol,direction,entry,stop_loss,take_profit,status,opened_at) VALUES(?,?,?,?,?,?,?,?)", (signal.signal_id, signal.symbol, signal.direction, signal.entry, signal.stop_loss, signal.take_profit, "OPEN", signal.timestamp))
            return cur.rowcount == 1

    def mark_paper_trades(self, symbol: str, high: float, low: float, timestamp: str) -> list[dict]:
        """Conservative same-candle ambiguity rule: if stop and target both touch, stop wins."""
        closed=[]
        with self.connect() as db:
            rows=db.execute("SELECT * FROM paper_trades WHERE status='OPEN' AND symbol=?", (symbol,)).fetchall()
            for row in rows:
                hit_stop = low <= row['stop_loss'] if row['direction']=='BUY' else high >= row['stop_loss']
                hit_target = high >= row['take_profit'] if row['direction']=='BUY' else low <= row['take_profit']
                if not (hit_stop or hit_target): continue
                price = row['stop_loss'] if hit_stop else row['take_profit']
                pnl = (price-row['entry']) if row['direction']=='BUY' else (row['entry']-price)
                db.execute("UPDATE paper_trades SET status='CLOSED',closed_at=?,exit_price=?,pnl=? WHERE id=?",(timestamp,price,pnl,row['id']))
                closed.append({"signal_id":row['signal_id'],"exit_price":price,"pnl":pnl})
        return closed
