# BTC 交易系统 - Git 备份说明

## 每次修改前自动备份

本项目已启用 Git 版本管理。

### 手动备份命令（改代码前必执行）
```bash
cd D:/BTC
git add -A
git commit -m "backup before edit: <说明>"
```

### 查看历史版本
```bash
git log --oneline
git show <commit号>:btc_panel.py   # 查看某版本的文件
```

### 回滚到某个版本
```bash
git checkout <commit号> -- btc_panel.py   # 只恢复某个文件
git reset --hard <commit号>               # 全部回滚
```

### 自动化备份（推荐）
运行 `python auto_backup.py` 会自动提交所有改动。
