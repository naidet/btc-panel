"""
BTC 交易面板 — 序列号生成器 (仅供开发者使用)
=============================================
用法:
  python keygen.py <机器码> [到期日期] [类型]
  
示例:
  python keygen.py A1B2-C3D4-E5F6                     → 永久授权
  python keygen.py A1B2-C3D4-E5F6 2026-12-31          → 指定到期
  python keygen.py A1B2-C3D4-E5F6 2026-06-30 trial    → 7天试用
"""

import sys
from license import generate_key, validate_key, get_hwid

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python keygen.py <机器码> [到期日期] [类型]")
        print()
        print("本机机器码:", get_hwid())
        sys.exit(1)
    
    hwid = sys.argv[1]
    expiry = sys.argv[2] if len(sys.argv) > 2 else "2099-12-31"
    utype = sys.argv[3] if len(sys.argv) > 3 else "full"
    
    if utype not in ("full", "trial"):
        print("类型必须是 full 或 trial")
        sys.exit(1)
    
    key = generate_key(hwid, expiry, utype)
    
    print(f"机器码:    {hwid}")
    print(f"到期日期:  {expiry}")
    print(f"类型:      {utype}")
    print(f"序列号:    {key}")
    print()
    
    # 自检
    valid, exp, err = validate_key(key)
    if valid:
        print("自检: ✓ 有效")
    else:
        print(f"自检: ✗ {err}")
