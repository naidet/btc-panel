#!/usr/bin/env python3
"""
K线数据本地存储 — SQLite
=========================
- 每次刷新自动存 1h/4h/1d K线
- 去重：同一时间戳+周期+品种只存一条
- 积攒到足够数据后触发 ML 模型重训练
"""
import sqlite3
import os
import time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data.db")

# 建表 SQL
SCHEMA = """
CREATE TABLE IF NOT EXISTS klines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_time INTEGER NOT NULL,  -- Unix timestamp
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(symbol, timeframe, bar_time)
);

CREATE INDEX IF NOT EXISTS idx_kl_sym_tf ON klines(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_kl_time ON klines(bar_time);

CREATE TABLE IF NOT EXISTS store_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_db():
    """获取数据库连接（自动建表）"""
    is_new = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    if is_new:
        conn.executescript(SCHEMA)
        conn.commit()
    return conn


def init_db():
    """初始化数据库（确保表存在）"""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def save_klines(symbol: str, timeframe: str, bars: list) -> int:
    """
    批量保存 K 线，返回新插入数量。
    bars: list of dict，每个 dict 含 bar_time/open/high/low/close/volume
    """
    if not bars:
        return 0
    conn = get_db()
    count = 0
    try:
        for b in bars:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO klines(symbol,timeframe,bar_time,open,high,low,close,volume) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (symbol, timeframe, b["bar_time"],
                     b["open"], b["high"], b["low"], b["close"], b.get("volume", 0))
                )
                count += conn.total_changes
            except Exception:
                continue
        conn.commit()
    finally:
        conn.close()
    return count


def count_klines(symbol: str = None, timeframe: str = None) -> dict:
    """统计各品种各周期 K 线数量"""
    conn = get_db()
    try:
        cur = conn.cursor()
        if symbol and timeframe:
            cur.execute("SELECT COUNT(*) FROM klines WHERE symbol=? AND timeframe=?", (symbol, timeframe))
            return {"total": cur.fetchone()[0]}
        cur.execute(
            "SELECT symbol, timeframe, COUNT(*) as cnt, "
            "MIN(datetime(bar_time,'unixepoch')) as first, "
            "MAX(datetime(bar_time,'unixepoch')) as last "
            "FROM klines GROUP BY symbol, timeframe ORDER BY symbol, timeframe"
        )
        rows = cur.fetchall()
        return {
            f"{r[0]}/{r[1]}": {"count": r[2], "first": r[3], "last": r[4]}
            for r in rows
        }
    finally:
        conn.close()


def get_klines(symbol: str, timeframe: str, limit: int = 500) -> list:
    """获取最近 N 根 K 线，按时间升序"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT bar_time, open, high, low, close, volume "
            "FROM klines WHERE symbol=? AND timeframe=? "
            "ORDER BY bar_time ASC LIMIT ?",
            (symbol, timeframe, limit)
        )
        return [
            {"bar_time": r[0], "open": r[1], "high": r[2],
             "low": r[3], "close": r[4], "volume": r[5]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def get_total_count(symbol: str) -> int:
    """获取指定品种所有周期总 K 线数"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM klines WHERE symbol=?", (symbol,))
        return cur.fetchone()[0]
    finally:
        conn.close()


def get_db_size_mb() -> float:
    """获取数据库文件大小 (MB)"""
    if not os.path.exists(DB_PATH):
        return 0
    return os.path.getsize(DB_PATH) / (1024 * 1024)


def convert_mt5_rates(rates, bars=None):
    """将 MT5 copy_rates 返回的 numpy 数组转为 dict 列表"""
    import numpy as np
    if bars is None or len(bars) == 0:
        return []
    result = []
    for r in rates if rates is not None else []:
        try:
            # MT5 rates: [time, open, high, low, close, tick_volume, spread, real_volume]
            ts = int(r[0])
            if ts > 10000000000:  # 毫秒级
                ts = ts // 1000
            result.append({
                "bar_time": ts,
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            })
        except Exception:
            continue
    return result


# ═══════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════
init_db()
