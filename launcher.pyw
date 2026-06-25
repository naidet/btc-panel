#!/usr/bin/env python3
"""
BTC面板启动器 — 闪屏先行 + 后台加载
双击后 0.1s 显示闪屏，加载重型依赖时实时反馈进度
"""
import tkinter as tk


def main():
    # ============================================================
    # 1. 闪屏 — 0.1秒内显示
    # ============================================================
    splash = tk.Tk()
    splash.overrideredirect(True)
    splash.configure(bg="#0d1117")
    splash.attributes("-topmost", True)

    # 居中定位
    w, h = 400, 210
    sx = (splash.winfo_screenwidth() - w) // 2
    sy = (splash.winfo_screenheight() - h) // 2
    splash.geometry(f"{w}x{h}+{sx}+{sy}")

    # --- 闪屏内容 ---
    # BTC 橙标
    icon = tk.Label(
        splash, text="₿", font=("Segoe UI", 44, "bold"),
        fg="#f7931a", bg="#0d1117"
    )
    icon.pack(pady=(35, 0))

    title = tk.Label(
        splash, text="BTC AI 交易面板 v2.1",
        font=("Microsoft YaHei", 13, "bold"),
        fg="#e0e0e0", bg="#0d1117"
    )
    title.pack()

    ver = tk.Label(
        splash, text="账户 #60107268  |  高级开发工程师",
        font=("Microsoft YaHei", 8),
        fg="#555555", bg="#0d1117"
    )
    ver.pack(pady=(0, 10))

    status = tk.Label(
        splash, text="正在加载...",
        font=("Microsoft YaHei", 9),
        fg="#888888", bg="#0d1117"
    )
    status.pack()

    # 进度条
    bar_bg = tk.Frame(splash, bg="#2a2a2a", height=4, width=300)
    bar_bg.pack(pady=(8, 0))
    bar_bg.pack_propagate(False)
    bar_fill = tk.Frame(bar_bg, bg="#f7931a", width=0, height=4)
    bar_fill.place(x=0, y=0, height=4)

    splash.update()

    # ============================================================
    # 2. 加载重型依赖 (进度条逐步推进)
    # ============================================================
    import sys, os, time

    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)
    os.chdir(base)

    steps = [
        (30,  "加载 tkinter..."),
        (60,  "加载 numpy + pandas..."),
        (120, "加载 MetaTrader5..."),
        (180, "加载策略 + ML 模型..."),
        (250, "初始化面板..."),
    ]

    def progress(px, msg):
        status.config(text=msg)
        bar_fill.place_configure(width=px)
        splash.update()

    # Step 1: tkinter 已加载
    progress(*steps[0])

    # Step 2: numpy + pandas (btc_trader 会触发)
    progress(*steps[1])
    import numpy as np  # noqa: F401 — 预热, 让 btc_panel 的 import 命中缓存

    # Step 3: MetaTrader5
    progress(*steps[2])
    import MetaTrader5  # noqa: F401

    # Step 4: btc_trader + 策略
    progress(*steps[3])
    from btc_trader import calc_ema, calc_rsi, calc_atr, calc_adx, Bar  # noqa: F401

    # Step 5: btc_panel 主模块
    progress(*steps[4])
    from btc_panel import BTCPanel

    # ============================================================
    # 3. 先创建面板窗口(立即可见) → 再关闭闪屏 → 启动主循环
    # ============================================================
    status.config(text="✓ 启动完成", fg="#00ff88")
    bar_fill.place_configure(width=300)
    splash.update()

    app = BTCPanel()         # 创建窗口 (__init__ 中已显示窗口)
    splash.destroy()         # 关闭闪屏
    app.run()                # 进入主循环


if __name__ == "__main__":
    main()
