@echo off
echo 启动BTC AI交易面板...
cd /d D:\BTC

REM 设置环境变量避免MT5阻塞
set SKIP_MT5_INIT=1
set PYTHONIOENCODING=utf-8

REM 使用后台启动
start "BTC交易面板" "C:\Users\82682\.workbuddy\binaries\python\versions\3.13.12\python.exe" -c "
import sys, os, threading, time
os.chdir('D:/BTC')
sys.path.insert(0, 'D:/BTC')

print('BTC AI交易面板启动中...')

# 快速UI测试
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton, QTextEdit
from PySide6.QtCore import Qt, QTimer

app = QApplication(sys.argv)

class QuickPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('BTC AI交易面板 - 快速启动')
        self.setGeometry(100, 100, 900, 700)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        title = QLabel('🚀 BTC AI自动交易系统')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet('font-size: 24px; font-weight: bold; color: #00a86b; margin: 20px;')
        layout.addWidget(title)
        
        status = QLabel('✅ 系统已启动 - 快速模式')
        status.setStyleSheet('color: #4CAF50; font-size: 16px; padding: 10px; background: #1a1a2e; border-radius: 5px;')
        layout.addWidget(status)
        
        btn_frame = QWidget()
        btn_layout = QVBoxLayout(btn_frame)
        
        btn_start = QPushButton('▶ 启动完整版面板')
        btn_start.setMinimumHeight(40)
        btn_start.clicked.connect(self.start_full_panel)
        
        btn_test = QPushButton('🔧 测试MT5连接')
        btn_test.setMinimumHeight(40)
        btn_test.clicked.connect(self.test_mt5)
        
        btn_exit = QPushButton('❌ 退出')
        btn_exit.setMinimumHeight(40)
        btn_exit.clicked.connect(self.close)
        
        btn_layout.addWidget(btn_start)
        btn_layout.addWidget(btn_test)
        btn_layout.addWidget(btn_exit)
        layout.addWidget(btn_frame)
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(200)
        self.log_area.setStyleSheet('background: #1a1a2e; color: #e0e0e0; font-family: Consolas;')
        layout.addWidget(self.log_area)
        
        self.log('快速启动面板已就绪')
        self.log('原始面板启动问题可能是MT5连接超时')
        self.log('点击上方按钮进行测试')
    
    def log(self, msg):
        import datetime
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        self.log_area.append(f'[{ts}] {msg}')
    
    def start_full_panel(self):
        self.log('启动完整面板...')
        threading.Thread(target=self._launch_full_panel, daemon=True).start()
    
    def _launch_full_panel(self):
        try:
            import btc_panel_qt
            self.log('完整面板模块导入成功')
        except Exception as e:
            self.log(f'导入失败: {e}')
    
    def test_mt5(self):
        self.log('测试MT5连接...')
        threading.Thread(target=self._test_mt5_connection, daemon=True).start()
    
    def _test_mt5_connection(self):
        try:
            import MetaTrader5 as mt5
            self.log('MT5模块导入成功')
            import os
            mt5_path = 'C:/Program Files/MetaTrader 5/terminal64.exe'
            if os.path.exists(mt5_path):
                self.log(f'MT5路径存在: {mt5_path}')
                if mt5.initialize(path=mt5_path):
                    self.log('✅ MT5连接成功')
                    mt5.shutdown()
                else:
                    self.log('❌ MT5连接失败')
            else:
                self.log(f'❌ MT5路径不存在: {mt5_path}')
        except Exception as e:
            self.log(f'MT5测试异常: {e}')

window = QuickPanel()
window.show()

# 定时器保持运行
timer = QTimer()
timer.timeout.connect(lambda: None)
timer.start(1000)

sys.exit(app.exec())
"

echo 面板启动命令已发送
echo 如果窗口未显示，请检查Python环境
pause