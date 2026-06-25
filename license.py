"""
BTC 交易面板 — 授权验证模块 v2
================================
方案: 密钥(到期日期+类型+签名) + 本地存储(密钥+HWID绑定)
防止: 复制密钥到其他机器 → HWID不匹配 → 拒绝

注册表: HKCU\Software\BTCPanel\License = "key|hwid"
"""

import hashlib
import hmac
import os
import re
import uuid
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict

# ============================================================
# 配置
# ============================================================
SECRET_KEY = b"BTC_PANEL_V3_SECRET_2026"
TRIAL_DAYS = 3
REG_PATH = r"Software\BTCPanel"

# ============================================================
# 机器码
# ============================================================
def get_hwid() -> str:
    parts = []
    try:
        import socket; parts.append(socket.gethostname())
    except: pass
    try:
        parts.append(os.environ.get("COMPUTERNAME", ""))
    except: pass
    try:
        parts.append(os.environ.get("PROCESSOR_IDENTIFIER", ""))
    except: pass
    raw = "|".join(parts)
    if len(raw) < 10:
        raw = str(uuid.getnode()) + str(uuid.uuid4())[:8]
    h = hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
    return "-".join(h[i:i+4] for i in range(0, 12, 4))


# ============================================================
# 密钥系统
# ============================================================
def _sign(data: str) -> str:
    return hmac.new(SECRET_KEY, data.encode(), hashlib.sha256).hexdigest()[:8].upper()


def _encode_expiry(date_str: str) -> str:
    days = (datetime.strptime(date_str, "%Y-%m-%d") - datetime(2024, 1, 1)).days
    return f"{days:04X}"


def _decode_expiry(hex_str: str) -> str:
    days = int(hex_str, 16)
    return (datetime(2024, 1, 1) + timedelta(days=days)).strftime("%Y-%m-%d")


def generate_key(expiry_date: str = "2099-12-31", user_type: str = "full") -> str:
    """生成序列号 (格式: XXXX-XXXX-XXXX-XXXX)"""
    exp = _encode_expiry(expiry_date)       # 4 hex chars
    typ = "00" if user_type == "full" else "01"  # 2 chars
    raw = exp + typ                         # 6 chars → concat sig
    sig = _sign(raw)
    combined = raw + sig                    # 6 + 8 = 14 chars
    import base64
    enc = base64.b32encode(combined.encode()).decode().rstrip("=")
    return "-".join(enc[i:i+4] for i in range(0, len(enc), 4)).upper()


def validate_key(key: str) -> Tuple[bool, str]:
    """验证密钥格式, 返回 (有效, 到期日期或错误)"""
    try:
        k = key.replace("-", "").upper().strip()
        pad = (8 - len(k) % 8) % 8
        k += "=" * pad
        import base64
        dec = base64.b32decode(k).decode()
        if len(dec) < 14:
            return False, "密钥格式错误"
        exp = dec[:4]
        typ = dec[4:6]
        sig = dec[6:]
        expected = _sign(exp + typ)
        if sig != expected:
            return False, "密钥校验失败"
        date = _decode_expiry(exp)
        if datetime.now() > datetime.strptime(date, "%Y-%m-%d"):
            return True, f"已过期:{date}"
        return True, date
    except:
        return False, "密钥无效"


# ============================================================
# 存储
# ============================================================
def _reg_write(value: str):
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as r:
            winreg.SetValueEx(r, "License", 0, winreg.REG_SZ, value)
    except:
        with open("license.dat", "w") as f:
            f.write(value)


def _reg_read() -> Optional[str]:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as r:
            return winreg.QueryValueEx(r, "License")[0]
    except:
        try:
            if os.path.exists("license.dat"):
                with open("license.dat") as f:
                    return f.read().strip()
        except: pass
        return None


def check_license() -> Dict:
    """检查授权, 返回状态字典"""
    hwid = get_hwid()
    data = _reg_read()

    if data:
        parts = data.split("|")
        if len(parts) >= 2:
            key, saved_hwid = parts[0], parts[1]
            valid, exp = validate_key(key)
            if valid and saved_hwid == hwid:
                return {"valid": True, "expiry": exp, "hwid": hwid}
            if not valid and "已过期" in exp:
                return {"valid": False, "expiry": exp, "hwid": hwid, "expired": True}

    if TRIAL_DAYS > 0:
        try:
            tf = "trial_start.dat"
            now = datetime.now()
            if os.path.exists(tf):
                with open(tf) as f:
                    start = datetime.strptime(f.read().strip(), "%Y-%m-%d")
            else:
                start = now
                with open(tf, "w") as f:
                    f.write(start.strftime("%Y-%m-%d"))
            left = TRIAL_DAYS - (now - start).days
            if left >= 0:
                return {"valid": True, "hwid": hwid, "trial": True,
                        "expiry": (start + timedelta(days=TRIAL_DAYS)).strftime("%Y-%m-%d"),
                        "trial_left": left}
        except: pass

    return {"valid": False, "hwid": hwid}


