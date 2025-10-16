import sys
import subprocess
import cv2
import numpy as np
import mss
import pyautogui
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLabel
)
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen


# ===================== 主控制面板 =====================
class ADBController(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('ADB 控制面板')
        self.setGeometry(100, 100, 400, 600)

        layout = QVBoxLayout()

        # 常規按鈕
        btn_back = QPushButton('返回', self)
        btn_back.clicked.connect(self.adb_back)
        layout.addWidget(btn_back)

        btn_home = QPushButton('主畫面', self)
        btn_home.clicked.connect(self.adb_home)
        layout.addWidget(btn_home)

        btn_screenshot = QPushButton('截圖', self)
        btn_screenshot.clicked.connect(self.adb_screenshot)
        layout.addWidget(btn_screenshot)

        btn_airplane_on = QPushButton('開啟飛航模式', self)
        btn_airplane_on.clicked.connect(self.adb_airplane_mode_on)
        layout.addWidget(btn_airplane_on)
        
        btn_airplane_off = QPushButton('關閉飛航模式', self)
        btn_airplane_off.clicked.connect(self.adb_airplane_mode_off)
        layout.addWidget(btn_airplane_off)

        btn_screen_stream = QPushButton('啟動螢幕串流', self)
        btn_screen_stream.clicked.connect(self.start_screen_stream)
        layout.addWidget(btn_screen_stream)

        # 新增即時取色按鈕
        btn_live_color = QPushButton('即時取色 (scrcpy 畫面)', self)
        btn_live_color.clicked.connect(self.open_live_color_picker)
        layout.addWidget(btn_live_color)

        self.color_label = QLabel("RGB: (---, ---, ---)")
        self.color_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.color_label)

        self.setLayout(layout)

    # -------------------- ADB 指令 --------------------
    def adb_command(self, command):
        try:
            result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output = result.stdout.decode('utf-8')
            print(output)
        except Exception as e:
            print(f'執行錯誤: {e}')

    def adb_back(self):
        self.adb_command('adb shell input keyevent KEYCODE_BACK')

    def adb_home(self):
        self.adb_command('adb shell input keyevent KEYCODE_HOME')

    def adb_screenshot(self):
        self.adb_command('adb shell screencap -p /sdcard/screenshot.png')
        self.adb_command('adb pull /sdcard/screenshot.png')
        print('截圖已保存到當前目錄')

    def adb_airplane_mode_on(self):
        self.adb_command('adb shell settings put global airplane_mode_on 1')
        self.adb_command('adb shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true')
        print('飛航模式已開啟')

    def adb_airplane_mode_off(self):
        self.adb_command('adb shell settings put global airplane_mode_on 0')
        self.adb_command('adb shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false')
        print('飛航模式已關閉')

    def start_screen_stream(self):
        try:
            subprocess.Popen('scrcpy', shell=True)
            print('啟動螢幕串流')
        except Exception as e:
            print(f'啟動失敗: {e}')

    # -------------------- 新增功能 --------------------
    def open_live_color_picker(self):
        self.color_picker = LiveColorPicker(self.color_label)
        self.color_picker.show()


# ===================== 即時取色視窗 =====================
class LiveColorPicker(QWidget):
    def __init__(self, color_label):
        super().__init__()
        self.setWindowTitle('即時取色（scrcpy 畫面）')
        self.setGeometry(600, 200, 400, 200)

        self.color_label = color_label
        layout = QVBoxLayout()

        self.info_label = QLabel("請將滑鼠移到 scrcpy 視窗上以取色")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        self.setLayout(layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_color)
        self.timer.start(50)  # 每 50ms 更新一次 (約 20fps)

    def update_color(self):
        try:
            # 取得滑鼠位置
            x, y = pyautogui.position()

            # 擷取滑鼠所在像素
            with mss.mss() as sct:
                monitor = {"top": y, "left": x, "width": 1, "height": 1}
                img = np.array(sct.grab(monitor))
                r, g, b = img[0, 0, :3]

            self.color_label.setText(f"RGB: ({r}, {g}, {b})")
            self.info_label.setText(f"滑鼠位置 ({x}, {y}) → RGB: ({r}, {g}, {b})")
        except Exception as e:
            self.info_label.setText(f"取色失敗: {e}")


# ===================== 主程式入口 =====================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ADBController()
    ex.show()
    sys.exit(app.exec_())
