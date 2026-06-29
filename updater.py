"""
BTC Panel — 远程更新模块
=====================
流程:
  1. 面板启动后异步请求 version.json
  2. 对比本地版本号
  3. 有新版 → 弹窗提示 → 下载安装包 → 运行安装程序 → 退出
"""

import json, os, sys, time, hashlib, threading
from urllib.request import urlopen, Request
from datetime import datetime

# ═══════════════════════════════════════════
# 配置 (部署时修改 UPDATE_URL)
# ═══════════════════════════════════════════
CURRENT_VERSION = "5.11"
VERSION_FILE = "panel_version.txt"  # 本地存储版本号
UPDATE_URL = "https://raw.githubusercontent.com/naidet/btc-panel/main/version.json"

# ═══════════════════════════════════
# 从 jsdelivr CDN 获取 version.json (带commit hash防缓存)
# ═══════════════════════════════════
UPDATE_URL_CDN = "https://cdn.jsdelivr.net/gh/naidet/btc-panel@main/version.json"

# ============================================================
# 版本检查
# ============================================================
def get_local_version() -> str:
    """读取本地版本号"""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE) as f:
                return f.read().strip()
    except:
        pass
    return CURRENT_VERSION


def check_update() -> dict:
    """
    检查远程更新
    返回: {"has_update": bool, "remote_version": str, "download_url": str, "notes": str, "error": str}
    """
    result = {"has_update": False, "remote_version": "", "download_url": "", "notes": "", "error": ""}
    try:
        # 先用 raw GitHub (带时间戳绕过缓存), CDN作为备份
        urls = [
            UPDATE_URL + f"?t={int(time.time())}",
            UPDATE_URL_CDN,
        ]
        data = None
        for url in urls:
            try:
                req = Request(url, headers={"User-Agent": "BTC-Panel-Updater/1.0"})
                resp = urlopen(req, timeout=8)
                data = json.loads(resp.read().decode())
                break
            except:
                continue
        
        if data is None:
            result["error"] = "无法连接更新服务器"
            return result
        remote_ver = data.get("version", "0")
        local_ver = get_local_version()
        result["remote_version"] = remote_ver

        if _compare_versions(remote_ver, local_ver) > 0:
            result["has_update"] = True
            result["remote_version"] = remote_ver
            result["download_url"] = data.get("url", "")
            result["notes"] = data.get("notes", "")
            result["size"] = data.get("size", 0)
    except Exception as e:
        result["error"] = str(e)[:100]
    return result


def _compare_versions(a: str, b: str) -> int:
    """比较版本号, a>b 返回1, a=b 返回0, a<b 返回-1"""
    try:
        pa = [int(x) for x in a.split(".")]
        pb = [int(x) for x in b.split(".")]
        for i in range(max(len(pa), len(pb))):
            va = pa[i] if i < len(pa) else 0
            vb = pb[i] if i < len(pb) else 0
            if va > vb: return 1
            if va < vb: return -1
        return 0
    except:
        return -1


# ============================================================
# 下载更新
# ============================================================
def download_update(url: str, version: str = "", progress_callback=None) -> str:
    """
    下载安装包到本地临时目录
    支持 .exe 和 .zip 格式 — zip自动解压后返回exe路径
    progress_callback(pct, downloaded, total)  # pct: 0-100
    返回本地文件路径, 失败返回空字符串
    """
    try:
        import tempfile, zipfile
        tmp_dir = tempfile.gettempdir()
        
        # 根据URL后缀决定保存路径
        is_zip = url.lower().endswith(".zip")
        ext = ".zip" if is_zip else ".exe"
        local_path = os.path.join(tmp_dir, f"BTC_Panel_Update_Setup{ext}")

        req = Request(url, headers={"User-Agent": "BTC-Panel-Updater/1.0"})
        resp = urlopen(req, timeout=300)
        total = int(resp.headers.get("Content-Length", 0))

        downloaded = 0
        chunk_size = 8192
        # 用已知 size 估算总量（GitHub 有的返回 0）
        if total <= 0 and hasattr(resp, "headers"):
            # 尝试从 Content-Range 头读取
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                try: total = int(content_range.split("/")[-1])
                except: pass
        with open(local_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    if total > 0:
                        pct = min(99, int(downloaded / total * 100))
                    else:
                        # 无 Content-Length 时用下载字节数显示进度
                        pct = min(99, int(downloaded / 1024 / 1024 / 1.5))  # 每1.5MB一跳
                    progress_callback(pct, downloaded, max(total, downloaded))

        if progress_callback:
            progress_callback(100, downloaded, total)

        # ZIP 自动解压
        if is_zip:
            extract_dir = os.path.join(tmp_dir, "BTC_Panel_Update")
            if os.path.exists(extract_dir):
                import shutil
                shutil.rmtree(extract_dir)
            with zipfile.ZipFile(local_path, "r") as zf:
                zf.extractall(extract_dir)
            # 找到 exe
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.lower().endswith(".exe") and "btc" in f.lower():
                        local_path = os.path.join(root, f)
                        break
                else:
                    continue
                break
            else:
                print("[UPDATER] ZIP中未找到EXE文件")
                return ""

        # 写入新版本号
        try:
            os.makedirs(os.path.dirname(VERSION_FILE) if os.path.dirname(VERSION_FILE) else ".", exist_ok=True)
            with open(VERSION_FILE, "w") as f:
                f.write(version if version else CURRENT_VERSION)
        except:
            pass

        return local_path
    except Exception as e:
        print(f"[UPDATER] 下载失败: {e}")
        return ""


# ============================================================
# 应用更新
# ============================================================
def apply_update(local_setup_path: str):
    """运行安装程序并退出当前面板"""
    try:
        os.startfile(local_setup_path)
        time.sleep(2)
        os._exit(0)
    except Exception as e:
        print(f"[UPDATER] 安装启动失败: {e}")