def activate(key: str) -> Tuple[bool, str]:
    """激活, 返回 (成功, 消息)"""
    valid, exp = validate_key(key)
    if not valid:
        return False, exp
    hwid = get_hwid()
    _reg_write(f"{key}|{hwid}")
    return True, f"激活成功! 到期: {exp}"


# ============================================================
# GUI
# ============================================================
def show_license_dialog(hwid: str, trial_left: int = 0, expired: bool = False) -> Optional[str]:
    result = {"key": None}
    root = tk.Tk()
    root.title("BTC 交易面板 — 授权验证")
    root.geometry("450x390")
    root.configure(bg="#1a1a2e")
    root.resizable(False, False)

    tk.Label(root, text="BTC AI 交易面板 v3",
             font=("Microsoft YaHei", 16, "bold"),
             fg="#4dabf7", bg="#1a1a2e").pack(pady=(20, 5))

    if expired:
        tk.Label(root, text="⚠ 授权已过期，请输入新序列号",
                 font=("Microsoft YaHei", 10), fg="#ff4d6a", bg="#1a1a2e").pack()
    elif trial_left > 0:
        tk.Label(root, text=f"试用版 — 剩余 {trial_left} 天",
                 font=("Microsoft YaHei", 10), fg="#ffc107", bg="#1a1a2e").pack()
    else:
        tk.Label(root, text="请输入授权序列号以继续使用",
                 font=("Microsoft YaHei", 10), fg="#7a7a9e", bg="#1a1a2e").pack()

    f = tk.Frame(root, bg="#252540", padx=10, pady=8)
    f.pack(pady=(15, 10), padx=30, fill="x")
    tk.Label(f, text="机器码:", font=("Consolas", 9),
             fg="#7a7a9e", bg="#252540").pack(side="left")
    tk.Label(f, text=hwid, font=("Consolas", 11, "bold"),
             fg="#00d26a", bg="#252540").pack(side="left", padx=8)

    tk.Label(root, text="序列号:", font=("Microsoft YaHei", 9),
             fg="#e0e0e0", bg="#1a1a2e").pack(anchor="w", padx=35, pady=(10, 2))

    ev = tk.StringVar()
    e = tk.Entry(root, textvariable=ev, font=("Consolas", 13),
                 bg="#12121f", fg="#ffffff", insertbackground="#00d26a",
                 relief="flat", justify="center", width=28)
    e.pack(padx=30, ipady=5)
    e.focus()

    sl = tk.Label(root, text="", font=("Microsoft YaHei", 9), fg="#ffc107", bg="#1a1a2e")
    sl.pack(pady=(5, 0))

    def do():
        k = ev.get().strip()
        if not k:
            sl.config(text="请输入序列号", fg="#ff4d6a"); return
        ok, msg = activate(k)
        sl.config(text=msg, fg="#00d26a" if ok else "#ff4d6a")
        if ok:
            result["key"] = k
            root.after(800, root.destroy)

    bf = tk.Frame(root, bg="#1a1a2e"); bf.pack(pady=15)
    tk.Button(bf, text=" 激 活 ", font=("Microsoft YaHei", 11, "bold"),
              bg="#00a86b", fg="white", relief="flat", padx=30, pady=8,
              cursor="hand2", command=do).pack(side="left", padx=5)
    tk.Button(bf, text=" 退 出 ", font=("Microsoft YaHei", 11),
              bg="#495057", fg="white", relief="flat", padx=30, pady=8,
              cursor="hand2", command=root.destroy).pack(side="left", padx=5)

    root.bind("<Return>", lambda e: do())
    root.mainloop()
    return result["key"]


if __name__ == "__main__":
    print("机器码:", get_hwid())
    k = generate_key("2026-12-31")
    print("测试密钥:", k)
    v, e = validate_key(k)
    print("验证:", v, e)
