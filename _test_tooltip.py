import sys
sys.path.insert(0, r"C:\Users\82682\.workbuddy\binaries\python\envs\default\Lib\site-packages")
from PySide6.QtWidgets import QApplication, QPushButton, QToolTip, QMainWindow, QLabel, QVBoxLayout, QWidget
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtCore import Qt

app = QApplication(sys.argv)
app.setStyle("Fusion")

# 方法1: QFont
font = QFont("Microsoft YaHei", 10)  # 先测试10看看效果
QToolTip.setFont(font)

# 方法2: 用stylesheet强行覆盖(比其他QSS优先级高)
app.setStyleSheet("QToolTip { font-size: 10px; background: #1a1a2e; color: #b0b0c0; padding: 2px 4px; border: 1px solid #333; }")

# 方法3: palette
p = app.palette()
p.setColor(QPalette.ToolTipBase, QColor("#1a1a2e"))
p.setColor(QPalette.ToolTipText, QColor("#b0b0c0"))
app.setPalette(p)

class TestWin(QMainWindow):
    def __init__(self):
        super().__init__()
        w = QWidget()
        l = QVBoxLayout(w)
        btn = QPushButton("悬停看我")
        btn.setToolTip("第一行测试文字很长很长\n第二行Bid(卖出价): 你做多平仓的价格\n第三行Ask(买入价): 你做多开仓的价格\n点差=Ask-Bid, 越小成本越低")
        l.addWidget(btn)
        self.setCentralWidget(w)
        self.resize(300, 200)

win = TestWin()
win.show()
print("QToolTip.font():", QToolTip.font().family(), QToolTip.font().pointSize())
app.exec()
