#!/usr/bin/env python3
"""
MT5 本地数据桥 — 持续采集1分钟K线到SQLite
然后按需合成多周期K线, 全部数据源100%来自MT5
"""
import sqlite3, os, time, pickle
from datetime import datetime, timedelta
import MetaTrader5 as mt5

DB_PATH = "D:/BTC/mt5_data.db"
SYMBOL = "BTCUSD"
MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
COLLECT_INTERVAL = 60  # 每60秒采集一次

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bars_1m (
            time TEXT PRIMARY KEY,
            open REAL, high REAL, low REAL, close REAL,
            tick_volume INTEGER, real_volume INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_time ON bars_1m(time)")
    conn.commit()
    return conn

def collect_bars(conn):
    """采集MT5最新1m K线并写入数据库"""
    try:
        mt5.initialize(path=MT5_PATH)
        mt5.symbol_select(SYMBOL, True)
        
        # 获取最新的1m K线（取最近60根覆盖可能的断线）
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 60)
        mt5.shutdown()
        
        if rates is None or len(rates) == 0:
            return 0
        
        inserted = 0
        for r in rates:
            t = datetime.fromtimestamp(r[0]).strftime("%Y-%m-%d %H:%M:%S")
            o, h, l, c = r[1], r[2], r[3], r[4]
            tv, rv = r[5], r[6] if len(r) > 6 else 0
            
            conn.execute(
                "INSERT OR REPLACE INTO bars_1m VALUES (?,?,?,?,?,?,?)",
                (t, o, h, l, c, tv, rv)
            )
            inserted += 1
        
        conn.commit()
        return inserted
    except Exception as e:
        print(f"  ⚠️ 采集异常: {e}")
        return 0

def get_bars(conn, minutes: int) -> list:
    """从数据库获取最近N分钟K线，合成多周期"""
    # 读取原始1m数据
    rows = conn.execute(
        "SELECT time, open, high, low, close, tick_volume FROM bars_1m ORDER BY time DESC LIMIT ?",
        (minutes * 2,)  # 多取一些确保覆盖
    ).fetchall()
    
    if len(rows) < minutes:
        return []
    
    # 按时间正序
    rows = [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows[::-1]][-minutes:]
    
    return rows

def synthesize(bars_1m: list, period_minutes: int) -> list:
    """从1m数据合成大周期K线"""
    if not bars_1m or period_minutes < 1:
        return []
    
    result = []
    bucket = []
    bucket_start = None
    
    for bar in bars_1m:
        t_str, o, h, l, c, v = bar
        t = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
        
        # 计算这个bar属于哪个bucket
        slot = (t.minute // period_minutes) * period_minutes
        slot_time = t.replace(minute=slot, second=0, microsecond=0)
        
        if slot_time != bucket_start and bucket:
            # 保存上一个bucket
            result.append((
                bucket_start.strftime("%Y-%m-%d %H:%M:%S"),
                float(bucket[0][1]),
                float(max(b[2] for b in bucket)),
                float(min(b[3] for b in bucket)),
                float(bucket[-1][4]),
                int(sum(int(b[5]) for b in bucket)),
            ))
            bucket = []
        
        if not bucket:
            bucket_start = slot_time
        bucket.append(bar)
    
    # 最后一个bucket
    if bucket:
        result.append((
            bucket_start.strftime("%Y-%m-%d %H:%M:%S"),
            bucket[0][1], max(b[2] for b in bucket),
            min(b[3] for b in bucket), bucket[-1][4],
            sum(b[5] for b in bucket),
        ))
    
    return result

def get_multi_tf_bars(conn, tf_minutes: int, count: int = 60) -> list:
    """获取指定周期的K线 (1/5/15/30/60/240/1440分钟)"""
    # 要从多少分钟的数据合成
    raw_minutes = tf_minutes * (count + 2)
    bars_1m = get_bars(conn, raw_minutes)
    
    if not bars_1m:
        return []
    
    # 合成
    return synthesize(bars_1m, tf_minutes)[-count:]

# ============================================================
# 独立运行: 持续采集模式
# ============================================================
def dlog(msg: str):
    """同时输出到stdout(如果可用)和日志文件"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except:
        pass
    with open("data_bridge.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

if __name__ == "__main__":
    dlog("=" * 50)
    dlog("MT5 数据桥启动 — 1分钟K线采集 (静默模式)")
    dlog(f"数据库: {DB_PATH}")
    dlog("=" * 50)
    
    conn = init_db()
    
    # 先检查现有数据
    count = conn.execute("SELECT COUNT(*) FROM bars_1m").fetchone()[0]
    if count > 0:
        first = conn.execute("SELECT MIN(time) FROM bars_1m").fetchone()[0]
        last = conn.execute("SELECT MAX(time) FROM bars_1m").fetchone()[0]
        dlog(f"现有数据: {count} 根 ( {first} ~ {last} )")
    else:
        dlog("空数据库, 开始采集...")
    
    # 采集循环
    last_log = time.time()
    while True:
        try:
            n = collect_bars(conn)
            if n > 0:
                last = conn.execute("SELECT MAX(time) FROM bars_1m").fetchone()[0]
                total = conn.execute("SELECT COUNT(*) FROM bars_1m").fetchone()[0]
                # 每30秒打印一次避免日志爆炸
                if time.time() - last_log > 30:
                    dlog(f"采集 {n} 根 | 总计 {total} | 最新 {last}")
                    last_log = time.time()
            else:
                if time.time() - last_log > 30:
                    dlog("采集失败, 等待重试...")
                    last_log = time.time()
        except Exception as e:
            dlog(f"⚠️ 循环异常: {e}")
        
        time.sleep(COLLECT_INTERVAL)
