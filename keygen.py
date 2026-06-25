"""
BTC 交易面板 — 序列号生成器 (仅供开发者)
=========================================
python keygen.py [到期日期] [类型]

示例:
  python keygen.py                  → 永久授权
  python keygen.py 2026-12-31       → 指定到期
  python keygen.py 2026-07-01 trial → 试用授权
"""

import sys
from license import generate_key, validate_key, get_hwid

if __name__ == "__main__":
    expiry = sys.argv[1] if len(sys.argv) > 1 else "2099-12-31"
    utype = sys.argv[2] if len(sys.argv) > 2 else "full"

    if utype not in ("full", "trial"):
        print("类型: full 或 trial")
        sys.exit(1)

    key = generate_key(expiry, utype)
    hwid = get_hwid()

    print(f"到期:  {expiry}")
    print(f"类型:  {utype}")
    print(f"密钥:  {key}")
    print(f"本机码: {hwid}")

    v, e = validate_key(key)
    print(f"自检:  {'OK' if v else 'FAIL: ' + e}")
