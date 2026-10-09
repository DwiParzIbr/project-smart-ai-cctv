import time
import threading
from collections import deque
from typing import List, Tuple, Optional
import numpy as np

class RollingFrameBuffer:
    """
    Circular thread-safe frame buffer holding the past T seconds of video frames
    for pre-event video clipping.
    """
    def __init__(self, max_seconds: int = 10, fps: int = 25):
        self.max_seconds = max_seconds
        self.fps = fps
        self.max_frames = max_seconds * fps  # e.g., 250 frames
        self.buffer = deque(maxlen=self.max_frames)
        self.lock = threading.Lock()

    def append(self, frame: np.ndarray, timestamp: Optional[float] = None):
        """Append a frame to the rolling buffer."""
        if frame is None:
            return
        ts = timestamp or time.time()
        with self.lock:
            # We downscale slightly or keep frame copy to prevent reference mutation
            self.buffer.append((ts, frame.copy()))

    def get_pre_event_frames(self) -> List[Tuple[float, np.ndarray]]:
        """Return a copy of all buffered pre-event frames."""
        with self.lock:
            return list(self.buffer)

    def clear(self):
        with self.lock:
            self.buffer.clear()
