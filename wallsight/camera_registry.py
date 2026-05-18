import threading
import time
from typing import Dict, Optional
import numpy as np
import cv2

class CameraRegistry:
    """
    Holds the latest frame from every connected camera.
    Cameras can be:
      - Browser WebSocket (Mac A, Android, iPhone)
      - Local webcam (Mac B built-in)
      - ESP32-CAM MJPEG HTTP (future)
    All produce the same output: a numpy BGR frame.
    """

    def __init__(self):
        self._frames: Dict[str, np.ndarray] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()

    def update(self, camera_id: str, frame: np.ndarray):
        with self._lock:
            self._frames[camera_id] = frame
            self._timestamps[camera_id] = time.time()

    def get(self, camera_id: str) -> Optional[np.ndarray]:
        with self._lock:
            return self._frames.get(camera_id)

    def get_all_active(self, max_age_seconds: float = 2.0):
        """Returns all cameras with a recent frame."""
        now = time.time()
        with self._lock:
            return {
                cid: frame.copy()
                for cid, frame in self._frames.items()
                if now - self._timestamps.get(cid, 0) < max_age_seconds
            }

    def list_cameras(self):
        with self._lock:
            return list(self._frames.keys())


# Global registry — shared across all threads
registry = CameraRegistry()
