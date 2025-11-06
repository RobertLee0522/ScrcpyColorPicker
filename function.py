import sys
import subprocess
import cv2
import numpy as np
import mss
import pyautogui
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import List, Tuple, Optional
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QFileDialog, QSpinBox, QGroupBox, QScrollArea, QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QColor


# ===================== 資料類別 =====================
@dataclass
class ColorConfig:
    """顏色配置"""
    r: int
    g: int
    b: int
    tolerance: int


@dataclass
class SegmentConfig:
    """片段配置"""
    start_frame: int
    end_frame: int
    color: ColorConfig


# ===================== 顏色工具類 =====================
class ColorUtils:
    """顏色相關工具函數"""
    
    @staticmethod
    def get_screen_color(x: int, y: int) -> Optional[Tuple[int, int, int]]:
        """獲取螢幕指定位置的 RGB 顏色"""
        try:
            with mss.mss() as sct:
                monitor = {"top": int(y), "left": int(x), "width": 1, "height": 1}
                img = np.array(sct.grab(monitor))
                # mss 返回 BGRA 格式,需要轉換為 RGB
                b, g, r = img[0, 0, :3]
                return (int(r), int(g), int(b))
        except Exception as e:
            print(f"獲取顏色失敗: {e}")
            return None
    
    @staticmethod
    def is_color_match(color1: Tuple[int, int, int], 
                       color2: Tuple[int, int, int], 
                       tolerance: int) -> bool:
        """判斷兩個顏色是否匹配"""
        r1, g1, b1 = color1
        r2, g2, b2 = color2
        return (abs(r1 - r2) <= tolerance and 
                abs(g1 - g2) <= tolerance and 
                abs(b1 - b2) <= tolerance)
    
    @staticmethod
    def get_contrast_color(r: int, g: int, b: int) -> str:
        """根據背景色返回對比文字顏色"""
        return 'white' if (r + g + b) < 382 else 'black'


# ===================== 影片播放器 =====================
class VideoSegmentPlayer(QObject):
    """影片片段播放器"""
    
    segment_changed = pyqtSignal(int)  # 片段變更信號
    
    def __init__(self, video_path: str, segments: List[SegmentConfig]):
        super().__init__()
        self.video_path = video_path
        self.segments = segments
        self.cap = None
        self.total_frames = 0
        self.fps = 30
        self.current_segment = 1
        self.playing = False
        self.jump_to_segment = None
        self.window_name = 'Color Controlled Video Player'
        self.play_thread = None
        self._lock = threading.Lock()
        
        self._initialize_video()
    
    def _initialize_video(self):
        """初始化影片"""
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            
            if not self.cap.isOpened():
                raise ValueError(f"無法開啟影片檔案: {self.video_path}")
            
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            if self.fps <= 0:
                self.fps = 30
            
            print(f"影片載入成功: 總幀數 {self.total_frames}, FPS {self.fps}")
            print(f"片段設定: {len(self.segments)} 個片段")
            
        except Exception as e:
            print(f"影片初始化失敗: {e}")
            raise
    
    def jump_to(self, segment_num: int) -> bool:
        """跳轉到指定片段"""
        if segment_num < 1 or segment_num > len(self.segments):
            return False
        
        with self._lock:
            start_frame = self.segments[segment_num - 1].start_frame
            if self.cap:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            self.current_segment = segment_num
            self.segment_changed.emit(segment_num)
            print(f">>> 跳轉到第 {segment_num} 段 (幀 {start_frame})")
        
        return True
    
    def start_playing(self):
        """開始播放"""
        if self.playing:
            return
        
        self.playing = True
        self.play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self.play_thread.start()
    
    def stop_playing(self):
        """停止播放"""
        self.playing = False
        if self.play_thread:
            self.play_thread.join(timeout=2)
    
    def _play_loop(self):
        """播放循環"""
        try:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            frame_delay = max(1, int(1000 / self.fps))
            
            while self.playing and self.cap and self.cap.isOpened():
                # 處理跳轉請求
                if self.jump_to_segment is not None:
                    self.jump_to(self.jump_to_segment)
                    self.jump_to_segment = None
                
                ret, frame = self.cap.read()
                
                if not ret:
                    # 回到第一段重新播放
                    self.jump_to(1)
                    continue
                
                current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                
                # 檢查是否需要跳到下一段
                current_segment_config = self.segments[self.current_segment - 1]
                if current_frame >= current_segment_config.end_frame:
                    next_segment = (self.current_segment % len(self.segments)) + 1
                    self.jump_to(next_segment)
                    continue
                
                # 繪製資訊文字
                text = f"Segment: {self.current_segment}/{len(self.segments)} | Frame: {current_frame}/{self.total_frames}"
                cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.8, (0, 255, 0), 2, cv2.LINE_AA)
                
                cv2.imshow(self.window_name, frame)
                
                key = cv2.waitKey(frame_delay) & 0xFF
                if key == 27:  # ESC 鍵
                    self.playing = False
                    break
        
        except Exception as e:
            print(f"播放錯誤: {e}")
        finally:
            cv2.destroyWindow(self.window_name)
    
    def cleanup(self):
        """清理資源"""
        self.stop_playing()
        
        with self._lock:
            if self.cap:
                self.cap.release()
                self.cap = None
        
        try:
            cv2.destroyAllWindows()
        except:
            pass


