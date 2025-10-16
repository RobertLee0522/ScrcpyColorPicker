import cv2
import threading
import time

class VideoSegmentPlayer:
    def __init__(self, video_path, num_segments=10):
        self.video_path = video_path
        self.num_segments = num_segments
        self.cap = cv2.VideoCapture(video_path)
        
        if not self.cap.isOpened():
            raise ValueError("無法開啟影片檔案")
        
        # 取得影片資訊
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # 計算每個片段的幀數
        self.frames_per_segment = self.total_frames // num_segments
        
        # 當前片段和是否繼續播放的標誌
        self.current_segment = 1
        self.playing = True
        self.jump_to_segment = None
        
        print(f"影片資訊:")
        print(f"總幀數: {self.total_frames}")
        print(f"FPS: {self.fps}")
        print(f"片段數: {self.num_segments}")
        print(f"每片段幀數: {self.frames_per_segment}")
        print(f"\n操作說明:")
        print(f"- 輸入 1-{self.num_segments} 跳轉到對應片段")
        print(f"- 輸入 'q' 退出播放")
        print(f"- 按 ESC 或關閉視窗也可退出\n")
    
    def get_segment_start_frame(self, segment_num):
        """取得指定片段的起始幀"""
        if segment_num < 1 or segment_num > self.num_segments:
            return None
        return (segment_num - 1) * self.frames_per_segment
    
    def jump_to(self, segment_num):
        """跳轉到指定片段"""
        start_frame = self.get_segment_start_frame(segment_num)
        if start_frame is not None:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            self.current_segment = segment_num
            print(f"\n>>> 跳轉到第 {segment_num} 段")
            return True
        return False
    
    def input_thread(self):
        """獨立執行緒處理使用者輸入"""
        while self.playing:
            try:
                user_input = input()
                
                if user_input.lower() == 'q':
                    self.playing = False
                    print("停止播放...")
                    break
                
                try:
                    segment_num = int(user_input)
                    if 1 <= segment_num <= self.num_segments:
                        self.jump_to_segment = segment_num
                    else:
                        print(f"請輸入 1-{self.num_segments} 之間的數字")
                except ValueError:
                    print("請輸入有效的數字或 'q' 退出")
            except:
                break
    
    def play(self):
        """播放影片"""
        # 啟動輸入執行緒
        input_thread = threading.Thread(target=self.input_thread, daemon=True)
        input_thread.start()
        
        # 從第一段開始播放
        self.jump_to(1)
        
        cv2.namedWindow('Video Player', cv2.WINDOW_NORMAL)
        
        while self.playing:
            # 檢查是否需要跳轉
            if self.jump_to_segment is not None:
                self.jump_to(self.jump_to_segment)
                self.jump_to_segment = None
            
            ret, frame = self.cap.read()
            
            if not ret:
                print("\n影片播放結束")
                break
            
            # 取得當前幀數和片段
            current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            current_seg = (current_frame // self.frames_per_segment) + 1
            
            if current_seg > self.num_segments:
                current_seg = self.num_segments
            
            # 在畫面上顯示當前片段資訊
            text = f"Segment: {current_seg}/{self.num_segments} | Frame: {current_frame}/{self.total_frames}"
            cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       1, (0, 255, 0), 2, cv2.LINE_AA)
            
            cv2.imshow('Video Player', frame)
            
            # 按 ESC 退出
            key = cv2.waitKey(int(1000/self.fps)) & 0xFF
            if key == 27:  # ESC
                print("\n使用者按下 ESC，停止播放")
                self.playing = False
                break
        
        self.cleanup()
    
    def cleanup(self):
        """清理資源"""
        self.cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    # 使用範例
    video_path = r"C:\Users\54-0461100-01\Desktop\python\scrcpy-win64-v3.1\DSCF4587.MOV"  # 請替換成你的影片路徑
    num_segments = 10  # 分成 10 等份
    
    try:
        player = VideoSegmentPlayer(video_path, num_segments)
        player.play()
    except Exception as e:
        print(f"發生錯誤: {e}")