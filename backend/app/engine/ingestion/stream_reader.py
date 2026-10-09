import os
import cv2
import time
import threading
import numpy as np
from typing import Optional, Tuple
from pathlib import Path

# Configure FFmpeg headers for remote live CCTV streams (Cloudflare protected, etc.)
DEFAULT_STREAM_HEADERS = (
    "Origin: https://analisabengkulu.com\r\n"
    "Referer: https://analisabengkulu.com/\r\n"
    "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36\r\n"
)
os.environ["OPENCV_FFMPEG_HTTP_HEADERS"] = DEFAULT_STREAM_HEADERS

class VideoStreamReader:
    def __init__(self, camera_id: str, source_url: str, source_type: str = "RTSP", fps_limit: int = 25):
        self.camera_id = camera_id
        self.source_url = source_url
        self.source_type = source_type.upper()
        self.fps_limit = max(0, fps_limit)  # 0 means full native camera FPS
        
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        
        self.current_frame: Optional[np.ndarray] = None
        self.last_frame_time = 0.0
        self.is_connected = False
        self.fps_measured = 0.0
        
        # Simulated generator state if synthetic
        self._sim_step = 0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.thread = None

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None

    def _generate_synthetic_traffic_frame(self) -> np.ndarray:
        """
        Generate a photorealistic simulated road scene with moving vehicles and pedestrians
        for standalone testing when external RTSP/HLS feeds are not accessible.
        """
        width, height = 1280, 720
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # 1. Background (Sky & Road)
        frame[0:300] = [60, 50, 45]       # City background
        frame[300:720] = [40, 40, 40]     # Asphalt road

        # Road markings
        # Yellow center lines
        for y in range(320, 720, 80):
            cv2.line(frame, (640, y), (640, y + 40), (0, 215, 255), 4)

        # Curbs
        cv2.line(frame, (150, 300), (50, 720), (200, 200, 200), 5)
        cv2.line(frame, (1130, 300), (1230, 720), (200, 200, 200), 5)

        # Sidewalk
        cv2.fillPoly(frame, [np.array([[0, 300], [150, 300], [50, 720], [0, 720]])], (70, 70, 70))
        cv2.fillPoly(frame, [np.array([[1130, 300], [1280, 300], [1280, 720], [1230, 720]])], (70, 70, 70))

        # Time step
        self._sim_step += 1
        t = self._sim_step

        # Vehicle 1: Moving Downwards (IN)
        v1_y = int((t * 6) % 900) - 150
        if -100 <= v1_y <= 750:
            v1_x = 420
            # Car body
            cv2.rectangle(frame, (v1_x, v1_y), (v1_x + 130, v1_y + 190), (180, 40, 40), -1)
            cv2.rectangle(frame, (v1_x + 15, v1_y + 35), (v1_x + 115, v1_y + 140), (80, 20, 20), -1)
            # Windshield
            cv2.rectangle(frame, (v1_x + 20, v1_y + 110), (v1_x + 110, v1_y + 135), (200, 220, 230), -1)
            # License Plate
            cv2.rectangle(frame, (v1_x + 35, v1_y + 170), (v1_x + 95, v1_y + 185), (250, 250, 250), -1)
            cv2.putText(frame, "B 1234 CD", (v1_x + 37, v1_y + 182), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)

        # Vehicle 2: Moving Upwards (OUT)
        v2_y = 800 - int(((t * 8) + 300) % 1000)
        if -100 <= v2_y <= 750:
            v2_x = 760
            cv2.rectangle(frame, (v2_x, v2_y), (v2_x + 120, v2_y + 180), (30, 120, 180), -1)
            cv2.rectangle(frame, (v2_x + 15, v2_y + 35), (v2_x + 105, v2_y + 135), (20, 70, 100), -1)
            cv2.rectangle(frame, (v2_x + 30, v2_y + 165), (v2_x + 90, v2_y + 178), (250, 250, 250), -1)
            cv2.putText(frame, "D 9981 XY", (v2_x + 32, v2_y + 175), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)

        # Pedestrian 1: Walking on sidewalk
        p1_y = int((t * 2 + 100) % 800) - 50
        if 0 <= p1_y <= 700:
            cv2.circle(frame, (90, p1_y), 15, (190, 160, 140), -1)
            cv2.rectangle(frame, (75, p1_y + 15), (105, p1_y + 70), (40, 150, 40), -1)
            cv2.line(frame, (83, p1_y + 70), (80, p1_y + 105), (30, 30, 80), 4)
            cv2.line(frame, (97, p1_y + 70), (100, p1_y + 105), (30, 30, 80), 4)

        # CCTV timestamp and camera watermark
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"CAM LIVE: {self.camera_id[:8]} | {now_str}", (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        return frame

    def _generate_connecting_frame(self, message: str = "Menghubungkan ke Feed Kamera...") -> np.ndarray:
        """
        Generate a professional dark surveillance waiting screen
        when connecting or reconnecting to a real IP/HLS camera.
        """
        width, height = 1280, 720
        frame = np.full((height, width, 3), (20, 24, 30), dtype=np.uint8)

        # Draw grid pattern
        for y in range(0, height, 40):
            cv2.line(frame, (0, y), (width, y), (30, 35, 45), 1)
        for x in range(0, width, 40):
            cv2.line(frame, (x, 0), (x, height), (30, 35, 45), 1)

        # Center info box
        cv2.rectangle(frame, (320, 230), (960, 490), (15, 20, 25), -1)
        cv2.rectangle(frame, (320, 230), (960, 490), (56, 189, 248), 2)

        # Header
        cv2.putText(frame, "SMART AI CCTV SURVEILLANCE - LIVE FEED", (350, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (56, 189, 248), 2)
        cv2.putText(frame, f"STATUS: {message}", (350, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(frame, f"SOURCE: {self.source_type} ({self.source_url[:42]}...)", (350, 375), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 175, 195), 1)

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"WAKTU SISTEM: {now_str}", (350, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 220, 120), 1)
        cv2.putText(frame, "Sedang menyambungkan stream video...", (350, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 200, 100), 1)
        return frame

    def _capture_loop(self):
        backoff_sec = 1.0
        frame_interval = (1.0 / self.fps_limit) if self.fps_limit > 0 else 0.033

        while self.running:
            # Handle synthetic / demo mode
            if self.source_type == "SYNTHETIC" or self.source_url.lower() == "demo":
                self.is_connected = True
                frame = self._generate_synthetic_traffic_frame()
                with self.lock:
                    self.current_frame = frame
                time.sleep(frame_interval)
                continue

            # Real stream capture
            cap = None
            try:
                # Ensure headers are configured in current thread environment
                os.environ["OPENCV_FFMPEG_HTTP_HEADERS"] = DEFAULT_STREAM_HEADERS

                if self.source_url.isdigit():
                    cap = cv2.VideoCapture(int(self.source_url))
                else:
                    # RTSP / HLS options
                    cap = cv2.VideoCapture(self.source_url)
                    if self.source_type == "RTSP":
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not cap.isOpened():
                    self.is_connected = False
                    print(f"[StreamReader] Cannot connect to {self.source_url}. Retrying in {backoff_sec:.1f}s...")
                    frame = self._generate_connecting_frame(f"CONNECTING ({backoff_sec:.0f}s)...")
                    with self.lock:
                        self.current_frame = frame
                    time.sleep(backoff_sec)
                    backoff_sec = min(backoff_sec * 1.5, 15.0)
                    continue

                self.is_connected = True
                backoff_sec = 1.0
                frame_count = 0
                fps_timer = time.time()

                while self.running and cap.isOpened():
                    start_time = time.time()
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        print(f"[StreamReader] Stream disconnected for camera {self.camera_id}")
                        frame = self._generate_connecting_frame("RECONNECTING...")
                        with self.lock:
                            self.current_frame = frame
                        break

                    with self.lock:
                        self.current_frame = frame

                    # FPS measurement
                    frame_count += 1
                    if time.time() - fps_timer >= 1.0:
                        self.fps_measured = frame_count / (time.time() - fps_timer)
                        frame_count = 0
                        fps_timer = time.time()

                    # Throttle only if fps_limit is configured under 30 FPS
                    if 0 < self.fps_limit < 30:
                        elapsed = time.time() - start_time
                        delay = max(0.001, frame_interval - elapsed)
                        time.sleep(delay)
                    else:
                        time.sleep(0.001)

            except Exception as e:
                print(f"[StreamReader] Exception on camera {self.camera_id}: {e}")
                self.is_connected = False
                frame = self._generate_connecting_frame(f"ERROR: {str(e)[:30]}")
                with self.lock:
                    self.current_frame = frame
            finally:
                if cap is not None:
                    cap.release()

            if self.running:
                time.sleep(backoff_sec)
                backoff_sec = min(backoff_sec * 1.5, 15.0)

        self.is_connected = False
