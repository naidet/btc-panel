"""
BTC AI Trading System - Core Trading Module (Production Version)
提供: MT5接口、信号计算、风控、交易执行
!!! 实盘使用前必须用模拟盘测试 !!!
"""

from datetime import datetime, time as dt_time
from typing import Optional, Dict, List, Tuple
import json, os, time, threading, warnings, math
warnings.filterwarnings("ignore", category=FutureWarning)
from btc_trader import calc_ema, calc_rsi, calc_atr, calc_adx, Bar
import MetaTrader5 as mt5
import numpy as np

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

# ============================================================
# MT5 连接管理器 (全局单例, 避免反复初始化/关闭)
# ============================================================
_mt5_initialized = False
_mt5_lock = threading.RLock()  # 可重入锁, 避免死锁
_mt5_last_ok = 0.0             # 最后一次成功操作的时间戳
_mt5_fail_count = 0            # 连续失败计数
_mt5_max_fails = 3             # 连续失败N次后强制重连
_mt5_ping_interval = 30.0      # 心跳间隔(秒)

def mt5_ensure():
    """确保MT5已初始化且连接可用, 返回True/False"""
    global _mt5_initialized, _mt5_fail_count, _mt5_last_ok

    # 快速路径：已初始化 + 最近有心跳 = 直接返回
    if _mt5_initialized and (time.time() - _mt5_last_ok) < _mt5_ping_interval:
        return True

    # 慢路径：检查连接是否真的可用
    if _mt5_initialized:
        try:
            # 真实心跳：用account_info()验证连接不是僵尸
            acct = mt5.account_info()
            if acct is not None:
                _mt5_last_ok = time.time()
                _mt5_fail_count = 0
                return True
        except:
            pass

        # 连接是僵尸，强制重连
        _mt5_fail_count += 1
        if _mt5_fail_count >= _mt5_max_fails:
            _mt5_initialized = False  # 标记失效，触发重连

    # 初始化/重连
    try:
        if mt5.initialize(path=MT5_PATH, timeout=5000):
            # 验证新连接可用
            acct = mt5.account_info()
            if acct is not None:
                _mt5_initialized = True
                _mt5_last_ok = time.time()
                _mt5_fail_count = 0
                return True
            else:
                mt5.shutdown()
                _mt5_initialized = False
    except:
        try:
            mt5.shutdown()
        except:
            pass
        _mt5_initialized = False

    _mt5_fail_count += 1
    return False

def mt5_reconnect():
    """强制断开并重新连接MT5"""
    global _mt5_initialized, _mt5_fail_count, _mt5_last_ok
    try:
        mt5.shutdown()
    except:
        pass
    _mt5_initialized = False
    _mt5_fail_count = 0
    _mt5_last_ok = 0.0
    time.sleep(0.5)  # 给MT5释放资源的时间
    return mt5_ensure()

def mt5_cleanup():
    """程序退出时调用, 关闭MT5"""
    global _mt5_initialized
    try:
        mt5.shutdown()
    except:
        pass
    _mt5_initialized = False

def _mt5_mark_ok():
    """标记一次成功的MT5操作"""
    global _mt5_last_ok, _mt5_fail_count
    _mt5_last_ok = time.time()
    _mt5_fail_count = 0

def _mt5_mark_fail():
    """标记一次失败的MT5操作"""
    global _mt5_fail_count
    _mt5_fail_count += 1

def check_autotrading() -> dict:
    """检测MT5终端AutoTrading是否开启"""
    try:
        with _mt5_lock:
            if not mt5_ensure():
                return {"enabled": False, "msg": "MT5未连接"}
        info = mt5.terminal_info()
        if info is None:
            return {"enabled": False, "msg": "无法读取终端信息"}
        return {
            "enabled": info.trade_allowed,
            "connected": info.connected,
            "community_account": info.community_account,
            "community_connection": info.community_connection,
            "msg": "AlgoTrading已开启 ✓" if info.trade_allowed else "⚠ AutoTrading未开启 — 无法下单"
        }
    except Exception as e:
        return {"enabled": False, "msg": f"检测异常: {e}"}

