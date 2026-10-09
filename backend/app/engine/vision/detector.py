import os
import torch
from pathlib import Path
from typing import List, Dict, Any, Optional
from ultralytics import YOLO
from backend.app.core.config import settings

COCO_CLASS_MAP = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

REVERSE_CLASS_MAP = {v: k for k, v in COCO_CLASS_MAP.items()}

class VisionDetector:
    def __init__(self, model_name: str = "yolo11n.pt"):
        self.model_name = model_name
        self.device = os.getenv("DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        print(f"[VisionDetector] Initializing YOLO model: {model_name} on device: {self.device}")
        
        # Load or download model
        model_path = settings.MODELS_PATH / model_name
        if not model_path.exists():
            # If not in custom models path, ultralytics will auto-download yolo11n.pt
            self.model = YOLO(model_name)
        else:
            self.model = YOLO(str(model_path))

    def detect_and_track(
        self,
        frame,
        target_classes: Optional[List[str]] = None,
        conf_threshold: float = 0.35
    ) -> List[Dict[str, Any]]:
        """
        Run YOLOv11 detection with ByteTrack multi-object tracking.
        """
        if frame is None:
            return []

        # Determine target class IDs
        if target_classes:
            allowed_ids = [REVERSE_CLASS_MAP[c] for c in target_classes if c in REVERSE_CLASS_MAP]
        else:
            allowed_ids = list(COCO_CLASS_MAP.keys())

        try:
            # Run tracking with ByteTrack
            results = self.model.track(
                source=frame,
                persist=True,
                tracker="bytetrack.yaml",
                classes=allowed_ids,
                conf=conf_threshold,
                verbose=False,
                device=self.device
            )

            tracked_objects = []
            if not results or len(results) == 0:
                return []

            r = results[0]
            boxes = r.boxes
            if boxes is None or len(boxes) == 0:
                return []

            for box in boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                class_name = COCO_CLASS_MAP.get(cls_id, "unknown")

                # Get track ID (can be None if not tracked yet)
                track_id = int(box.id[0].item()) if box.id is not None else None

                xyxy = box.xyxy[0].tolist()
                x1, y1, x2, y2 = xyxy

                # Calculate bottom-center contact point
                bottom_center = ((x1 + x2) / 2.0, y2)
                center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

                tracked_objects.append({
                    "track_id": track_id,
                    "class_name": class_name,
                    "confidence": round(conf, 2),
                    "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                    "center": center,
                    "bottom_center": bottom_center
                })

            return tracked_objects
        except Exception as e:
            print(f"[VisionDetector] Inference error: {e}")
            return []
