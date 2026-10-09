import cv2
import numpy as np
import os
import uuid
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
from backend.app.core.config import settings
from backend.app.engine.anpr.plate_parser import normalize_indonesian_plate, clean_ocr_text

class PlateOCREngine:
    def __init__(self):
        self._reader = None
        self._initialized = False

    def _get_reader(self):
        if not self._initialized:
            try:
                import easyocr
                # Initialize English OCR for alphanumeric plates
                self._reader = easyocr.Reader(['en'], gpu=False, verbose=False)
                self._initialized = True
            except Exception as e:
                print(f"[PlateOCREngine] Error initializing EasyOCR: {e}")
                self._reader = None
                self._initialized = True
        return self._reader

    def preprocess_plate_image(self, img_bgr: np.ndarray) -> np.ndarray:
        """
        Enhance plate image: grayscale, resize, bilateral filter, contrast enhancement.
        """
        if img_bgr is None or img_bgr.size == 0:
            return img_bgr

        # Resize if plate is too small
        h, w = img_bgr.shape[:2]
        if h < 60 or w < 160:
            scale = max(60 / max(h, 1), 160 / max(w, 1))
            img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        # Bilateral filter removes noise while keeping edges sharp
        filtered = cv2.bilateralFilter(gray, 11, 17, 17)
        # Contrast Limited Adaptive Histogram Equalization (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(filtered)

        return enhanced

    def extract_plate(self, vehicle_crop: np.ndarray) -> Tuple[Optional[str], Optional[str], float, Optional[str]]:
        """
        Extract plate from vehicle crop.
        Returns (raw_plate, normalized_plate, confidence, saved_plate_path).
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None, None, 0.0, None

        reader = self._get_reader()
        if reader is None:
            return None, None, 0.0, None

        vh, vw = vehicle_crop.shape[:2]
        # Focus on lower half of vehicle where plate is located
        lower_crop = vehicle_crop[int(vh * 0.45):, :]
        enhanced = self.preprocess_plate_image(lower_crop)

        try:
            results = reader.readtext(enhanced, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ')
            if not results:
                # Fallback to full crop
                results = reader.readtext(vehicle_crop, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ')

            if not results:
                return None, None, 0.0, None

            # Sort text elements by confidence and horizontal position
            results_sorted = sorted(results, key=lambda x: x[2], reverse=True)
            top_box, top_text, top_conf = results_sorted[0]

            raw_text = clean_ocr_text(top_text)
            normalized_plate, is_valid = normalize_indonesian_plate(raw_text)

            # Save plate crop to storage
            plate_filename = f"plate_{uuid.uuid4().hex[:8]}.jpg"
            save_path = str(settings.PLATES_PATH / plate_filename)
            cv2.imwrite(save_path, lower_crop)

            return raw_text, normalized_plate, float(top_conf), save_path
        except Exception as e:
            print(f"[PlateOCREngine] OCR inference error: {e}")
            return None, None, 0.0, None

plate_ocr_engine = PlateOCREngine()