def mt5_call_with_retry(op_name, fn, retries=2, backoff=1.0):
    """
    MT5操作重试包装器
    - retries: 最多重试次数
    - backoff: 重试间隔递增倍数
    返回: (result, success)
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            with _mt5_lock:
                if not mt5_ensure():
                    last_err = "mt5_ensure 失败"
                    time.sleep(backoff * (2 ** attempt))
                    continue
                result = fn()
                _mt5_mark_ok()
                return result, True
        except Exception as e:
            last_err = str(e)[:80]
            _mt5_mark_fail()
            time.sleep(backoff * (2 ** attempt))
    return None, False

# ============================================================
# 默认参数配置
# ============================================================
DEFAULT_PARAMS = {
    "ema_period": 20,
    "rsi_period": 14,
    "rsi_long_lo": 50, "rsi_long_hi": 70,
    "rsi_short_lo": 30, "rsi_short_hi": 50,
    "adx_period": 14, "adx_threshold": 25,
    "resonance_threshold": 2,
    "sl_atr_mult": 1.5,
    "sl_min": 800,
    "tp_atr_mult": 6.0,
    "tp_min": 1500,
    "trail_profit": 5,
    "trail_dist": 300,
    "profit_lock_trigger": 5,
    "profit_lock_pullback": 20,
    "risk_per_trade": 20,
    "lot_fixed": 0,
    "lot_min": 0.01,
    "max_daily_loss": 100,
    "max_drawdown_pct": 20,
    "atr_spike_mult": 2.0,
    "max_spread_pct": 0.15,
    "cooldown_minutes": 30,
    "volatility_filter": True,
}

# ============================================================
# 品种配置 (支持券商自动适配)
# ============================================================
# 默认品种 (MT5未连接时回退)
# 目前只聚焦黄金和BTC
SYMBOLS = ["XAUUSD", "BTCUSD"]
SYMBOL_NAMES = {"XAUUSD": "黄金", "BTCUSD": "BTC"}
BROKER_WHITELIST = {"XAUUSD", "BTCUSD"}  # auto_setup_broker 只加载这两个
_BROKER_MAP = {}  # config名 → 券商实际名 (如 "BTCUSD" → "BTCUSD.z")
_FILLING_MODE_CACHE = {}  # 缓存每个品种的填充模式 (symbol → mt5 filling constant)
_DEAD_SYMBOLS = {}  # 不可用品种缓存: real_sym → (timestamp, reason) 避免无限重试
_DEAD_SYMBOL_TTL = 300  # 死品种5分钟后重试 (市场可能重开)
SYMBOL_PARAMS: dict = {}
STRATEGY_PARAMS: dict = {}

def _load_symbol_params(symbol: str):
    """加载品种专属配置 (含POINT_REFERENCE)"""
    import importlib.util
    cfg_path = os.path.join(os.path.dirname(__file__), "symbols", symbol.lower(), "config.py")
    if os.path.exists(cfg_path):
        spec = importlib.util.spec_from_file_location(f"symcfg_{symbol}", cfg_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        point_ref = getattr(mod, "POINT_REFERENCE", None)
        return getattr(mod, "PARAMS", {}), getattr(mod, "STRATEGY_CFG", {}), point_ref
    return {}, {}, None

def _auto_calibrate_params(params: dict, ref_point: float, actual_point: float) -> dict:
    """
    根据券商实际point自动缩放参数
    params: 原始参数 (基于 ref_point 校准)
    返回: 缩放后的参数副本
    """
    if ref_point is None or abs(ref_point - actual_point) < 1e-9:
        return dict(params)

    scale = ref_point / actual_point
    calibrated = dict(params)
    # 缩放所有点数类参数
    for key in ("sl_min", "tp_min", "trail_profit", "trail_dist"):
        if key in calibrated and calibrated[key] is not None:
            calibrated[key] = int(float(calibrated[key]) * scale + 0.5)
    return calibrated

def _generate_aliases(sym: str) -> list:
    """为一个品种名生成可能的MT5券商变体列表"""
    sym = sym.upper().strip()
    aliases = [sym]  # 精确名

    # 后缀变体: 有些券商加 .z / .m / .pro / . 等
    for suffix in (".z", ".m", ".pro", "."):
        aliases.append(sym + suffix)

    # #前缀变体 (#BTCUSD, #XAUUSD)
    aliases.append("#" + sym)

    # USDT变体: 加密券商用USDT代替USD (如 BTCUSDT, BTCUST)
    if sym in ("BTCUSD", "ETHUSD"):
        aliases.append(sym.replace("USD", "USDT"))
        aliases.append("#" + sym.replace("USD", "USDT"))
        # 有些券商缩写为 BTCUST (去掉了D, 如 DooTechnology)
        aliases.append(sym.replace("USD", "UST"))
        aliases.append("#" + sym.replace("USD", "UST"))
        # USDT也加后缀
        for suffix in (".z", ".m", ".pro", "."):
            aliases.append(sym.replace("USD", "USDT") + suffix)
            aliases.append(sym.replace("USD", "UST") + suffix)

    # XAU → GOLD 映射
    if sym == "XAUUSD":
        aliases.extend(["GOLD", "#GOLD", "GOLD.", "GOLDm", "GOLDz", "GOLD.pro",
                        "XAUUSD.s", "XAUUSD.S",           # DooTechnology 小写后缀
                        "#XAUUSD.s", "#XAUUSD.S"])
    
    # 去重保序
    seen = set()
    unique = []
    for a in aliases:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    return unique


def _find_mt5_symbol(config_name: str, mt5_symbols: set, verify: bool = False) -> str:
    """
    在MT5品种列表中找匹配品种, 返回MT5中的实际名称
    层级: 精确 → 前缀(后缀证) → 别名 → 模糊子串
    verify=True 时验证 symbol_info 可读 (用于 broker setup 阶段)
    找不到返回空字符串
    """
    config_name = config_name.upper()

    candidates = []  # 收集所有候选名

    # 1) 精确匹配
    if config_name in mt5_symbols:
        candidates.append(config_name)

    # 2) 前缀匹配 (如 BTCUSD.z, BTCUSDpro) — 按名称长度排序, 最短优先
    found = sorted(
        [ms for ms in mt5_symbols if ms.upper().startswith(config_name)],
        key=lambda x: len(x)
    )
    for ms in found:
        if ms not in candidates:
            candidates.append(ms)

    # 3) 别名匹配
    aliases = _generate_aliases(config_name)
    for alias in aliases:
        if alias == config_name:
            continue
        if alias in mt5_symbols and alias not in candidates:
            candidates.append(alias)
        alias_found = [
            ms for ms in mt5_symbols
            if ms.upper().startswith(alias) and ms not in candidates
        ]
        for ms in sorted(alias_found, key=lambda x: len(x)):
            if ms not in candidates:
                candidates.append(ms)

    # 4) 子串模糊匹配
    base = config_name.replace("USD", "").replace("USDT", "").replace("#", "")
    if len(base) >= 3:
        fuzzy = [
            ms for ms in mt5_symbols
            if base in ms.upper()
            and len(ms) <= len(config_name) + 8
            and ms not in candidates
        ]
        for ms in fuzzy:
            if ms not in candidates:
                candidates.append(ms)

    # 验证候选 (verify=True 时检查 symbol_info 是否可读)
    if verify:
        for cand in list(candidates):
            mt5.symbol_select(cand, True)
            working_name = _verify_symbol_readable(cand)
            if working_name:
                print(f"[BROKER]   ✅ {config_name:12s} → {working_name} (已验证可读)")
                return working_name
        if config_name not in candidates:
            mt5.symbol_select(config_name, True)
            working_name = _verify_symbol_readable(config_name)
            if working_name:
                print(f"[BROKER]   ✅ {config_name:12s} → {working_name} (回退直接访问)")
                return working_name
        return ""

    return candidates[0] if candidates else ""


def auto_setup_broker() -> dict:
    """
    启动时自动检测券商并配置品种
    返回: {"broker": str, "server": str, "symbols": [...], "warnings": [...]}
    副作用: 更新全局 SYMBOLS, SYMBOL_NAMES, SYMBOL_PARAMS, STRATEGY_PARAMS
    """
    global SYMBOLS, SYMBOL_NAMES, SYMBOL_PARAMS, STRATEGY_PARAMS, _BROKER_MAP
    import importlib.util

    result = {"broker": "未知", "server": "未知", "symbols": [], "warnings": []}

    # 尝试连接MT5获取券商信息
    try:
        if not mt5_ensure():
            result["warnings"].append("MT5未连接, 使用默认品种列表")
            _rebuild_params_from_static_list()
            return result
    except:
        result["warnings"].append("MT5连接异常, 使用默认品种列表")
        _rebuild_params_from_static_list()
        return result

    acct = mt5.account_info()
    if acct:
        result["broker"] = getattr(acct, "company", "未知") or "未知"
        result["server"] = getattr(acct, "server", "未知") or "未知"

    # 扫描symbols/目录下所有config
    config_dir = os.path.join(os.path.dirname(__file__), "symbols")
    available_configs = []
    if os.path.isdir(config_dir):
        for entry in os.listdir(config_dir):
            cfg_file = os.path.join(config_dir, entry, "config.py")
            if os.path.isfile(cfg_file):
                available_configs.append(entry.upper())

    # 检查MT5中实际可用的品种
    mt5_symbols = set()
    try:
        all_mt5 = mt5.symbols_get()
        if all_mt5:
            mt5_symbols = {s.name.upper() for s in all_mt5 if s.name}
            print(f"[BROKER] MT5品种总数: {len(mt5_symbols)}")
    except Exception as e:
        print(f"[BROKER] 扫描MT5品种异常: {e}")
        pass

    # ─── 诊断: 列出MT5中所有含BTC/XAU的品种 (方便排查) ───
    _btc_xau_in_mt5 = [s for s in mt5_symbols if "BTC" in s.upper() or "XAU" in s.upper() or "GOLD" in s.upper()]
    if _btc_xau_in_mt5:
        print(f"[BROKER] 券商 BTC/XAU 相关品种: {sorted(_btc_xau_in_mt5)}")
    else:
        print(f"[BROKER] ⚠️ 券商没有任何 BTC/XAU 品种! (总品种数: {len(mt5_symbols)})")

    # 匹配: 本地有config + MT5有品种 = 可用
    # 三层匹配: 精确 → 前缀(后缀证等) → 模糊(不同命名规则)
    matched = []
    _BROKER_MAP.clear()
    for sym in available_configs:
        real_name = _find_mt5_symbol(sym, mt5_symbols, verify=True)
        if real_name:
            matched.append(sym)
            if real_name != sym:
                _BROKER_MAP[sym] = real_name
                result["warnings"].append(f"{sym} → {real_name} (券商名映射)")
            else:
                _BROKER_MAP[sym] = sym
            print(f"[BROKER]   ✅ {sym:12s} → {real_name}")
        else:
            result["warnings"].append(f"{sym} 在此券商不可用, 已跳过")
            print(f"[BROKER]   ❌ {sym:12s} 未找到匹配品种")

    # 白名单过滤: 只保留 XAUUSD 和 BTCUSD
    matched = [s for s in matched if s in BROKER_WHITELIST]
    if not matched:
        result["warnings"].append("没有匹配的品种! 使用默认XAUUSD")
        _rebuild_params_from_static_list()
        return result

    # 为每个匹配品种加载并校准参数
    new_symbols = []
    new_names = {}
    new_params = {}
    new_strategies = {}

    for sym in matched:
        real_sym = _BROKER_MAP.get(sym, sym)  # 券商实际名称
        params, strategy, point_ref = _load_symbol_params(sym)

        # 读取MT5实际point并校准
        try:
            info = mt5.symbol_info(real_sym)
            if info and point_ref is not None:
                actual_point = info.point
                if abs(actual_point - point_ref) > 1e-9:
                    params = _auto_calibrate_params(params, point_ref, actual_point)
            elif info and info.point:
                # 没有POINT_REFERENCE → 设为实际值 (向后兼容, 不缩放)
                pass
        except:
            pass

        new_symbols.append(sym)
        # 名称从config读取
        import importlib.util as _iu2
        cfg_path = os.path.join(config_dir, sym.lower(), "config.py")
        try:
            spec = _iu2.spec_from_file_location(f"__symname_{sym}", cfg_path)
            mod = _iu2.module_from_spec(spec)
            spec.loader.exec_module(mod)
            display = getattr(mod, "DISPLAY", sym)
        except:
            display = sym
        new_names[sym] = display
        new_params[sym] = params
        new_strategies[sym] = strategy

        if point_ref is not None:
            try:
                ap = mt5.symbol_info(real_sym).point if mt5.symbol_info(real_sym) else point_ref
                if abs(ap - point_ref) > 1e-9:
                    sc = point_ref / ap
                    result["warnings"].append(
                        f"{sym}: point={ap} (参考{point_ref}), "
                        f"sl_min={params.get('sl_min','?')} (x{sc:.1f})"
                    )
            except:
                pass

    # 原地更新全局变量 (不能直接赋值, 否则 import 引用断裂)
    SYMBOLS.clear(); SYMBOLS.extend(new_symbols)
    SYMBOL_NAMES.clear(); SYMBOL_NAMES.update(new_names)
    SYMBOL_PARAMS.clear(); SYMBOL_PARAMS.update(new_params)
    STRATEGY_PARAMS.clear(); STRATEGY_PARAMS.update(new_strategies)
    result["symbols"] = new_symbols

    return result

def _get_filling_mode(symbol: str):
    """
    自动检测券商支持的订单填充模式
    MT5 filling_mode 位掩码:
      1 = FOK (Fill or Kill)
      2 = IOC (Immediate or Cancel)
      0 = RETURN (默认, 按指定价格成交)
    优先 IOC, 其次 FOK, 兜底 RETURN
    """
    from typing import Optional
    real_sym = _real_symbol(symbol)

    # 查缓存
    if real_sym in _FILLING_MODE_CACHE:
        return _FILLING_MODE_CACHE[real_sym]

    mode = mt5.ORDER_FILLING_RETURN  # 默认
    try:
        info = mt5.symbol_info(real_sym)
        if info:
            fm = info.filling_mode
            if fm & 2:  # IOC supported
                mode = mt5.ORDER_FILLING_IOC
            elif fm & 1:  # FOK supported
                mode = mt5.ORDER_FILLING_FOK
            # else: RETURN (默认)
            _FILLING_MODE_CACHE[real_sym] = mode
            mode_names = {mt5.ORDER_FILLING_IOC: "IOC", mt5.ORDER_FILLING_FOK: "FOK", mt5.ORDER_FILLING_RETURN: "RETURN"}
            print(f"[FILL] {real_sym} 填充模式: {mode_names.get(mode, mode)} (filling_mode={fm})")
        else:
            _FILLING_MODE_CACHE[real_sym] = mode
    except:
        _FILLING_MODE_CACHE[real_sym] = mode

    return mode


def _verify_symbol_readable(real_sym: str) -> Optional[str]:
    """检查品种是否可读, 返回可用的名称 (大小写修正后), 不可读返回 None"""
    # 尝试原名
    try:
        info = mt5.symbol_info(real_sym)
        if info is not None:
            return real_sym
    except:
        pass
    # 尝试大小写变体
    variants = set()
    variants.add(real_sym.lower())
    if "." in real_sym:
        base, ext = real_sym.rsplit(".", 1)
        variants.add(f"{base}.{ext.lower()}")
        variants.add(f"{base}.{ext.upper()}")
    for v in sorted(variants):
        if v == real_sym:
            continue
        try:
            info = mt5.symbol_info(v)
            if info is not None:
                print(f"[VERIFY] {real_sym} → {v} (大小写变体命中)")
                return v
        except:
            pass
    return None


def _real_symbol(sym: str) -> str:
    """将配置名称解析为券商实际名称"""
    return _BROKER_MAP.get(sym, sym)

def _rebuild_params_from_static_list():
    """回退: 用模块默认的SYMBOLS加载参数 (不校准)"""
    global SYMBOL_PARAMS, STRATEGY_PARAMS
    SYMBOL_PARAMS.clear()
    STRATEGY_PARAMS.clear()
    for _sym in SYMBOLS:
        _p, _s, _ = _load_symbol_params(_sym)
        SYMBOL_PARAMS[_sym] = _p
        STRATEGY_PARAMS[_sym] = _s

# 首次加载: 先用静态配置快速启动, 券商检测延迟到后台执行
_rebuild_params_from_static_list()
_broker_info: dict = {}  # 后台线程填充
_broker_ready = False     # 标记已检测完成

def lazy_broker_setup():
    """后台运行券商检测, 不阻塞主线程 (由Qt面板在窗口显示后调用)"""
    global _broker_info, _broker_ready
    try:
        print("[BROKER] lazy_broker_setup 开始扫描...")
        _broker_info = auto_setup_broker()
        print(f"[BROKER] 扫描完成: {len(_broker_info.get('symbols',[]))} 个品种 - {_broker_info.get('symbols',[])}")
    except Exception as _e:
        print(f"[BROKER] 异常: {_e}")
        import traceback; traceback.print_exc()
        _rebuild_params_from_static_list()
        _broker_info = {"broker": "错误", "server": str(_e)[:80], "symbols": list(SYMBOLS), "warnings": [f"自动检测异常: {str(_e)[:100]}"]}
    _broker_ready = True
    print(f"[BROKER] _broker_ready = True")


# ============================================================
# 参数持久化
# ============================================================
def _data_dir():
    """返回数据存储目录(绝对路径) — 优先AppData(无需admin), 兜底EXE目录"""
    try:
        import sys
        if getattr(sys, 'frozen', False):
            # 冻结exe: 优先%APPDATA%\BTC Panel (Program Files可能无写权限)
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                d = os.path.join(appdata, "BTC Panel")
                os.makedirs(d, exist_ok=True)
                return d
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))
    except:
        return os.getcwd()

def load_params(symbol=None, filepath="panel_params.json"):
    """加载参数。如果提供 symbol, 优先加载品种专属文件 (panel_params_BTCUSD.json)"""
    base = _data_dir()
    if symbol:
        sym_file = os.path.join(base, f"panel_params_{symbol}.json")
        # 品种专属默认值 (覆盖 DEFAULT_PARAMS 中的 BTC 默认值)
        sp = SYMBOL_PARAMS.get(symbol, {})
        sc = STRATEGY_PARAMS.get(symbol, {})
        if os.path.exists(sym_file):
            try:
                with open(sym_file, encoding="utf-8") as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, OSError, ValueError) as e:
                # JSON损坏或无法读取 — 记录错误但继续用品种默认值
                print(f"[load_params] 无法解析 {sym_file}: {e}", file=sys.stderr)
                raw = {}
            return {**DEFAULT_PARAMS, **sp, **sc, **raw}
        # 迁移: 如果旧通用文件存在, 复制一份作为品种初始值
        legacy_file = os.path.join(base, filepath)
        if os.path.exists(legacy_file):
            try:
                with open(legacy_file, encoding="utf-8") as f:
                    legacy = {**DEFAULT_PARAMS, **json.load(f)}
            except (json.JSONDecodeError, OSError, ValueError):
                legacy = dict(DEFAULT_PARAMS)
            legacy.update(sp)
            legacy.update(sc)
            save_params(legacy, symbol=symbol)
            return legacy
        # 品种文件不存在、无旧文件 — 用品种默认值
        return {**DEFAULT_PARAMS, **sp, **sc}
    # 未指定symbol: 通读通用文件
    generic = os.path.join(base, filepath)
    if os.path.exists(generic):
        try:
            with open(generic, encoding="utf-8") as f:
                return {**DEFAULT_PARAMS, **json.load(f)}
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return dict(DEFAULT_PARAMS)

def save_params(params, symbol=None, filepath="panel_params.json"):
    base = _data_dir()
    if symbol:
        filepath = os.path.join(base, f"panel_params_{symbol}.json")
    else:
        filepath = os.path.join(base, filepath)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)

def get_params_file(symbol: str) -> str:
    """返回品种专属参数文件路径(绝对路径)"""
    name = f"panel_params_{symbol.upper()}.json" if symbol else "panel_params.json"
    return os.path.join(_data_dir(), name)

# ============================================================
# 当日盈亏追踪
# ============================================================
_daily_pnl_cache = {"date": None, "start_balance": None, "pnl": 0.0}

def get_daily_pnl() -> dict:
    """
    追踪当日盈亏, 从MT5账户读取余额, 带RLock保护
    返回: {"date", "start_balance", "pnl", "balance", "equity"}
    """
    global _daily_pnl_cache
    today = datetime.now().strftime("%Y%m%d")
    s = _daily_pnl_cache

    with _mt5_lock:
        if not mt5_ensure():
            return {"date": today, "start_balance": s.get("start_balance"),
                    "pnl": s.get("pnl", 0.0), "balance": 0, "equity": 0}
        acct = mt5.account_info()
        if not acct:
            return {"date": today, "start_balance": s.get("start_balance"),
                    "pnl": s.get("pnl", 0.0), "balance": 0, "equity": 0}

        balance = acct.balance
        equity = acct.equity

        if s["date"] != today or s["start_balance"] is None:
            s["date"] = today
            s["start_balance"] = balance
            s["pnl"] = 0.0
        else:
            s["pnl"] = balance - s["start_balance"]

        return {"date": s["date"], "start_balance": s["start_balance"],
                "pnl": s["pnl"], "balance": balance, "equity": equity}

# ============================================================
# MT5 数据获取 (使用全局连接, 带RLock)
# ============================================================
def fetch_all_mt5_data(symbol: str, include_h1: bool = True) -> Optional[dict]:
    """获取多时间框架K线数据，带重试和单周期容错"""
    def _do_one_tf(s, tf, count):
        """获取单个周期的K线，失败返回None"""
        try:
            rates = mt5.copy_rates_from_pos(s, tf, 0, count)
            if rates is not None and len(rates) > 0:
                return [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rates]
        except:
            pass
        return None

    def _do():
        real_sym = _real_symbol(symbol)  # 券商实际名称
        mt5.symbol_select(real_sym, True)
        frames = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1,
        }
        result = {}
        failed_tfs = []
        for name, tf in frames.items():
            if name == "H1" and not include_h1:
                continue
            bars = _do_one_tf(real_sym, tf, 200)
            if bars:
                result[name] = bars
            else:
                failed_tfs.append(name)

        # 至少需要核心周期（H1/H4/D1）中2个有效
        core = ["H1", "H4", "D1"]
        core_ok = sum(1 for c in core if c in result)
        if core_ok < 2:
            raise RuntimeError(f"核心周期不足 有效:{core_ok}/{len(core)}")
        if failed_tfs:
            raise RuntimeError(f"部分周期超时: {failed_tfs}")  # 会被重试
        return result

    # 最多重试2次；重试可以恢复超时的周期
    for attempt in range(3):
        result, ok = mt5_call_with_retry(f"K线获取(尝试{attempt+1})", _do, retries=0)
        if ok and result:
            return result
        if attempt < 2:
            time.sleep(1.0 * (attempt + 1))  # 递增等待
    return None


def fetch_dashboard_data(symbol: str, params: dict):
    """
    面板全能数据获取 — 一次调用返回面板所需的全部数据
    返回: (data_dict, ml_dict, resonance_list, filter_info_dict)

    data_dict 包含: price, ask, bid, position, balance, equity, broker, login
    ml_dict 包含:   signal, ready, confidence (简化版ML信号, 基于共振聚合)
    resonance_list: 多时间框架共振信号列表
    filter_info:    风控过滤信息
    """
    # --- 1. 基础数据 (价格/账户/持仓) ---
    data = {}
    try:
        tick, info = get_mt5_tick(symbol)
        if tick and info:
            data["price"] = tick.bid
            data["ask"] = tick.ask
            data["bid"] = tick.bid
            data["spread"] = tick.ask - tick.bid

        acct = get_mt5_account_info()
        if acct:
            data["balance"] = acct.get("balance", 0)
            data["equity"] = acct.get("equity", 0)
            data["broker"] = acct.get("server", "")
            data["login"] = str(acct.get("login", ""))

        positions = get_mt5_positions(symbol)
        if positions:
            p = positions[0]
            side = "多" if p.type == 0 else "空"
            data["position"] = {
                "side": side,
                "entry": p.price_open,
                "volume": p.volume,
                "profit": p.profit,
                "ticket": p.ticket,
            }
        else:
            data["position"] = None
    except Exception:
        pass

    # --- 2. 共振信号 ---
    # name映射: 面板详情区用 "1h"/"4h"/"1d" 匹配 脉冲层/谐波段/基频面
    _TF_NAME_MAP = {"M5": "1h", "M15": "1h", "H1": "1h", "H4": "4h", "D1": "1d"}
    resonance = []
    try:
        raw_bars = fetch_all_mt5_data(symbol, include_h1=True)
        if raw_bars:
            for tf in ["M5", "M15", "H1", "H4", "D1"]:
                if tf not in raw_bars:
                    continue
                sig = calc_signal(raw_bars[tf], params)
                resonance.append({
                    "timeframe": tf,
                    "name": _TF_NAME_MAP.get(tf, tf),   # 面板详情匹配用
                    "signal": sig["signal"],
                    "strength": sig["strength"],
                    "reasons": sig.get("reasons", []),
                    "rsi": sig.get("rsi", 50),
                    "adx": sig.get("adx", 0),
                    "atr": sig.get("atr", 0),
                })
    except Exception:
        pass

    # --- 3. ML引擎信号 (基于共振聚合, 强化过滤) ---
    ml = {"signal": 0, "ready": False, "confidence": 0.0}
    try:
        if resonance and len(resonance) >= 3:
            # 按时间框架分组: 脉冲层(1h)=M5+M15+H1, 谐波段(4h)=H4, 基频面(1d)=D1
            groups = {
                "脉冲层": [r for r in resonance if r["name"] == "1h"],
                "谐波段": [r for r in resonance if r["name"] == "4h"],
                "基频面": [r for r in resonance if r["name"] == "1d"],
            }
            
            # 每个组取信号（组内多数票）
            group_signals = {}
            for gname, rs in groups.items():
                if not rs:
                    continue
                buys = sum(1 for r in rs if r["signal"] == 1)
                sells = sum(1 for r in rs if r["signal"] == -1)
                if buys > sells:
                    group_signals[gname] = 1
                elif sells > buys:
                    group_signals[gname] = -1
                else:
                    group_signals[gname] = 0  # 平局
            
            # 层级加权 (基频面权重2, 谐波段权重1.5, 脉冲层权重1)
            weighted = {"BUY": 0.0, "SELL": 0.0}
            for gname, sig in group_signals.items():
                w = {"基频面": 2.0, "谐波段": 1.5, "脉冲层": 1.0}.get(gname, 1.0)
                if sig == 1:
                    weighted["BUY"] += w
                elif sig == -1:
                    weighted["SELL"] += w
            
            # 判断方向，要求 >1.0 加权优势
            if weighted["BUY"] > 1.0 and weighted["BUY"] > weighted["SELL"]:
                ml["signal"] = 1
                ml["confidence"] = min(0.95, weighted["BUY"] / (weighted["BUY"] + weighted["SELL"]))
            elif weighted["SELL"] > 1.0 and weighted["SELL"] > weighted["BUY"]:
                ml["signal"] = -1
                ml["confidence"] = min(0.95, weighted["SELL"] / (weighted["SELL"] + weighted["BUY"]))
            
            # 附加组信号信息给面板
            ml["group_signals"] = group_signals
            ml["ready"] = True
            
            # 强烈信号标记（当基频面和谐波段同向且脉冲层同向或中性）
            if group_signals.get("基频面") == group_signals.get("谐波段"):
                if group_signals.get("脉冲层") == group_signals.get("基频面"):
                    ml["strong"] = True
                elif group_signals.get("脉冲层") == 0:
                    ml["strong"] = True
                else:
                    ml["strong"] = False
            else:
                ml["strong"] = False
    except Exception:
        pass

    # --- 4. 过滤信息 ---
    filter_info = {}
    try:
        # 点差检查
        spread = data.get("spread", 0)
        price = data.get("price", 1)
        if price > 0 and spread > 0:
            filter_info["spread_pct"] = spread / price * 100

        # HMM状态 (直接引用全局变量)
        filter_info["hmm_state"] = _hmm_state.get("state", -1)
        filter_info["hmm_label"] = ""
        state = _hmm_state.get("state")
        if state == 0:
            filter_info["hmm_label"] = "强势趋势"
        elif state == 1:
            filter_info["hmm_label"] = "窄幅整理"
        elif state == 2:
            filter_info["hmm_label"] = "高波回撤"

        # 日盈亏
        daily = get_daily_pnl()
        filter_info["daily_pnl"] = daily.get("pnl", 0)

        # 更新HMM状态
        update_hmm_state(symbol)
    except Exception:
        pass

    return data, ml, resonance, filter_info

def get_mt5_account_info() -> Optional[dict]:
    """获取账户信息，带自动重试"""
    def _do():
        acct = mt5.account_info()
        if acct:
            return {"balance": acct.balance, "equity": acct.equity,
                    "margin": acct.margin, "free_margin": acct.margin_free,
                    "login": acct.login, "server": acct.server}
        return None
    result, ok = mt5_call_with_retry("账户查询", _do, retries=1)
    return result if ok else None

def get_mt5_positions(symbol: str = "") -> list:
    """获取持仓，带自动重试"""
    real_sym = _real_symbol(symbol) if symbol else ""
    def _do():
        if real_sym:
            mt5.symbol_select(real_sym, True)
            positions = mt5.positions_get(symbol=real_sym)
        else:
            positions = mt5.positions_get()
        return list(positions or [])
    result, ok = mt5_call_with_retry("持仓查询", _do, retries=1)
    return result if ok else []

def get_mt5_tick(symbol: str):
    """获取最新tick，带自动重试。返回(symbol_info_tick, symbol_info)或(None, None)"""
    real_sym = _real_symbol(symbol)
    if not real_sym:
        print(f"[TICK] {symbol}: _real_symbol 返回空, 跳过")
        return (None, None)

    # 检查是否已标记为不可用 (避免无限重试)
    if real_sym in _DEAD_SYMBOLS:
        ts, reason = _DEAD_SYMBOLS[real_sym]
        if time.time() - ts < _DEAD_SYMBOL_TTL:
            return (None, None)  # 静默跳过
        else:
            del _DEAD_SYMBOLS[real_sym]  # TTL过期, 重试一次
            print(f"[TICK] {real_sym} 死缓存过期, 重新尝试...")

    def _do():
        # 先试券商映射名
        ok = mt5.symbol_select(real_sym, True)
        if not ok:
            ok = mt5.symbol_select(real_sym, False)

        # 映射名失败 → 尝试原始配置名 (有的券商品种不在symbols_get()列表但可直接访问)
        tick = mt5.symbol_info_tick(real_sym)
        info = mt5.symbol_info(real_sym)

        # 大小写变体重试 (如 XAUUSD.S → XAUUSD.s)
        if (tick is None or info is None) and "." in real_sym:
            base, ext = real_sym.rsplit(".", 1)
            alt = f"{base}.{ext.lower() if ext.isupper() else ext.upper()}"
            if alt != real_sym:
                mt5.symbol_select(alt, True)
                tick2 = mt5.symbol_info_tick(alt)
                info2 = mt5.symbol_info(alt)
                if tick2 is not None and info2 is not None:
                    tick, info = tick2, info2
                    _BROKER_MAP[symbol] = alt  # 更新为正确的大小写
                    _DEAD_SYMBOLS.pop(real_sym, None)
                    print(f"[TICK] ✅ {alt} (大小写变体命中), 更新映射")
        use_name = real_sym

        if (tick is None or info is None) and real_sym != symbol:
            # 用原始名重试
            mt5.symbol_select(symbol, True)
            tick2 = mt5.symbol_info_tick(symbol)
            info2 = mt5.symbol_info(symbol)
            if tick2 is not None and info2 is not None:
                tick, info, use_name = tick2, info2, symbol
                # 更新映射缓存, 下次直接用
                _BROKER_MAP[symbol] = symbol
                _DEAD_SYMBOLS.pop(real_sym, None)
                print(f"[TICK] ✅ {symbol} 直接可用 (回退成功), 更新映射")

        if tick is None or info is None:
            if info and info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
                print(f"[TICK] {real_sym} 市场关闭 (trade_mode={info.trade_mode})")
            else:
                # 标记为不可用, 避免后续无限重试
                _DEAD_SYMBOLS[real_sym] = (time.time(), "symbol_info返回None")
            raise RuntimeError("tick/info为None")
        # 可用了, 从死缓存移除
        _DEAD_SYMBOLS.pop(real_sym, None)
        return (tick, info)
    result, ok = mt5_call_with_retry("报价获取", _do, retries=1)
    return result if ok else (None, None)


def _ensure_symbols_ready(symbols: list):
    """
    券商切换后，确保所有品种可读取数据
    用于 auto_setup_broker 后调用
    """
    for sym in symbols:
        real = _real_symbol(sym)
        print(f"[INIT] 初始化 {sym} → {real} ...")
        def _do():
            # 尝试多种方式激活品种 (含大小写变体)
            ok = mt5.symbol_select(real, True)
            if not ok:
                ok = mt5.symbol_select(real, False)
            if not ok:
                ok = mt5.symbol_select(sym, True)
            # 用 _verify_symbol_readable 做大小写回退
            working_name = _verify_symbol_readable(real)
            if working_name is None:
                # 尝试原始名
                working_name = _verify_symbol_readable(sym)
            if working_name is None:
                raise RuntimeError(f"symbol_info({real}) 返回 None (品种不存在)")
            # 如果大小写修正了, 更新映射
            if working_name != real:
                _BROKER_MAP[sym] = working_name
                print(f"[INIT] ⚠️ 名称修正: {real} → {working_name}")
            # 验证可读
            info = mt5.symbol_info(working_name)
            if info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
                print(f"[INIT] ⚠️ {sym} 交易模式={info.trade_mode} (非全模式, 可能市场关闭)")
            # symbol_select 失败只是警告, 不影响后续使用
            if not ok:
                print(f"[INIT] ⚠️ {real} symbol_select 失败但不影响数据读取")
            return True
        result, ok = mt5_call_with_retry(f"品种初始化{sym}", _do, retries=1)
        if ok:
            print(f"[INIT] ✅ {sym} 就绪")
            # 预检测填充模式
            _get_filling_mode(sym)
        else:
            print(f"[INIT] ❌ {sym} 初始化失败")
    print(f"[INIT] 品种就绪检查完成")

# ============================================================
# 信号计算
# ============================================================
def calc_signal(bars: List[Bar], params: dict) -> dict:
    """计算单周期交易信号"""
    if not bars or len(bars) < 30:
        return {"signal": 0, "strength": 0, "reasons": ["数据不足"]}
    closes = np.array([b.close for b in bars])
    highs = np.array([b.high for b in bars])
    lows = np.array([b.low for b in bars])
    ema = calc_ema(closes, params.get("ema_period", 20))
    rsi = calc_rsi(closes, params.get("rsi_period", 14))
    atr_list = calc_atr(highs, lows, closes, 14)
    atr = atr_list[-1] if len(atr_list) > 0 else 0.0
    adx_list = calc_adx(highs, lows, closes, params.get("adx_period", 14))
    adx = adx_list[-1] if len(adx_list) > 0 else 0.0
    last = bars[-1]
    signal = 0
    reasons = []
    if last.close > ema[-1]:
        signal += 1
        reasons.append("EMA向上")
    else:
        signal -= 1
        reasons.append("EMA向下")
    rsi_v = rsi[-1]
    if rsi_v > params.get("rsi_long_lo", 50):
        signal += 1
        reasons.append(f"RSI={rsi_v:.1f}")
    elif rsi_v < params.get("rsi_short_hi", 50):
        signal -= 1
        reasons.append(f"RSI={rsi_v:.1f}")
    if adx > params.get("adx_threshold", 25):
        reasons.append(f"ADX={adx:.1f}(强趋势)")
    return {"signal": 1 if signal > 0 else (-1 if signal < 0 else 0),
            "strength": abs(signal), "reasons": reasons,
            "rsi": rsi_v, "adx": adx, "atr": atr}

def calc_resonance(symbol: str, params: dict) -> list:
    """多时间框架共振分析, 返回各周期信号列表"""
    data = fetch_all_mt5_data(symbol, include_h1=False)
    if not data:
        return []
    result = []
    for tf in ["M5", "M15", "H1", "H4", "D1"]:
        if tf not in data:
            continue
        sig = calc_signal(data[tf], params)
        result.append({"timeframe": tf, "signal": sig["signal"],
                        "strength": sig["strength"], "reasons": sig["reasons"]})
    return result

# ============================================================
# HMM 市场状态判断
# ============================================================
_hmm_state = {"state": -1, "confidence": 0.0, "expected_duration": 0}

def update_hmm_state(symbol: str):
    """更新HMM市场状态 (简化版: 基于波动率和趋势方向)"""
    global _hmm_state
    data = fetch_all_mt5_data(symbol, include_h1=False)
    if not data or "H4" not in data:
        return
    bars = data["H4"]
    closes = np.array([b.close for b in bars[-50:]])
    if len(closes) < 30:
        return
    returns = np.diff(closes) / closes[:-1]
    vol = np.std(returns) * np.sqrt(6 * 24)
    sma20 = np.mean(closes[-20:])
    sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma20
    trend = 1 if sma20 > sma50 else -1
    hist_vols = []
    for i in range(30, len(closes)):
        h = np.std(np.diff(closes[:i]) / closes[:i-1])
        hist_vols.append(h)
    vol_threshold = np.percentile(hist_vols, 80) if len(hist_vols) > 10 else vol
    if vol > vol_threshold * 1.2:
        if trend == -1:
            _hmm_state = {"state": 2, "confidence": 0.9, "expected_duration": 8}
        else:
            _hmm_state = {"state": 0, "confidence": 0.7, "expected_duration": 12}
    else:
        _hmm_state = {"state": 1, "confidence": 0.6, "expected_duration": 20}

def get_trade_signal(symbol: str, params: dict) -> dict:
    """
    综合交易信号（供手工开仓参考）
    返回: {
        "direction": 1(做多) / -1(做空) / 0(观望),
        "strength": "强烈" / "中等" / "弱",
        "confidence": 0.0~1.0,
        "reason": "文本描述",
        "components": {  # 各组件信号
            "base": 1/-1/0,
            "harmonic": 1/-1/0, 
            "pulse": 1/-1/0,
            "hmm": 1/-1/0,
            "atr_filter": bool,
            "daily_filter": bool
        }
    }
    """
    try:
        data, ml, resonance, filter_info = fetch_dashboard_data(symbol, params)
        hmm_state = filter_info.get("hmm_state", -1)
        
        # 1. 解析组件信号
        group_sigs = ml.get("group_signals", {})
        base_sig = group_sigs.get("基频面", 0)      # 长期
        harmonic_sig = group_sigs.get("谐波段", 0)   # 中期
        pulse_sig = group_sigs.get("脉冲层", 0)      # 短期
        
        # 2. HMM信号转换 (状态->方向)
        hmm_sig = 0
        if hmm_state == 0:  # 强势趋势 → 做多
            hmm_sig = 1
        elif hmm_state == 2:  # 高波回撤 → 做空
            hmm_sig = -1
        
        # 3. 加权决策（基频面权重最高）
        weighted = {"BUY": 0.0, "SELL": 0.0}
        if base_sig == 1:
            weighted["BUY"] += 2.5
        elif base_sig == -1:
            weighted["SELL"] += 2.5
            
        if harmonic_sig == 1:
            weighted["BUY"] += 2.0
        elif harmonic_sig == -1:
            weighted["SELL"] += 2.0
            
        if pulse_sig == 1:
            weighted["BUY"] += 1.0
        elif pulse_sig == -1:
            weighted["SELL"] += 1.0
            
        if hmm_sig == 1:
            weighted["BUY"] += 1.5
        elif hmm_sig == -1:
            weighted["SELL"] += 1.5
        
        # 4. 决策 (基频面+谐波段同向就足够强)
        direction = 0
        confidence = 0.0
        strength = "弱"
        
        # 如果基频面和谐波段同向，那就是强烈信号
        if base_sig == harmonic_sig and base_sig != 0:
            direction = base_sig
            confidence = 0.8  # 基频+谐波同向就是80%置信度
        # 否则用加权总分≥3.0（更宽松）
        elif weighted["BUY"] >= 3.0 and weighted["BUY"] > weighted["SELL"]:
            direction = 1
            confidence = weighted["BUY"] / (weighted["BUY"] + weighted["SELL"])
        elif weighted["SELL"] >= 3.0 and weighted["SELL"] > weighted["BUY"]:
            direction = -1
            confidence = weighted["SELL"] / (weighted["SELL"] + weighted["BUY"])
        
        # 5. 强度判定
        if confidence >= 0.75:
            strength = "强烈"
        elif confidence >= 0.6:
            strength = "中等"
        elif confidence > 0:
            strength = "弱"
        
        # 6. 理由构建
        reasons = []
        if base_sig == 1:
            reasons.append("基频面看多")
        elif base_sig == -1:
            reasons.append("基频面看空")
            
        if harmonic_sig == 1:
            reasons.append("谐波段看多")
        elif harmonic_sig == -1:
            reasons.append("谐波段看空")
            
        if pulse_sig == 1:
            reasons.append("脉冲层看多")
        elif pulse_sig == -1:
            reasons.append("脉冲层看空")
            
        if hmm_sig == 1:
            reasons.append("HMM强势趋势")
        elif hmm_sig == -1:
            reasons.append("HMM高波回撤")
        
        # 7. 过滤条件检查（供参考）
        atr_ok = filter_info.get("spread_pct", 0) <= float(params.get("max_spread_pct", 0.15))
        daily_ok = abs(filter_info.get("daily_pnl", 0)) < abs(float(params.get("max_daily_loss", 100)))
        
        # 8. 冲突检测: ML引擎 vs 加权投票
        ml_dir = ml.get("signal", 0) if ml and ml.get("ready") else 0
        ml_confidence = ml.get("confidence", 0) if ml and ml.get("ready") else 0
        # 只有当两者都有效且方向相反时才算冲突
        conflict = (direction != 0 and ml_dir != 0 and direction != ml_dir)
        
        # 9. 如果冲突且方向强度弱 → 降级为观望
        if conflict and strength == "弱":
            direction = 0
            confidence = 0
            strength = "弱"
            reasons = ["信号分歧:加权与引擎方向不一致, 建议观望"]
        
        return {
            "direction": direction,
            "strength": strength,
            "confidence": confidence,
            "reason": " + ".join(reasons) if reasons else "观望",
            "components": {
                "base": base_sig,
                "harmonic": harmonic_sig,
                "pulse": pulse_sig,
                "hmm": hmm_sig,
                "atr_filter": atr_ok,
                "daily_filter": daily_ok
            },
            "weighted": weighted,
            "raw_ml": ml,
            "ml_dir": ml_dir,
            "ml_confidence": ml_confidence,
            "conflict": conflict
        }
    except Exception as e:
        return {
            "direction": 0,
            "strength": "错误",
            "confidence": 0.0,
            "reason": f"计算错误: {e}",
            "components": {}
        }

# ============================================================
# 风险控制检查
# ============================================================
def check_risk_gates(symbol: str, side: str, params: dict) -> Tuple[bool, str]:
    """检查风控闸门, 返回(passed, reason)"""
    daily = get_daily_pnl()
    if daily.get("pnl", 0) <= -abs(float(params.get("max_daily_loss", 100))):
        return False, f"日亏${abs(daily['pnl']):.0f}超限"

    tick, info = get_mt5_tick(symbol)
    if tick and info:
        spread_pct = (tick.ask - tick.bid) / tick.bid * 100
        if spread_pct > float(params.get("max_spread_pct", 0.15)):
            return False, f"点差{spread_pct:.3f}%过高"

    with _mt5_lock:
        if mt5_ensure():
            real_sym = _real_symbol(symbol)
            rates = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_H4, 0, 30)
            if rates is not None and len(rates) > 14:
                trs = []
                for i in range(1, len(rates)):
                    h, l, c = rates[i][2], rates[i][3], rates[i-1][4]
                    trs.append(max(h-l, abs(h-c), abs(l-c)))
                atr = np.mean(trs[-14:])
                atr_avg = np.mean(trs) if len(trs) >= 30 else atr
                if atr > atr_avg * float(params.get("atr_spike_mult", 2.0)):
                    return False, f"ATR飙升{atr/atr_avg:.1f}x"

    if _hmm_state.get("state") == 2 and side == "BUY":
        return False, "HMM高波回撤, 不做多"
    if _hmm_state.get("state") == 0 and side == "SELL":
        return False, "HMM强势趋势, 不做空"
    return True, ""

# ============================================================
# 交易执行 (核心函数, 带RLock, 不关闭MT5)
# ============================================================
def execute_trade(action: str, symbol: str, params: dict = None) -> dict:
    """
    执行交易指令
    action: "BUY", "SELL", "CLOSE"
    symbol: 交易品种
    params: 参数字典 (不传则自动加载)
    返回: {"ok": bool, "msg": str, ...}
    """
    if params is None:
        # 加载品种专属参数 (切到BTC/黄金时各自独立)
        params = load_params(symbol)

    sym_params, _, _ = _load_symbol_params(symbol)
    real_sym = _real_symbol(symbol)

    with _mt5_lock:
        if not mt5_ensure():
            return {"ok": False, "msg": "MT5连接失败"}

        try:
            mt5.symbol_select(real_sym, True)
            tick = mt5.symbol_info_tick(real_sym)
            info = mt5.symbol_info(real_sym)
            if not tick or not info:
                return {"ok": False, "msg": "无法获取报价或品种信息"}

            # 品种报价精度 (BTC通常digits=2, 黄金digits=2, 外汇digits=5)
            digits = info.digits

            # ========== 平仓 ==========
            if action == "CLOSE":
                positions = mt5.positions_get(symbol=real_sym)
                if not positions:
                    return {"ok": True, "msg": "无持仓"}
                for p in positions:
                    # AutoTrading 检查
                    at_info = mt5.terminal_info()
                    if at_info and not at_info.trade_allowed:
                        return {"ok": False, "msg": "MT5 AlgoTrading未开启 — 点击MT5顶部 ⚡AlgoTrading 按钮"}
                    close_price = tick.bid if p.type == 0 else tick.ask
                    close_price = round(close_price, digits)
                    req = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": p.symbol,
                        "volume": p.volume,
                        "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
                        "position": p.ticket,
                        "price": close_price,
                        "magic": 60107,
                        "comment": "BTC-AI-CLOSE",
                        "type_filling": _get_filling_mode(symbol)
                    }
                    result = mt5.order_send(req)
                    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
                        return {"ok": False, "msg": f"平仓失败: {result.comment if result else '未知'}"}
                return {"ok": True, "msg": "已平仓"}

            # ========== 开仓 ==========
            is_buy = (action == "BUY")
            order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            price = round(tick.ask if is_buy else tick.bid, digits)

            # --- SL/TP 距离 (点数) ---
            sl_atr_mult = float(params.get("sl_atr_mult", 1.5) or sym_params.get("sl_atr_mult", 1.5))
            tp_atr_mult = float(params.get("tp_atr_mult", 2.0) or sym_params.get("tp_atr_mult", 2.0))
            sl_min_cfg = float(params.get("sl_min", 800) or sym_params.get("sl_min", 800))
            tp_min_cfg = float(params.get("tp_min", 1500) or sym_params.get("tp_min", 1500))

            # 从H4计算ATR (转换为点数)
            rates = mt5.copy_rates_from_pos(real_sym, mt5.TIMEFRAME_H4, 0, 20)
            sl_points = int(sl_min_cfg)
            tp_points = int(tp_min_cfg)
            point = info.point
            if rates is not None and len(rates) > 14:
                trs = []
                for i in range(1, len(rates)):
                    h, l, c = rates[i][2], rates[i][3], rates[i-1][4]
                    trs.append(max(h-l, abs(h-c), abs(l-c)))
                atr_price = np.mean(trs[-14:])
                atr_points = atr_price / point if point > 0 else atr_price * 10000
                sl_points = max(int(sl_min_cfg), int(atr_points * sl_atr_mult))
                tp_points = max(int(tp_min_cfg), int(atr_points * tp_atr_mult))

            # --- SL/TP 价格 (按品种精度取整, MT5要求) ---
            if is_buy:
                sl_price = round(price - sl_points * point, digits)
                tp_price = round(price + tp_points * point, digits)
            else:
                sl_price = round(price + sl_points * point, digits)
                tp_price = round(price - tp_points * point, digits)

            # --- 手数计算 ---
            lot_fixed = float(params.get("lot_fixed", 0) or sym_params.get("lot_fixed", 0))
            lot_min = max(float(params.get("lot_min", 0.01) or sym_params.get("lot_min", 0.01)),
                         info.volume_min or 0.01)

            if lot_fixed > 0:
                lot = lot_fixed
            else:
                risk = float(params.get("risk_per_trade", 20) or sym_params.get("risk_per_trade", 20))
                point_value = point * price  # 1点的价格价值 (近似)
                risk_per_point = point_value * (info.trade_contract_size or 1)
                if risk_per_point > 0 and sl_points > 0:
                    lot = risk / (sl_points * risk_per_point)
                else:
                    lot = lot_min
                lot = max(lot_min, round(lot, 2))

            lot = max(lot_min, min(lot, info.volume_max or 100))
            lot = math.floor(lot * 100) / 100  # 向下取整到0.01手

            if lot <= 0:
                return {"ok": False, "msg": f"计算手数异常: lot={lot}"}

            # --- 发送订单前检查 AutoTrading ---
            at_info = mt5.terminal_info()
            if at_info and not at_info.trade_allowed:
                return {"ok": False, "msg": "MT5 AlgoTrading未开启 — 点击MT5顶部 ⚡AlgoTrading 按钮"}

            # --- 发送订单 ---
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": real_sym,
                "volume": lot,
                "type": order_type,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "magic": 60107,
                "comment": "BTC-AI-OPEN",
                "type_filling": _get_filling_mode(symbol)
            }
            result = mt5.order_send(req)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {"ok": True,
                        "msg": f"开仓成功 {action} {lot}手 SL:{sl_price} TP:{tp_price}",
                        "ticket": result.order, "sl": sl_price, "tp": tp_price,
                        "sl_points": sl_points, "tp_points": tp_points}
            else:
                err = result.comment if result else "未知错误"
                return {"ok": False, "msg": f"开仓失败: {err}"}
        except Exception as e:
            return {"ok": False, "msg": f"执行异常: {e}"}

# ============================================================
# 修改SL (移动止损用)
# ============================================================
def modify_sl(ticket: int, new_sl: float) -> bool:
    """修改持仓止损价, 带重试。new_sl 应按品种精度已取整"""
    def _do():
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False
        p = positions[0]
        # 获取品种精度, 取整SL
        info = mt5.symbol_info(p.symbol)
        digits = info.digits if info else 2
        sl = round(float(new_sl), digits)
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": p.ticket,
            "symbol": p.symbol,
            "sl": sl,
            "tp": p.tp,
            "magic": 60107
        }
        result = mt5.order_send(req)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"SL修改失败: {result.comment if result else '无响应'}")
        return True
    result, ok = mt5_call_with_retry("止损修改", _do, retries=2, backoff=1.5)
    return result if ok else False

# ============================================================
# 交易时间过滤
# ============================================================
def is_trade_time_allowed(params: dict) -> Tuple[bool, str]:
    """检查当前是否在允许交易的时间段内 (已关闭时间限制)"""
    # 注释掉原有的时间限制逻辑，永远允许交易
    # now = datetime.now()
    # after_hour = int(params.get("no_trade_after_hour", 22))
    # before_hour = int(params.get("no_trade_before_hour", 0))
    # current_hour = now.hour
    # if current_hour >= after_hour:
    #     return False, f"已过{after_hour}点, 停止开仓(避免过夜费)"
    # if 0 < before_hour <= current_hour:
    #     return False, f"未到{before_hour}点, 不允许开仓"
    return True, "交易时间限制已关闭"
