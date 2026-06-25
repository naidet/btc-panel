"""
序列号生成器 GUI v2 — 机器码查询 + 密钥历史管理
双击桌面 序列号生成器.bat 运行
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import sys, os, json, sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from license import generate_key, validate_key, get_hwid

BG = "#1a1a2e"
CARD = "#252540"
GREEN = "#00d26a"
RED = "#ff4d6a"
BLUE = "#4dabf7"
GRAY = "#7a7a9e"
TEXT = "#e0e0e0"
YELLOW = "#ffc107"
WHITE = "#ffffff"
DARK = "#12121f"

# 密钥历史数据库
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key_history.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            customer TEXT DEFAULT '',
            machine_code TEXT DEFAULT '',
            key TEXT NOT NULL,
            expiry TEXT NOT NULL,
            key_type TEXT DEFAULT 'full',
            notes TEXT DEFAULT ''
        )
    """)
    conn.commit()
    return conn

class KeygenApp:
    def __init__(self):
        init_db()
        self.root = tk.Tk()
        self.root.title("BTC 交易面板 — 序列号生成器 v2")
        self.root.geometry("650x720")
        self.root.minsize(550, 600)
        self.root.configure(bg=BG)
        
        # 标题
        hdr = tk.Frame(self.root, bg=CARD, padx=15, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔑 序列号生成器  v2", font=("Microsoft YaHei", 14, "bold"),
                 fg=BLUE, bg=CARD).pack(side="left")
        tk.Button(hdr, text="查询历史", font=("Microsoft YaHei", 9),
                  bg=BLUE, fg="white", relief="flat", padx=12, pady=4,
                  cursor="hand2", command=self.show_history).pack(side="right")
        
        # === 输入区 ===
        card = tk.Frame(self.root, bg=CARD, padx=12, pady=10)
        card.pack(fill="x", padx=12, pady=(8, 4))
        
        # 本机机器码
        self.hwid = get_hwid()
        fhw = tk.Frame(card, bg=CARD)
        fhw.pack(fill="x", pady=(0, 8))
        tk.Label(fhw, text="本机机器码:", font=("Microsoft YaHei", 9),
                 fg=GRAY, bg=CARD).pack(side="left")
        self.hwid_label = tk.Label(fhw, text=self.hwid, font=("Consolas", 12, "bold"),
                                    fg=GREEN, bg=CARD)
        self.hwid_label.pack(side="left", padx=8)
        tk.Button(fhw, text="复制", font=("Microsoft YaHei", 8),
                  bg="#3a3a5c", fg=GRAY, relief="flat", padx=8,
                  cursor="hand2", command=lambda: self.copy_text(self.hwid)).pack(side="left")
        
        # 客户机器码 (可选, 生成给别人的密钥时填)
        f1 = tk.Frame(card, bg=CARD)
        f1.pack(fill="x", pady=2)
        tk.Label(f1, text="客户机器码:", font=("Microsoft YaHei", 9),
                 fg=GRAY, bg=CARD, width=10, anchor="w").pack(side="left")
        self.machine_var = tk.StringVar()
        tk.Entry(f1, textvariable=self.machine_var, font=("Consolas", 11), width=18,
                 bg=DARK, fg="white", insertbackground=GREEN,
                 relief="flat", justify="center").pack(side="left", padx=(5, 10))
        tk.Label(f1, text="(可选, 仅记录)", font=("Microsoft YaHei", 8),
                 fg=GRAY, bg=CARD).pack(side="left")
        
        # 客户名称
        f2 = tk.Frame(card, bg=CARD)
        f2.pack(fill="x", pady=2)
        tk.Label(f2, text="客户名称:", font=("Microsoft YaHei", 9),
                 fg=GRAY, bg=CARD, width=10, anchor="w").pack(side="left")
        self.customer_var = tk.StringVar()
        tk.Entry(f2, textvariable=self.customer_var, font=("Microsoft YaHei", 11), width=18,
                 bg=DARK, fg="white", insertbackground=GREEN,
                 relief="flat").pack(side="left", padx=(5, 10))
        tk.Label(f2, text="(可选)", font=("Microsoft YaHei", 8),
                 fg=GRAY, bg=CARD).pack(side="left")
        
        # 备注
        f3 = tk.Frame(card, bg=CARD)
        f3.pack(fill="x", pady=2)
        tk.Label(f3, text="备注:", font=("Microsoft YaHei", 9),
                 fg=GRAY, bg=CARD, width=10, anchor="w").pack(side="left")
        self.notes_var = tk.StringVar()
        tk.Entry(f3, textvariable=self.notes_var, font=("Microsoft YaHei", 10), width=40,
                 bg=DARK, fg="white", insertbackground=GREEN,
                 relief="flat").pack(side="left", padx=5)
        
        # 到期日期 + 类型 + 快捷
        f4 = tk.Frame(card, bg=CARD)
        f4.pack(fill="x", pady=(8, 2))
        tk.Label(f4, text="到期日期:", font=("Microsoft YaHei", 9),
                 fg=GRAY, bg=CARD).pack(side="left")
        self.date_var = tk.StringVar(value=(datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"))
        tk.Entry(f4, textvariable=self.date_var, font=("Consolas", 11), width=12,
                 bg=DARK, fg="white", insertbackground=GREEN,
                 relief="flat", justify="center").pack(side="left", padx=5)
        
        tk.Label(f4, text="类型:", font=("Microsoft YaHei", 9),
                 fg=GRAY, bg=CARD).pack(side="left", padx=(10, 2))
        self.type_var = tk.StringVar(value="正式版")
        s = ttk.Style()
        s.configure("TCombobox", fieldbackground=DARK, background=CARD, foreground="white")
        cb = ttk.Combobox(f4, textvariable=self.type_var, values=["正式版", "试用版"],
                          state="readonly", width=8, font=("Microsoft YaHei", 10))
        cb.pack(side="left", padx=3)
        
        quick = tk.Frame(card, bg=CARD)
        quick.pack(pady=5)
        for label, days in [("周", 7), ("30天", 30), ("90天", 90), ("1年", 365), ("永久", 99999)]:
            d = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            if days == 99999: d = "2099-12-31"
            tk.Button(quick, text=label, font=("Microsoft YaHei", 8),
                      bg="#3a3a5c", fg=GRAY, relief="flat", padx=10, pady=2,
                      command=lambda x=d: self.date_var.set(x)).pack(side="left", padx=2)
        
        # 生成按钮
        bf = tk.Frame(self.root, bg=BG)
        bf.pack(pady=8)
        tk.Button(bf, text=" 生成序列号 ", font=("Microsoft YaHei", 12, "bold"),
                  bg="#00a86b", fg="white", relief="flat", padx=25, pady=8,
                  cursor="hand2", command=self.generate).pack()
        
        # 结果卡片
        self.result_card = tk.Frame(self.root, bg=CARD, padx=15, pady=10)
        self.result_key = tk.Label(self.result_card, text="",
                                    font=("Consolas", 14, "bold"), fg=GREEN, bg=CARD)
        self.result_key.pack()
        self.result_info = tk.Label(self.result_card, text="",
                                     font=("Microsoft YaHei", 9), fg=GRAY, bg=CARD)
        self.result_info.pack(pady=(2, 0))
        
        # 状态
        self.status = tk.Label(self.root, text="就绪", font=("Microsoft YaHei", 9),
                               fg=GRAY, bg=BG)
        self.status.pack(pady=3)
        
        # === 最近密钥列表 ===
        list_card = tk.Frame(self.root, bg=CARD, padx=10, pady=8)
        list_card.pack(fill="both", expand=True, padx=12, pady=(5, 10))
        
        list_hdr = tk.Frame(list_card, bg=CARD)
        list_hdr.pack(fill="x")
        tk.Label(list_hdr, text="📋 最近密钥", font=("Microsoft YaHei", 10, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        tk.Button(list_hdr, text="导出CSV", font=("Microsoft YaHei", 8),
                  bg="#3a3a5c", fg=GRAY, relief="flat", padx=10, pady=2,
                  cursor="hand2", command=self.export_csv).pack(side="right")
        
        self.tree_frame = tk.Frame(list_card, bg=CARD)
        self.tree_frame.pack(fill="both", expand=True, pady=(4, 0))
        self._build_tree()
        
        self.load_recent()
        self.root.mainloop()
    
    def _build_tree(self):
        cols = ("key", "expiry", "customer", "machine", "date", "type")
        self.tree = ttk.Treeview(self.tree_frame, columns=cols, show="headings", height=8)
        self.tree.heading("key", text="序列号", anchor="w")
        self.tree.heading("expiry", text="到期", anchor="w")
        self.tree.heading("customer", text="客户", anchor="w")
        self.tree.heading("machine", text="机器码", anchor="w")
        self.tree.heading("date", text="生成日期", anchor="w")
        self.tree.heading("type", text="类型", anchor="w")
        
        self.tree.column("key", width=180, minwidth=100)
        self.tree.column("expiry", width=80, minwidth=60)
        self.tree.column("customer", width=100, minwidth=60)
        self.tree.column("machine", width=100, minwidth=60)
        self.tree.column("date", width=80, minwidth=60)
        self.tree.column("type", width=50, minwidth=40)
        
        sb = tk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        # 右键菜单
        self.tree_menu = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT)
        self.tree_menu.add_command(label="复制序列号", command=self._copy_selected_key)
        self.tree_menu.add_command(label="展开查看详情", command=self._show_key_detail)
        self.tree.bind("<Button-3>", lambda e: self.tree_menu.post(e.x_root, e.y_root))
        
        # 颜色标记即将过期的
        self.tree.tag_configure("expired", foreground="#ff4d6a")
        self.tree.tag_configure("soon", foreground="#ffc107")
        self.tree.tag_configure("active", foreground="#00d26a")
    
    def copy_text(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.config(text="已复制到剪贴板", fg=GREEN)
    
    def generate(self):
        date_str = self.date_var.get().strip()
        utype_cn = self.type_var.get()
        utype = "full" if utype_cn == "正式版" else "trial"
        
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except:
            self.status.config(text="日期格式错误", fg=RED)
            return
        
        try:
            key = generate_key(date_str, utype)
            valid, msg = validate_key(key)
            
            # 显示结果
            self.result_card.pack(fill="x", padx=12, pady=(0, 4))
            self.result_key.config(text=key, fg=GREEN if valid else RED)
            self.result_info.config(
                text=f"到期: {date_str} | 类型: {utype_cn} | {'✓ 有效' if valid else '✗ ' + msg}")
            
            # 复制
            self.root.clipboard_clear()
            self.root.clipboard_append(key)
            
            # 保存到数据库
            customer = self.customer_var.get().strip()
            machine = self.machine_var.get().strip()
            notes = self.notes_var.get().strip()
            self._save_key(key, date_str, utype, customer, machine, notes)
            
            # 清空可选字段
            if customer: self.customer_var.set("")
            if machine: self.machine_var.set("")
            if notes: self.notes_var.set("")
            
            self.status.config(
                text=f"✓ 生成成功 (到期: {date_str}) | 已复制到剪贴板 | 已保存", fg=GREEN)
            
        except Exception as e:
            self.status.config(text=f"错误: {e}", fg=RED)
    
    def _save_key(self, key, expiry, ktype, customer, machine, notes):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO keys (created_at, customer, machine_code, key, expiry, key_type, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), customer, machine,
             key, expiry, ktype, notes)
        )
        conn.commit()
        conn.close()
        self.load_recent()
    
    def load_recent(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT key, expiry, customer, machine_code, created_at, key_type "
            "FROM keys ORDER BY id DESC LIMIT 50"
        ).fetchall()
        conn.close()
        
        now = datetime.now()
        for row in rows:
            key, expiry, customer, machine, created, ktype = row
            try:
                exp_dt = datetime.strptime(expiry, "%Y-%m-%d")
                days_left = (exp_dt - now).days
                if days_left < 0:
                    tag = "expired"
                elif days_left < 30:
                    tag = "soon"
                else:
                    tag = "active"
            except:
                tag = "active"
                days_left = "?"
            
            display_key = key[:20] + "..." if len(key) > 20 else key
            vals = (display_key, expiry, customer or "-",
                    machine[:15] + "..." if len(machine) > 15 else (machine or "-"),
                    created[:10], "正式版" if (ktype or "full") == "full" else "试用版")
            self.tree.insert("", "end", values=vals, tags=(tag,))
    
    def _copy_selected_key(self):
        sel = self.tree.selection()
        if sel:
            display = self.tree.item(sel[0], "values")[0]
            # 从数据库获取完整key
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT key FROM keys WHERE key LIKE ?", (display.replace("...", "") + "%",)).fetchone()
            conn.close()
            if row:
                self.copy_text(row[0])
    
    def _show_key_detail(self):
        sel = self.tree.selection()
        if sel:
            vals = self.tree.item(sel[0], "values")
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute(
                "SELECT key, expiry, customer, machine_code, created_at, key_type, notes "
                "FROM keys WHERE key LIKE ? LIMIT 1",
                (vals[0].replace("...", "") + "%",)
            ).fetchone()
            conn.close()
            if row:
                key, exp, cust, mach, created, kt, notes = row
                detail = (
                    f"序列号: {key}\n"
                    f"到期:   {exp}\n"
                    f"类型:   {'正式版' if kt == 'full' else '试用版'}\n"
                    f"客户:   {cust or '-'}\n"
                    f"机器码: {mach or '-'}\n"
                    f"生成:   {created}\n"
                    f"备注:   {notes or '-'}"
                )
                messagebox.showinfo("密钥详情", detail)
    
    def show_history(self):
        """搜索过滤"""
        win = tk.Toplevel(self.root)
        win.title("搜索密钥")
        win.geometry("400x150")
        win.configure(bg=BG)
        win.resizable(False, False)
        
        tk.Label(win, text="搜索客户名称或机器码:", font=("Microsoft YaHei", 10),
                 fg=TEXT, bg=BG).pack(pady=(15, 5))
        sv = tk.StringVar()
        e = tk.Entry(win, textvariable=sv, font=("Microsoft YaHei", 11), width=30,
                     bg=DARK, fg="white", insertbackground=GREEN, relief="flat")
        e.pack(pady=5)
        e.focus()
        
        def search():
            q = f"%{sv.get().strip()}%"
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT key, expiry, customer, machine_code, created_at, key_type "
                "FROM keys WHERE customer LIKE ? OR machine_code LIKE ? OR notes LIKE ? "
                "ORDER BY id DESC LIMIT 30",
                (q, q, q)
            ).fetchall()
            conn.close()
            msg = "\n".join(
                f"{r[0][:25]:<25} {r[1]} {r[2] or '-'}" for r in rows
            ) if rows else "无匹配结果"
            messagebox.showinfo("搜索", msg if len(msg) < 1000 else msg[:1000] + "...")
        
        tk.Button(win, text="搜索", font=("Microsoft YaHei", 10, "bold"),
                  bg=BLUE, fg="white", relief="flat", padx=25, pady=6,
                  cursor="hand2", command=search).pack(pady=10)
        win.bind("<Return>", lambda e: search())
    
    def export_csv(self):
        path = os.path.join(os.path.dirname(DB_PATH), f"keys_export_{datetime.now().strftime('%Y%m%d')}.csv")
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT created_at, customer, machine_code, key, expiry, key_type, notes FROM keys ORDER BY id"
        ).fetchall()
        conn.close()
        
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write("生成日期,客户,机器码,序列号,到期日期,类型,备注\n")
            for r in rows:
                f.write(",".join(f'"{c or ""}"' for c in r) + "\n")
        
        self.status.config(text=f"已导出: {path}", fg=GREEN)
        os.startfile(os.path.dirname(path))


if __name__ == "__main__":
    KeygenApp()
