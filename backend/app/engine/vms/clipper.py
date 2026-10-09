import os
import cv2
import numpy as np
import time
import uuid
import threading
from datetime import datetime
from typing import List, Tuple, Optional
from pathlib import Path

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.db.base import VideoClip

class ClipRecorder:
    """
    Asynchronous event-based video clipping engine.
    Combines pre-event frames from RollingFrameBuffer with post-event frames,
    encodes to H.264 MP4, extracts thumbnail, and records metadata in database.
    """
    def __init__(self):
        self.active_jobs = []

    def record_event_clip(
        self,
        camera_id: str,
        event_type: str,
        pre_frames: List[Tuple[float, np.ndarray]],
        get_current_frame_fn,
        post_duration_sec: float = 10.0,
        fps: int = 25
    ):
        """
        Spawns a background thread to collect post-event frames for post_duration_sec,
        then writes the full video file.
        """
        thread = threading.Thread(
            target=self._clip_worker,
            args=(camera_id, event_type, pre_frames, get_current_frame_fn, post_duration_sec, fps),
            daemon=True
        )
        thread.start()

    def _clip_worker(
        self,
        camera_id: str,
        event_type: str,
        pre_frames: List[Tuple[float, np.ndarray]],
        get_current_frame_fn,
        post_duration_sec: float,
        fps: int
    ):
        post_frames = []
        start_time = time.time()
        interval = 1.0 / max(1, fps)

        # Collect post-event frames for requested duration
        while time.time() - start_time < post_duration_sec:
            f = get_current_frame_fn()
            if f is not None:
                post_frames.append((time.time(), f.copy()))
            time.sleep(interval)

        # Combine all frames
        all_frames = pre_frames + post_frames
        if not all_frames:
            return

        # Determine dimensions
        first_frame = all_frames[0][1]
        h, w = first_frame.shape[:2]

        clip_id = str(uuid.uuid4())
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        clip_filename = f"clip_{camera_id[:6]}_{event_type}_{timestamp_str}_{clip_id[:6]}.mp4"
        thumb_filename = f"thumb_{camera_id[:6]}_{timestamp_str}_{clip_id[:6]}.jpg"

        clip_path = settings.CLIPS_PATH / clip_filename
        thumb_path = settings.CLIPS_PATH / thumb_filename

        # Save trigger thumbnail (midpoint frame)
        mid_idx = len(all_frames) // 2
        cv2.imwrite(str(thumb_path), all_frames[mid_idx][1])

        # Write MP4 file
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(clip_path), fourcc, fps, (w, h))

        for ts, frame in all_frames:
            if frame.shape[:2] != (h, w):
                frame = cv2.resize(frame, (w, h))
            writer.write(frame)

        writer.release()
        total_duration = len(all_frames) / float(fps)

        # Save to database
        try:
            db = SessionLocal()
            record = VideoClip(
                id=clip_id,
                camera_id=camera_id,
                event_type=event_type,
                start_time=datetime.fromtimestamp(all_frames[0][0]),
                end_time=datetime.fromtimestamp(all_frames[-1][0]),
                duration_sec=round(total_duration, 1),
                file_path=str(clip_path),
                thumbnail_path=str(thumb_path),
                cloud_synced=False
            )
            db.add(record)
            db.commit()
            db.close()
            print(f"[ClipRecorder] Event clip generated successfully: {clip_filename} ({total_duration:.1f}s)")

            # Dispatch automatic Google Cloud Storage upload
            try:
                from backend.app.engine.storage.gcs_manager import gcs_manager
                if gcs_manager.is_configured():
                    print(f"[ClipRecorder] Uploading clip {clip_id} to GCS Bucket '{gcs_manager.bucket_name}'...")
                    upload_res = gcs_manager.upload_video_clip(
                        clip_id=clip_id,
                        file_path=str(clip_path),
                        thumbnail_path=str(thumb_path),
                        auto_delete_local=settings.GCS_AUTO_DELETE_LOCAL
                    )
                    if upload_res.get("success"):
                        print(f"[ClipRecorder] Successfully uploaded to GCS: {upload_res.get('cloud_url')}")
                    else:
                        print(f"[ClipRecorder] GCS upload notice: {upload_res.get('error')}")
            except Exception as gcs_err:
                print(f"[ClipRecorder] GCS upload error: {gcs_err}")

        except Exception as e:
            print(f"[ClipRecorder] Database save error: {e}")

clip_recorder = ClipRecorder()