# ===================== 顏色選取器 =====================
class ColorPicker:
    """顏色選取器"""
    
    def __init__(self, callback):
        self.callback = callback
        self.listener = None
    
    def start(self):
        """開始選取顏色"""
        from pynput import mouse
        
        def on_click(x, y, button, pressed):
            if pressed:
                color = ColorUtils.get_screen_color(x, y)
                if color:
                    self.callback(color)
                if self.listener:
                    self.listener.stop()
        
        self.listener = mouse.Listener(on_click=on_click)
        self.listener.start()


# ===================== 主控制面板 =====================
class ADBController(QWidget):
    def __init__(self):
        super().__init__()
        self.video_player: Optional[VideoSegmentPlayer] = None
        self.segment_configs: List[SegmentConfig] = []
        self.color_detection_active = False
        self.video_path: Optional[str] = None
        self.segment_input_widgets = []
        self.root_mode = False  # ROOT 模式標記
        
        self.initUI()
    
    def initUI(self):
        """初始化 UI"""
        self.setWindowTitle('ADB 控制面板 + 顏色影片控制')
        self.setGeometry(100, 100, 700, 850)
        
        main_layout = QVBoxLayout()
        
        # ADB 控制區
        main_layout.addWidget(self._create_adb_controls())
        
        # 即時取色顯示
        main_layout.addWidget(self._create_color_display())
        
        # 影片設定區
        main_layout.addWidget(self._create_video_settings())
        
        # 片段顏色設定區
        main_layout.addWidget(self._create_segment_color_settings())
        
        # 控制按鈕
        main_layout.addLayout(self._create_control_buttons())
        
        # 狀態標籤
        self.status_label = QLabel("狀態: 待機中")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; padding: 10px; background-color: #e8e8e8;")
        main_layout.addWidget(self.status_label)
        
        self.setLayout(main_layout)
        
        # 啟動即時取色 Timer
        self.color_timer = QTimer()
        self.color_timer.timeout.connect(self._update_mouse_color)
        self.color_timer.start(50)
    
    def _create_adb_controls(self) -> QGroupBox:
        """創建 ADB 控制區"""
        group = QGroupBox("ADB 控制")
        main_layout = QVBoxLayout()
        
        # ROOT 模式切換
        root_layout = QHBoxLayout()
        self.root_mode_checkbox = QCheckBox("🔓 ROOT 模式")
        self.root_mode_checkbox.setStyleSheet("font-weight: bold; color: #ff6600;")
        self.root_mode_checkbox.stateChanged.connect(self._on_root_mode_changed)
        root_layout.addWidget(self.root_mode_checkbox)
        
        self.root_status_label = QLabel("(未啟用)")
        self.root_status_label.setStyleSheet("color: #666;")
        root_layout.addWidget(self.root_status_label)
        
        btn_check_root = QPushButton("檢查 ROOT")
        btn_check_root.clicked.connect(self.check_root_access)
        root_layout.addWidget(btn_check_root)
        
        root_layout.addStretch()
        main_layout.addLayout(root_layout)
        
        # 第一行：基本控制
        row1 = QHBoxLayout()
        buttons_row1 = [
            ('返回', self.adb_back),
            ('主畫面', self.adb_home),
            ('截圖', self.adb_screenshot),
            ('啟動 scrcpy', self.start_screen_stream)
        ]
        
        for text, callback in buttons_row1:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            row1.addWidget(btn)
        
        # 第二行：網路共享控制
        row2 = QHBoxLayout()
        buttons_row2 = [
            ('📶 開啟熱點', self.adb_enable_hotspot),
            ('📵 關閉熱點', self.adb_disable_hotspot),
            ('🔌 開啟 USB 共享', self.adb_enable_usb_tethering),
            ('🔇 關閉 USB 共享', self.adb_disable_usb_tethering),
            ('📊 共享狀態', self.adb_check_tethering)
        ]
        
        for text, callback in buttons_row2:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            row2.addWidget(btn)
        
        main_layout.addLayout(row1)
        main_layout.addLayout(row2)
        group.setLayout(main_layout)
        return group
    
    def _create_color_display(self) -> QGroupBox:
        """創建即時取色顯示區"""
        group = QGroupBox("即時取色")
        layout = QVBoxLayout()
        
        self.color_label = QLabel("滑鼠位置顏色: RGB(---, ---, ---)")
        self.color_label.setAlignment(Qt.AlignCenter)
        self.color_label.setStyleSheet("font-size: 16px; padding: 15px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(self.color_label)
        
        group.setLayout(layout)
        return group
    
    def _create_video_settings(self) -> QGroupBox:
        """創建影片設定區"""
        group = QGroupBox("影片設定")
        layout = QVBoxLayout()
        
        # 載入影片按鈕
        btn_load = QPushButton('📂 載入影片')
        btn_load.clicked.connect(self.load_video)
        btn_load.setStyleSheet("padding: 8px; font-size: 14px;")
        layout.addWidget(btn_load)
        
        # 影片資訊標籤
        self.video_info_label = QLabel("尚未載入影片")
        self.video_info_label.setStyleSheet("padding: 5px; color: #666;")
        layout.addWidget(self.video_info_label)
        
        # 片段數量設定
        segment_layout = QHBoxLayout()
        segment_layout.addWidget(QLabel("切分片段數:"))
        
        self.segment_spinbox = QSpinBox()
        self.segment_spinbox.setMinimum(2)
        self.segment_spinbox.setMaximum(20)
        self.segment_spinbox.setValue(3)
        self.segment_spinbox.valueChanged.connect(self._update_segment_inputs)
        segment_layout.addWidget(self.segment_spinbox)
        segment_layout.addStretch()
        
        layout.addLayout(segment_layout)
        group.setLayout(layout)
        return group
    
    def _create_segment_color_settings(self) -> QGroupBox:
        """創建片段顏色設定區"""
        self.segment_color_group = QGroupBox("片段顏色與起始幀設定")
        layout = QVBoxLayout()
        
        # 使用 ScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.segment_inputs_layout = QVBoxLayout(scroll_content)
        scroll.setWidget(scroll_content)
        
        layout.addWidget(scroll)
        self.segment_color_group.setLayout(layout)
        
        # 初始化片段輸入欄位
        self._update_segment_inputs()
        
        return self.segment_color_group
    
    def _create_control_buttons(self) -> QHBoxLayout:
        """創建控制按鈕"""
        layout = QHBoxLayout()
        
        self.btn_start_video = QPushButton('▶ 開始播放')
        self.btn_start_video.clicked.connect(self.start_video)
        self.btn_start_video.setEnabled(False)
        self.btn_start_video.setStyleSheet("padding: 10px; font-size: 14px;")
        layout.addWidget(self.btn_start_video)
        
        self.btn_start_detection = QPushButton('🎯 開始顏色偵測')
        self.btn_start_detection.clicked.connect(self.start_color_detection)
        self.btn_start_detection.setEnabled(False)
        self.btn_start_detection.setStyleSheet("padding: 10px; font-size: 14px;")
        layout.addWidget(self.btn_start_detection)
        
        self.btn_stop_detection = QPushButton('⏸ 停止偵測')
        self.btn_stop_detection.clicked.connect(self.stop_detection)
        self.btn_stop_detection.setEnabled(False)
        self.btn_stop_detection.setStyleSheet("padding: 10px; font-size: 14px;")
        layout.addWidget(self.btn_stop_detection)
        
        self.btn_stop = QPushButton('⏹ 全部停止')
        self.btn_stop.clicked.connect(self.stop_all)
        self.btn_stop.setStyleSheet("padding: 10px; font-size: 14px; background-color: #ffcccc;")
        layout.addWidget(self.btn_stop)
        
        return layout
    
    def _update_mouse_color(self):
        """更新滑鼠位置顏色顯示"""
        try:
            x, y = pyautogui.position()
            color = ColorUtils.get_screen_color(x, y)
            
            if color:
                r, g, b = color
                text_color = ColorUtils.get_contrast_color(r, g, b)
                
                self.color_label.setText(f"滑鼠位置 ({x}, {y}) 顏色: RGB({r}, {g}, {b})")
                self.color_label.setStyleSheet(
                    f"font-size: 16px; padding: 15px; background-color: rgb({r},{g},{b}); "
                    f"color: {text_color}; border-radius: 5px;"
                )
        except Exception as e:
            pass
    
    def _update_segment_inputs(self):
        """更新片段輸入欄位"""
        # 儲存舊設定
        old_settings = []
        for widgets in self.segment_input_widgets:
            old_settings.append({
                'r': widgets['r'].value(),
                'g': widgets['g'].value(),
                'b': widgets['b'].value(),
                'tolerance': widgets['tolerance'].value(),
                'start_frame': widgets['start_frame'].value()
            })
        
        # 清除舊的輸入欄位
        for widget_group in self.segment_input_widgets:
            for widget in widget_group.values():
                if hasattr(widget, 'deleteLater'):
                    widget.deleteLater()
        self.segment_input_widgets.clear()
        
        num_segments = self.segment_spinbox.value()
        
        # 計算每段的預設幀數範圍
        if self.video_player:
            frames_per_segment = self.video_player.total_frames // num_segments
        else:
            frames_per_segment = 1000
        
        # 為每個片段創建輸入欄位
        for i in range(num_segments):
            segment_frame = QGroupBox(f"片段 {i+1}")
            segment_layout = QVBoxLayout()
            
            # 第一行:顏色設定
            row1 = QHBoxLayout()
            
            btn_copy = QPushButton('🎨 擷取顏色')
            btn_copy.clicked.connect(lambda checked, idx=i: self._pick_color_for_segment(idx))
            row1.addWidget(btn_copy)
            
            row1.addWidget(QLabel("R:"))
            r_input = QSpinBox()
            r_input.setMaximum(255)
            r_input.setValue(old_settings[i]['r'] if i < len(old_settings) else 0)
            row1.addWidget(r_input)
            
            row1.addWidget(QLabel("G:"))
            g_input = QSpinBox()
            g_input.setMaximum(255)
            g_input.setValue(old_settings[i]['g'] if i < len(old_settings) else 0)
            row1.addWidget(g_input)
            
            row1.addWidget(QLabel("B:"))
            b_input = QSpinBox()
            b_input.setMaximum(255)
            b_input.setValue(old_settings[i]['b'] if i < len(old_settings) else 0)
            row1.addWidget(b_input)
            
            row1.addWidget(QLabel("容差:"))
            tolerance_input = QSpinBox()
            tolerance_input.setMaximum(100)
            tolerance_input.setValue(old_settings[i]['tolerance'] if i < len(old_settings) else 30)
            row1.addWidget(tolerance_input)
            
            # 第二行:起始幀設定
            row2 = QHBoxLayout()
            row2.addWidget(QLabel("起始幀:"))
            start_frame_input = QSpinBox()
            start_frame_input.setMaximum(999999)
            start_frame_input.setValue(
                old_settings[i]['start_frame'] if i < len(old_settings) 
                else i * frames_per_segment
            )
            row2.addWidget(start_frame_input)
            row2.addWidget(QLabel(f"(建議: {i * frames_per_segment})"))
            row2.addStretch()
            
            segment_layout.addLayout(row1)
            segment_layout.addLayout(row2)
            segment_frame.setLayout(segment_layout)
            
            self.segment_inputs_layout.addWidget(segment_frame)
            
            self.segment_input_widgets.append({
                'frame': segment_frame,
                'r': r_input,
                'g': g_input,
                'b': b_input,
                'tolerance': tolerance_input,
                'start_frame': start_frame_input
            })
    
    def _pick_color_for_segment(self, segment_index: int):
        """為指定片段擷取顏色"""
        self.status_label.setText(f"狀態: 🖱 請點擊螢幕任一位置以擷取顏色 (片段 {segment_index + 1})...")
        
        def on_color_picked(color):
            r, g, b = color
            widgets = self.segment_input_widgets[segment_index]
            widgets['r'].setValue(r)
            widgets['g'].setValue(g)
            widgets['b'].setValue(b)
            
            self.status_label.setText(
                f"狀態: ✅ 片段 {segment_index+1} 擷取成功 RGB({r},{g},{b})"
            )
        
        picker = ColorPicker(on_color_picked)
        picker.start()
    
    # ==================== ADB 指令 ====================
    def adb_command(self, command: str):
        """執行 ADB 指令"""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                timeout=10
            )
            if result.returncode != 0:
                print(f'ADB 錯誤: {result.stderr.decode()}')
        except subprocess.TimeoutExpired:
            print('ADB 指令逾時')
        except Exception as e:
            print(f'執行錯誤: {e}')
    
    def adb_back(self):
        self.adb_command('adb shell input keyevent KEYCODE_BACK')
        self.status_label.setText("狀態: 已執行返回")
    
    def adb_home(self):
        self.adb_command('adb shell input keyevent KEYCODE_HOME')
        self.status_label.setText("狀態: 已執行主畫面")
    
    def adb_screenshot(self):
        self.adb_command('adb shell screencap -p /sdcard/screenshot.png')
        self.adb_command('adb pull /sdcard/screenshot.png')
        self.status_label.setText("狀態: 截圖已儲存")
    
    def start_screen_stream(self):
        try:
            subprocess.Popen('scrcpy', shell=True)
            self.status_label.setText("狀態: scrcpy 已啟動")
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"啟動失敗: {e}")
    
    def check_root_access(self):
        """檢查 ROOT 權限"""
        try:
            result = subprocess.run(
                'adb shell su -c "id"',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                encoding='utf-8'
            )
            
            if result.returncode == 0 and 'uid=0' in result.stdout:
                QMessageBox.information(
                    self,
                    "ROOT 檢查",
                    "✅ ROOT 權限可用！\n\n" +
                    f"輸出: {result.stdout.strip()}\n\n" +
                    "現在可以啟用 ROOT 模式來使用完全自動化功能"
                )
                self.root_status_label.setText("(ROOT 可用)")
                self.root_status_label.setStyleSheet("color: #00aa00; font-weight: bold;")
            else:
                QMessageBox.warning(
                    self,
                    "ROOT 檢查",
                    "❌ ROOT 權限不可用\n\n" +
                    "可能原因：\n" +
                    "1. 設備未 ROOT\n" +
                    "2. SuperSU/Magisk 未授權 ADB\n" +
                    "3. ROOT 權限已被拒絕\n\n" +
                    f"錯誤: {result.stderr}"
                )
                self.root_status_label.setText("(ROOT 不可用)")
                self.root_status_label.setStyleSheet("color: #ff0000;")
                
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, "錯誤", "檢查 ROOT 權限逾時")
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"無法檢查 ROOT: {e}")
    
    def _on_root_mode_changed(self, state):
        """ROOT 模式切換"""
        self.root_mode = (state == Qt.Checked)
        
        if self.root_mode:
            # 先檢查 ROOT 權限
            try:
                result = subprocess.run(
                    'adb shell su -c "id"',
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5,
                    encoding='utf-8'
                )
                
                if result.returncode == 0 and 'uid=0' in result.stdout:
                    self.root_status_label.setText("(ROOT 模式啟用)")
                    self.root_status_label.setStyleSheet("color: #00aa00; font-weight: bold;")
                    self.status_label.setText("狀態: 🔓 ROOT 模式已啟用")
                else:
                    self.root_mode_checkbox.setChecked(False)
                    self.root_mode = False
                    QMessageBox.warning(
                        self,
                        "ROOT 不可用",
                        "無法啟用 ROOT 模式\n\n請確保設備已 ROOT 並授權 ADB"
                    )
            except:
                self.root_mode_checkbox.setChecked(False)
                self.root_mode = False
                QMessageBox.warning(self, "錯誤", "無法檢查 ROOT 權限")
        else:
            self.root_status_label.setText("(未啟用)")
            self.root_status_label.setStyleSheet("color: #666;")
            self.status_label.setText("狀態: ROOT 模式已關閉")
    
    def adb_root_command(self, command: str):
        """執行 ROOT ADB 指令"""
        if self.root_mode:
            return self.adb_command(f'adb shell su -c "{command}"')
        else:
            return self.adb_command(f'adb shell {command}')
    
    def adb_enable_hotspot(self):
        """開啟 WiFi 熱點（網路共享）"""
        if self.root_mode:
            # ROOT 模式：完全自動化
            try:
                # 方法 1: 使用 settings 命令
                self.adb_root_command('settings put global wifi_ap_state 13')
                
                # 方法 2: 使用 svc 命令
                self.adb_root_command('svc wifi enable')
                
                # 方法 3: 使用 cmd 命令 (Android 11+)
                self.adb_command('adb shell cmd connectivity tether wifi on')
                
                self.status_label.setText("狀態: 📶 ROOT 模式 - 熱點已自動開啟")
                
                QMessageBox.information(
                    self,
                    "WiFi 熱點",
                    "✅ ROOT 模式啟用成功！\n\n" +
                    "已使用 ROOT 權限自動開啟熱點"
                )
            except Exception as e:
                QMessageBox.warning(self, "錯誤", f"ROOT 開啟失敗: {e}")
        else:
            # 非 ROOT 模式：開啟設定頁面
            self.adb_command('adb shell am start -n com.android.settings/.TetherSettings')
            self.status_label.setText("狀態: 📶 已開啟熱點設定頁面")
            
            QMessageBox.information(
                self, 
                "WiFi 熱點", 
                "已開啟熱點設定頁面\n\n" +
                "💡 提示：啟用 ROOT 模式可以自動開啟熱點\n\n" +
                "由於 Android 安全限制，非 ROOT 模式需要手動啟用"
            )
    
    def adb_disable_hotspot(self):
        """關閉 WiFi 熱點"""
        if self.root_mode:
            # ROOT 模式：完全自動化
            self.adb_root_command('settings put global wifi_ap_state 11')
            self.adb_command('adb shell cmd connectivity tether wifi off')
            self.status_label.setText("狀態: 📵 ROOT 模式 - 熱點已關閉")
        else:
            # 非 ROOT 模式
            self.adb_command('adb shell cmd connectivity tether wifi off')
            self.status_label.setText("狀態: 📵 已嘗試關閉熱點")
    
    def adb_enable_usb_tethering(self):
        """開啟 USB 網路共享"""
        try:
            if self.root_mode:
                # ROOT 模式：更可靠的方法
                self.adb_root_command('setprop sys.usb.config rndis,adb')
                self.adb_command('adb shell cmd connectivity tether usb on')
                self.status_label.setText("狀態: 🔌 ROOT 模式 - USB 網路共享已開啟")
                
                QMessageBox.information(
                    self,
                    "USB 網路共享",
                    "✅ ROOT 模式啟用成功！\n\n" +
                    "USB 網路共享已自動開啟"
                )
            else:
                # 非 ROOT 模式
                self.adb_command('adb shell cmd connectivity tether usb on')
                self.status_label.setText("狀態: 🔌 已開啟 USB 網路共享")
                
                QMessageBox.information(
                    self,
                    "USB 網路共享",
                    "已嘗試開啟 USB 網路共享\n\n" +
                    "💡 提示：啟用 ROOT 模式可提高成功率\n\n" +
                    "如果未成功，可能需要：\n" +
                    "1. ROOT 權限\n" +
                    "2. 確保 USB 已連接\n" +
                    "3. 手動到設定中啟用"
                )
            
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"開啟失敗: {e}")
    
    def adb_disable_usb_tethering(self):
        """關閉 USB 網路共享"""
        try:
            if self.root_mode:
                self.adb_root_command('setprop sys.usb.config adb')
            
            self.adb_command('adb shell cmd connectivity tether usb off')
            self.status_label.setText("狀態: 🔇 已關閉 USB 網路共享")
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"關閉失敗: {e}")
    
    def adb_check_tethering(self):
        """檢查網路共享狀態"""
        try:
            # 檢查 USB 網路共享
            result_usb = subprocess.run(
                'adb shell getprop sys.usb.config',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                encoding='utf-8'
            )
            
            # 檢查熱點狀態
            result_hotspot = subprocess.run(
                'adb shell settings get global wifi_ap_state',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                encoding='utf-8'
            )
            
            # 解析狀態
            usb_status = "USB 網路共享: " + ("🟢 已啟用" if "rndis" in result_usb.stdout else "🔴 未啟用")
            
            hotspot_state = result_hotspot.stdout.strip()
            hotspot_status = "WiFi 熱點: "
            if hotspot_state == "13":
                hotspot_status += "🟢 已啟用"
            elif hotspot_state == "11":
                hotspot_status += "🔴 已停用"
            else:
                hotspot_status += f"⚪ 狀態 {hotspot_state}"
            
            status_msg = f"{usb_status}\n{hotspot_status}"
            
            QMessageBox.information(self, "網路共享狀態", status_msg)
            self.status_label.setText(f"狀態: {usb_status} | {hotspot_status}")
            
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, "錯誤", "檢查狀態逾時")
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"無法檢查狀態: {e}")
    
    # ==================== 影片控制 ====================
    def load_video(self):
        """載入影片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "選擇影片", "", "Video Files (*.mp4 *.avi *.mkv *.mov)"
        )
        
        if not file_path:
            return
        
        self.video_path = file_path
        
        try:
            # 暫時載入以取得影片資訊
            cap = cv2.VideoCapture(file_path)
            
            if not cap.isOpened():
                raise ValueError("無法開啟影片檔案")
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            cap.release()
            
            self.video_info_label.setText(
                f"✅ 已載入 | 總幀數: {total_frames} | FPS: {fps:.1f} | "
                f"時長: {duration:.1f}秒"
            )
            
            self.btn_start_video.setEnabled(True)
            self.btn_start_detection.setEnabled(True)
            
            # 更新片段輸入的建議值
            self._update_segment_inputs()
            
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"載入失敗: {e}")
            self.video_info_label.setText(f"❌ 載入失敗: {e}")
    
    def start_video(self):
        """開始播放影片"""
        if not self.video_path:
            QMessageBox.warning(self, "警告", "請先載入影片")
            return
        
        # 讀取片段設定
        try:
            segments = self._build_segment_configs()
            
            # 清理舊的播放器
            if self.video_player:
                self.video_player.cleanup()
            
            # 創建新播放器
            self.video_player = VideoSegmentPlayer(self.video_path, segments)
            self.video_player.segment_changed.connect(self._on_segment_changed)
            self.video_player.start_playing()
            
            self.status_label.setText("狀態: ▶ 影片播放中")
            
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"播放失敗: {e}")
            self.status_label.setText(f"狀態: ❌ 播放失敗: {e}")
    
    def _build_segment_configs(self) -> List[SegmentConfig]:
        """建立片段配置"""
        segments = []
        
        for i, widgets in enumerate(self.segment_input_widgets):
            start_frame = widgets['start_frame'].value()
            
            # 計算結束幀
            if i < len(self.segment_input_widgets) - 1:
                end_frame = self.segment_input_widgets[i + 1]['start_frame'].value()
            else:
                # 最後一段到影片結尾
                cap = cv2.VideoCapture(self.video_path)
                end_frame = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
            
            # 建立顏色配置
            color = ColorConfig(
                r=widgets['r'].value(),
                g=widgets['g'].value(),
                b=widgets['b'].value(),
                tolerance=widgets['tolerance'].value()
            )
            
            segments.append(SegmentConfig(start_frame, end_frame, color))
        
        return segments
    
    def _on_segment_changed(self, segment_num: int):
        """片段變更時的回調"""
        pass  # 可以在這裡添加額外的處理邏輯
    
    def start_color_detection(self):
        """開始顏色偵測"""
        if not self.video_player or not self.video_player.playing:
            QMessageBox.warning(self, "警告", "請先開始播放影片")
            return
        
        # 建立片段配置
        self.segment_configs = self._build_segment_configs()
        
        print(f"已載入 {len(self.segment_configs)} 個片段顏色設定")
        
        self.color_detection_active = True
        self.btn_start_detection.setEnabled(False)
        self.btn_stop_detection.setEnabled(True)
        self.status_label.setText("狀態: 🎯 顏色偵測中...")
        
        # 每 200ms 偵測一次 (每秒 5 幀)
        self.detection_timer = QTimer()
        self.detection_timer.timeout.connect(self._check_color_and_control)
        self.detection_timer.start(200)
    
    def stop_detection(self):
        """停止顏色偵測"""
        self.color_detection_active = False
        
        if hasattr(self, 'detection_timer'):
            self.detection_timer.stop()
        
        self.btn_start_detection.setEnabled(True)
        self.btn_stop_detection.setEnabled(False)
        self.status_label.setText("狀態: ⏸ 偵測已停止")
    
    def _check_color_and_control(self):
        """檢查顏色並控制影片"""
        if not self.color_detection_active:
            return
        
        try:
            x, y = pyautogui.position()
            current_color = ColorUtils.get_screen_color(x, y)
            
            if not current_color:
                return
            
            # 檢查每個片段的顏色
            for segment_num, config in enumerate(self.segment_configs, start=1):
                if ColorUtils.is_color_match(
                    current_color,
                    (config.color.r, config.color.g, config.color.b),
                    config.color.tolerance
                ):
                    if self.video_player and self.video_player.playing:
                        if self.video_player.current_segment != segment_num:
                            self.video_player.jump_to_segment = segment_num
                            r, g, b = current_color
                            self.status_label.setText(
                                f"狀態: 🎯 匹配片段 {segment_num} | "
                                f"目標 RGB({config.color.r},{config.color.g},{config.color.b}) | "
                                f"當前 RGB({r},{g},{b})"
                            )
                    break
        
        except Exception as e:
            pass
    
    def stop_all(self):
        """停止所有操作"""
        if self.video_player:
            self.video_player.cleanup()
        
        self.stop_detection()
        self.status_label.setText("狀態: ⏹ 已全部停止")
    
    def closeEvent(self, event):
        """關閉事件處理"""
        self.color_timer.stop()
        
        if hasattr(self, 'detection_timer'):
            self.detection_timer.stop()
        
        if self.video_player:
            self.video_player.cleanup()
        
        event.accept()


# ===================== 主程式入口 =====================
def main():
    """主程式入口"""
    app = QApplication(sys.argv)
    
    # 設置應用程式樣式
    app.setStyle('Fusion')
    
    # 創建並顯示主視窗
    controller = ADBController()
    controller.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()