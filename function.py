import sys
import subprocess
import cv2
import numpy as np
import mss
import pyautogui
import threading
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QFileDialog, QSpinBox, QGroupBox, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor


# ===================== 影片播放器 =====================
class VideoSegmentPlayer:
    def __init__(self, video_path, num_segments=10):
        self.video_path = video_path
        self.num_segments = num_segments
        self.cap = cv2.VideoCapture(video_path)
        
        if not self.cap.isOpened():
            raise ValueError("無法開啟影片檔案")
        
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frames_per_segment = self.total_frames // num_segments
        
        self.current_segment = 1
        self.playing = False
        self.jump_to_segment = None
        self.window_name = 'Color Controlled Video Player'
        
        print(f"影片載入: 總幀數 {self.total_frames}, FPS {self.fps}")
        print(f"片段數: {self.num_segments}, 每段 {self.frames_per_segment} 幀")
    
    def jump_to(self, segment_num):
        if segment_num < 1 or segment_num > self.num_segments:
            return False
        start_frame = (segment_num - 1) * self.frames_per_segment
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        self.current_segment = segment_num
        print(f">>> 跳轉到第 {segment_num} 段")
        return True
    
    def start_playing(self):
        if self.playing:
            return
        self.playing = True
        self.play_thread = threading.Thread(target=self.play_loop, daemon=True)
        self.play_thread.start()
    
    def stop_playing(self):
        self.playing = False
    
    def play_loop(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        
        while self.playing:
            if self.jump_to_segment is not None:
                self.jump_to(self.jump_to_segment)
                self.jump_to_segment = None
            
            ret, frame = self.cap.read()
            
            if not ret:
                self.jump_to(1)
                continue
            
            current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            current_seg = min((current_frame // self.frames_per_segment) + 1, self.num_segments)
            
            text = f"Segment: {current_seg}/{self.num_segments} | Frame: {current_frame}/{self.total_frames}"
            cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       1, (0, 255, 0), 2, cv2.LINE_AA)
            
            cv2.imshow(self.window_name, frame)
            
            key = cv2.waitKey(int(1000/self.fps)) & 0xFF
            if key == 27:
                self.playing = False
                break
        
        cv2.destroyWindow(self.window_name)
    
    def cleanup(self):
        self.playing = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()


# ===================== 主控制面板 =====================
class ADBController(QWidget):
    def __init__(self):
        super().__init__()
        self.video_player = None
        self.segment_colors = []  # [(r, g, b, tolerance), ...]
        self.color_detection_active = False
        self.initUI()

    def initUI(self):
        self.setWindowTitle('ADB 控制面板 + 顏色影片控制')
        self.setGeometry(100, 100, 600, 700)

        main_layout = QVBoxLayout()

        # ==================== ADB 控制區 ====================
        adb_group = QGroupBox("ADB 控制")
        adb_layout = QHBoxLayout()

        btn_back = QPushButton('返回', self)
        btn_back.clicked.connect(self.adb_back)
        adb_layout.addWidget(btn_back)

        btn_home = QPushButton('主畫面', self)
        btn_home.clicked.connect(self.adb_home)
        adb_layout.addWidget(btn_home)

        btn_screenshot = QPushButton('截圖', self)
        btn_screenshot.clicked.connect(self.adb_screenshot)
        adb_layout.addWidget(btn_screenshot)

        btn_screen_stream = QPushButton('啟動 scrcpy', self)
        btn_screen_stream.clicked.connect(self.start_screen_stream)
        adb_layout.addWidget(btn_screen_stream)

        adb_group.setLayout(adb_layout)
        main_layout.addWidget(adb_group)

        # ==================== 即時取色顯示 ====================
        color_display_group = QGroupBox("即時取色")
        color_display_layout = QVBoxLayout()
        
        self.color_label = QLabel("滑鼠位置顏色: RGB(---, ---, ---)")
        self.color_label.setAlignment(Qt.AlignCenter)
        self.color_label.setStyleSheet("font-size: 16px; padding: 10px; background-color: #f0f0f0;")
        color_display_layout.addWidget(self.color_label)
        
        color_display_group.setLayout(color_display_layout)
        main_layout.addWidget(color_display_group)

        # 啟動即時取色 Timer
        self.color_timer = QTimer()
        self.color_timer.timeout.connect(self.update_mouse_color)
        self.color_timer.start(50)  # 每 50ms 更新

        # ==================== 影片設定區 ====================
        video_group = QGroupBox("影片設定")
        video_layout = QVBoxLayout()

        # 載入影片
        btn_load_video = QPushButton('📁 載入影片', self)
        btn_load_video.clicked.connect(self.load_video)
        video_layout.addWidget(btn_load_video)

        self.video_info_label = QLabel("尚未載入影片")
        video_layout.addWidget(self.video_info_label)

        # 片段數量設定
        segment_layout = QHBoxLayout()
        segment_layout.addWidget(QLabel("切分片段數:"))
        self.segment_spinbox = QSpinBox()
        self.segment_spinbox.setMinimum(2)
        self.segment_spinbox.setMaximum(20)
        self.segment_spinbox.setValue(3)
        self.segment_spinbox.valueChanged.connect(self.update_segment_inputs)
        segment_layout.addWidget(self.segment_spinbox)
        video_layout.addLayout(segment_layout)

        video_group.setLayout(video_layout)
        main_layout.addWidget(video_group)

        # ==================== 片段顏色設定區 ====================
        self.segment_color_group = QGroupBox("片段顏色設定")
        self.segment_color_layout = QVBoxLayout()
        
        # 使用 ScrollArea 以防片段太多
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.segment_inputs_layout = QVBoxLayout(scroll_content)
        scroll.setWidget(scroll_content)
        self.segment_color_layout.addWidget(scroll)
        
        self.segment_color_group.setLayout(self.segment_color_layout)
        main_layout.addWidget(self.segment_color_group)
        
        # 初始化片段輸入欄位
        self.segment_input_widgets = []
        self.update_segment_inputs()

        # ==================== 控制按鈕 ====================
        control_layout = QHBoxLayout()
        
        self.btn_start_video = QPushButton('▶ 開始播放')
        self.btn_start_video.clicked.connect(self.start_video)
        self.btn_start_video.setEnabled(False)
        control_layout.addWidget(self.btn_start_video)

        self.btn_start_detection = QPushButton('🎯 開始顏色偵測')
        self.btn_start_detection.clicked.connect(self.start_color_detection)
        self.btn_start_detection.setEnabled(False)
        control_layout.addWidget(self.btn_start_detection)

        self.btn_stop = QPushButton('⏹ 全部停止')
        self.btn_stop.clicked.connect(self.stop_all)
        control_layout.addWidget(self.btn_stop)

        main_layout.addLayout(control_layout)

        self.status_label = QLabel("狀態: 待機中")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

    # ==================== 即時取色 ====================
    def update_mouse_color(self):
        try:
            x, y = pyautogui.position()
            with mss.mss() as sct:
                monitor = {"top": y, "left": x, "width": 1, "height": 1}
                img = np.array(sct.grab(monitor))
                r, g, b = img[0, 0, :3]
            
            self.color_label.setText(f"滑鼠位置 ({x}, {y}) 顏色: RGB({r}, {g}, {b})")
            self.color_label.setStyleSheet(
                f"font-size: 16px; padding: 10px; background-color: rgb({r},{g},{b}); "
                f"color: {'white' if (r+g+b) < 382 else 'black'};"
            )
        except Exception as e:
            pass

    # ==================== 片段顏色設定 ====================
    def update_segment_inputs(self):
        # 清除舊的輸入欄位
        for widget_group in self.segment_input_widgets:
            for widget in widget_group:
                widget.deleteLater()
        self.segment_input_widgets.clear()
        
        num_segments = self.segment_spinbox.value()
        
        # 為每個片段創建顏色輸入欄位
        for i in range(num_segments):
            segment_layout = QHBoxLayout()
            
            label = QLabel(f"片段 {i+1}:")
            segment_layout.addWidget(label)
            
            # 複製按鈕（使用當前滑鼠顏色）
            btn_copy = QPushButton('📋 複製當前顏色')
            btn_copy.clicked.connect(lambda checked, idx=i: self.copy_current_color(idx))
            segment_layout.addWidget(btn_copy)
            
            segment_layout.addWidget(QLabel("R:"))
            r_input = QSpinBox()
            r_input.setMaximum(255)
            r_input.setValue(0)
            segment_layout.addWidget(r_input)
            
            segment_layout.addWidget(QLabel("G:"))
            g_input = QSpinBox()
            g_input.setMaximum(255)
            g_input.setValue(0)
            segment_layout.addWidget(g_input)
            
            segment_layout.addWidget(QLabel("B:"))
            b_input = QSpinBox()
            b_input.setMaximum(255)
            b_input.setValue(0)
            segment_layout.addWidget(b_input)
            
            segment_layout.addWidget(QLabel("容差:"))
            tolerance_input = QSpinBox()
            tolerance_input.setMaximum(100)
            tolerance_input.setValue(30)
            segment_layout.addWidget(tolerance_input)
            
            self.segment_inputs_layout.addLayout(segment_layout)
            self.segment_input_widgets.append([label, btn_copy, r_input, g_input, b_input, tolerance_input])

    def copy_current_color(self, segment_index):
        """按下後，等待使用者點擊螢幕任一位置，然後自動擷取該點顏色"""
        import pyautogui
        from pynput import mouse

        self.status_label.setText(f"狀態: 🖱 請點擊螢幕任一位置以擷取顏色...")

        def on_click(x, y, button, pressed):
            if pressed:
                try:
                    with mss.mss() as sct:
                        monitor = {"top": int(y), "left": int(x), "width": 1, "height": 1}
                        img = np.array(sct.grab(monitor))
                        r, g, b = img[0, 0, :3]

                    widgets = self.segment_input_widgets[segment_index]
                    widgets[2].setValue(r)
                    widgets[3].setValue(g)
                    widgets[4].setValue(b)

                    print(f"片段 {segment_index+1} 擷取顏色: RGB({r},{g},{b})")
                    self.status_label.setText(
                        f"狀態: ✅ 片段 {segment_index+1} 擷取成功 RGB({r},{g},{b})"
                    )

                except Exception as e:
                    print(f"擷取顏色失敗: {e}")
                finally:
                    listener.stop()

        listener = mouse.Listener(on_click=on_click)
        listener.start()


    # ==================== ADB 指令 ====================
    def adb_command(self, command):
        try:
            subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f'執行錯誤: {e}')

    def adb_back(self):
        self.adb_command('adb shell input keyevent KEYCODE_BACK')

    def adb_home(self):
        self.adb_command('adb shell input keyevent KEYCODE_HOME')

    def adb_screenshot(self):
        self.adb_command('adb shell screencap -p /sdcard/screenshot.png')
        self.adb_command('adb pull /sdcard/screenshot.png')

    def start_screen_stream(self):
        try:
            subprocess.Popen('scrcpy', shell=True)
        except Exception as e:
            print(f'啟動失敗: {e}')

    # ==================== 影片控制 ====================
    def load_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "選擇影片", "", "Video Files (*.mp4 *.avi *.mkv *.mov)"
        )
        if file_path:
            try:
                num_segments = self.segment_spinbox.value()
                self.video_player = VideoSegmentPlayer(file_path, num_segments)
                self.video_info_label.setText(
                    f"✅ 已載入 | 片段數: {num_segments} | FPS: {self.video_player.fps:.1f}"
                )
                self.btn_start_video.setEnabled(True)
                self.btn_start_detection.setEnabled(True)
            except Exception as e:
                self.video_info_label.setText(f"❌ 載入失敗: {e}")

    def start_video(self):
        if self.video_player:
            self.video_player.start_playing()
            self.status_label.setText("狀態: ▶ 影片播放中")

    def start_color_detection(self):
        if not self.video_player:
            print("請先載入影片")
            return
        
        # 讀取所有片段的顏色設定
        self.segment_colors.clear()
        for widgets in self.segment_input_widgets:
            r = widgets[2].value()
            g = widgets[3].value()
            b = widgets[4].value()
            tolerance = widgets[5].value()
            self.segment_colors.append((r, g, b, tolerance))
        
        print(f"已載入 {len(self.segment_colors)} 個片段顏色設定")
        
        self.color_detection_active = True
        self.status_label.setText("狀態: 🎯 顏色偵測中...")
        
        self.detection_timer = QTimer()
        self.detection_timer.timeout.connect(self.check_color_and_control)
        self.detection_timer.start(100)

    def check_color_and_control(self):
        try:
            x, y = pyautogui.position()
            with mss.mss() as sct:
                monitor = {"top": y, "left": x, "width": 1, "height": 1}
                img = np.array(sct.grab(monitor))
                current_r, current_g, current_b = img[0, 0, :3]

            # 檢查每個片段的顏色
            for segment_num, (r, g, b, tolerance) in enumerate(self.segment_colors, start=1):
                if self.is_color_match(current_r, current_g, current_b, r, g, b, tolerance):
                    if self.video_player and self.video_player.playing:
                        if self.video_player.current_segment != segment_num:
                            self.video_player.jump_to_segment = segment_num
                            self.status_label.setText(
                                f"狀態: 🎯 匹配片段 {segment_num} RGB({r},{g},{b})"
                            )
                    break

        except Exception as e:
            pass

    def is_color_match(self, r1, g1, b1, r2, g2, b2, tolerance):
        return (abs(r1 - r2) <= tolerance and 
                abs(g1 - g2) <= tolerance and 
                abs(b1 - b2) <= tolerance)

    def stop_all(self):
        if self.video_player:
            self.video_player.stop_playing()
        
        self.color_detection_active = False
        if hasattr(self, 'detection_timer'):
            self.detection_timer.stop()
        
        self.status_label.setText("狀態: ⏹ 已停止")

    def closeEvent(self, event):
        self.color_timer.stop()
        if hasattr(self, 'detection_timer'):
            self.detection_timer.stop()
        if self.video_player:
            self.video_player.cleanup()
        event.accept()


# ===================== 主程式入口 =====================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ADBController()
    ex.show()
    sys.exit(app.exec_())