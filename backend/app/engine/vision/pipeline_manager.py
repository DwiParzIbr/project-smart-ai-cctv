import cv2
import numpy as np
import time
import uuid
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime, date
from pathlib import Path

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.db.base import Camera, CountingLine, CrossingEvent, VehicleLog, VehicleRegistry
from backend.app.engine.ingestion.stream_reader import VideoStreamReader
from backend.app.engine.vision.detector import VisionDetector
from backend.app.engine.analytics.vector_math import check_line_crossing
from backend.app.engine.anpr.ocr_engine import plate_ocr_engine
from backend.app.engine.anpr.plate_parser import match_plate_fuzzy
from backend.app.engine.alerts.dispatcher import alert_dispatcher
from backend.app.engine.vms.ring_buffer import RollingFrameBuffer
from backend.app.engine.vms.clipper import clip_recorder

class CameraPipelineWorker:
    def __init__(self, camera: Camera, detector: VisionDetector):
        self.camera_id = camera.id
        self.camera_name = camera.name
        self.source_type = camera.source_type
        self.source_url = camera.source_url
        self.target_classes = camera.target_classes or ["person", "car", "motorcycle", "bus", "truck", "bicycle"]
        self.detector = detector

        self.is_enabled = getattr(camera, 'is_enabled', True)
        if self.is_enabled is None:
            self.is_enabled = True
        self.ai_enabled = getattr(camera, 'ai_enabled', True)
        if self.ai_enabled is None:
            self.ai_enabled = True

        self.reader = VideoStreamReader(
            camera_id=self.camera_id,
            source_url=self.source_url,
            source_type=self.source_type,
            fps_limit=camera.fps_limit or 25
        )

        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # State
        self.latest_raw_jpeg: Optional[bytes] = None
        self.latest_annotated_frame: Optional[bytes] = None
        self.frame_lock = threading.Lock()
        
        # Pre-event rolling frame buffer (10 seconds)
        self.rolling_buffer = RollingFrameBuffer(max_seconds=10, fps=camera.fps_limit or 25)

        # Tracking state: track_id -> {'last_pos': (x, y), 'counted_lines': set(), 'class_name': str}
        self.active_tracks: Dict[int, Dict[str, Any]] = {}
        
        # In-memory stats for fast dashboard response
        self.stats = {
            "today_total": 0,
            "today_in": 0,
            "today_out": 0,
            "class_breakdown": {
                "person": 0,
                "car": 0,
                "motorcycle": 0,
                "bus": 0,
                "truck": 0,
                "bicycle": 0
            }
        }
        self._load_initial_stats()

    def _load_initial_stats(self):
        try:
            db = SessionLocal()
            today_start = datetime.combine(date.today(), datetime.min.time())
            events = db.query(CrossingEvent).filter(
                CrossingEvent.camera_id == self.camera_id,
                CrossingEvent.timestamp >= today_start
            ).all()

            for ev in events:
                self.stats["today_total"] += 1
                if ev.direction == "IN":
                    self.stats["today_in"] += 1
                elif ev.direction == "OUT":
                    self.stats["today_out"] += 1
                if ev.object_class in self.stats["class_breakdown"]:
                    self.stats["class_breakdown"][ev.object_class] += 1
            db.close()
        except Exception as e:
            print(f"[PipelineWorker] Error loading initial stats: {e}")

    def start(self):
        if self.running:
            return
        self.running = True
        self.reader.start()
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.reader.stop()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.thread = None

    def get_latest_jpeg(self, overlay: bool = True) -> Optional[bytes]:
        with self.frame_lock:
            if overlay:
                return self.latest_annotated_frame or self.latest_raw_jpeg
            return self.latest_raw_jpeg or self.latest_annotated_frame

    def _process_loop(self):
        while self.running:
            raw_frame = self.reader.get_latest_frame()
            if raw_frame is None:
                time.sleep(0.04)
                continue

            h, w = raw_frame.shape[:2]

            # 1. Append to rolling buffer for event clipping
            self.rolling_buffer.append(raw_frame)

            # 2. Encode clean raw JPEG
            ret_raw, raw_jpeg = cv2.imencode('.jpg', raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret_raw:
                with self.frame_lock:
                    self.latest_raw_jpeg = raw_jpeg.tobytes()

            # 3. Check if AI inference is paused (efficiency mode)
            if not self.ai_enabled:
                with self.frame_lock:
                    if ret_raw:
                        self.latest_annotated_frame = self.latest_raw_jpeg
                time.sleep(0.02)
                continue

            # 4. Detect and track objects
            conf_thresh = getattr(settings, 'DETECTION_CONF_THRESHOLD', 0.35)
            tracked_objects = self.detector.detect_and_track(
                raw_frame,
                target_classes=self.target_classes,
                conf_threshold=conf_thresh
            )

            # 5. Fetch active counting lines for this camera
            lines = self._get_camera_lines()

            # 6. Process line crossing
            self._evaluate_crossings(raw_frame, tracked_objects, lines, w, h)

            # 7. Render overlays (bounding boxes, lines, stats)
            annotated = self._draw_overlays(raw_frame, tracked_objects, lines, w, h)

            # 8. Compress to JPEG
            ret, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                with self.frame_lock:
                    self.latest_annotated_frame = jpeg.tobytes()

            time.sleep(0.001)

    def _get_camera_lines(self) -> List[CountingLine]:
        try:
            db = SessionLocal()
            lines = db.query(CountingLine).filter(
                CountingLine.camera_id == self.camera_id,
                CountingLine.is_active == True
            ).all()
            db.close()
            return lines
        except Exception:
            return []

    def _evaluate_crossings(self, frame, tracked_objects, lines, w, h):
        current_frame_track_ids = set()

        for obj in tracked_objects:
            tid = obj.get("track_id")
            if tid is None:
                continue

            current_frame_track_ids.add(tid)
            bx, by = obj["bottom_center"]
            curr_pos_norm = (bx / float(w), by / float(h))
            cls_name = obj["class_name"]

            if tid not in self.active_tracks:
                self.active_tracks[tid] = {
                    "last_pos": curr_pos_norm,
                    "counted_lines": set(),
                    "class_name": cls_name,
                    "first_seen": time.time()
                }
                continue

            track_info = self.active_tracks[tid]
            prev_pos_norm = track_info["last_pos"]

            # Evaluate each line
            for line in lines:
                line_key = line.id
                if line_key in track_info["counted_lines"]:
                    continue  # Zero double counting!

                direction = check_line_crossing(
                    prev_pos=prev_pos_norm,
                    curr_pos=curr_pos_norm,
                    line_start=(line.x1, line.y1),
                    line_end=(line.x2, line.y2),
                    direction_arrow=line.direction_arrow
                )

                if direction:
                    # Flag counted
                    track_info["counted_lines"].add(line_key)
                    self._on_crossing_event(frame, obj, line, direction, w, h)

            # Update position
            track_info["last_pos"] = curr_pos_norm

        # Clean old tracks
        now = time.time()
        to_del = [tid for tid, info in self.active_tracks.items() if now - info.get("first_seen", now) > 60 and tid not in current_frame_track_ids]
        for tid in to_del:
            del self.active_tracks[tid]

    def _on_crossing_event(self, frame, obj, line, direction, w, h):
        cls_name = obj["class_name"]
        
        # 1. Update stats
        self.stats["today_total"] += 1
        if direction == "IN":
            self.stats["today_in"] += 1
        else:
            self.stats["today_out"] += 1

        if cls_name in self.stats["class_breakdown"]:
            self.stats["class_breakdown"][cls_name] += 1

        # 2. Save snapshot
        snap_filename = f"snap_{self.camera_id[:6]}_{uuid.uuid4().hex[:6]}.jpg"
        snap_path = str(settings.SNAPSHOTS_PATH / snap_filename)
        cv2.imwrite(snap_path, frame)

        # 3. Save CrossingEvent to DB
        try:
            db = SessionLocal()
            event = CrossingEvent(
                camera_id=self.camera_id,
                line_id=line.id,
                track_id=obj.get("track_id", 0),
                object_class=cls_name,
                direction=direction,
                snapshot_path=snap_path
            )
            db.add(event)
            db.commit()
            db.close()
        except Exception as e:
            print(f"[PipelineWorker] DB Save Event Error: {e}")

        # 4. Trigger ANPR for vehicles
        if cls_name in ["car", "motorcycle", "bus", "truck"]:
            self._trigger_anpr(frame, obj, snap_path)

    def _trigger_anpr(self, frame, obj, snap_path):
        bbox = obj["bbox"]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 - x1 < 20 or y2 - y1 < 20:
            return

        vehicle_crop = frame[y1:y2, x1:x2]
        raw_plate, normalized_plate, conf, plate_crop_path = plate_ocr_engine.extract_plate(vehicle_crop)

        if normalized_plate:
            # Check Registry for Whitelist / Blacklist
            access_status = "UNREGISTERED"
            owner_name = None
            try:
                db = SessionLocal()
                reg_items = db.query(VehicleRegistry).all()
                for item in reg_items:
                    if match_plate_fuzzy(normalized_plate, item.plate_number):
                        access_status = item.category
                        owner_name = item.owner_name
                        break

                # Save VehicleLog
                vlog = VehicleLog(
                    camera_id=self.camera_id,
                    plate_number=raw_plate or normalized_plate,
                    normalized_plate=normalized_plate,
                    confidence_score=conf,
                    access_status=access_status,
                    crop_image_path=plate_crop_path
                )
                db.add(vlog)
                db.commit()
                db.close()
            except Exception as e:
                print(f"[PipelineWorker] ANPR DB Error: {e}")

            # Check Alert Trigger & Video Clip Recording
            if access_status == "BLACKLIST":
                msg = f"Kendaraan BLACKLIST terdeteksi: *{normalized_plate}* di kamera *{self.camera_name}* (Pemilik: {owner_name or 'Tidak Diketahui'})"
                
                # Trigger Event-based Video Clipping (10s pre-buffer + 10s post-buffer)
                pre_frames = self.rolling_buffer.get_pre_event_frames()
                clip_recorder.record_event_clip(
                    camera_id=self.camera_id,
                    event_type="BLACKLIST_HIT",
                    pre_frames=pre_frames,
                    get_current_frame_fn=self.reader.get_latest_frame,
                    post_duration_sec=10.0,
                    fps=self.reader.fps_limit or 25
                )

                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(alert_dispatcher.broadcast_alert(
                            rule_type="BLACKLIST_MATCH",
                            message=msg,
                            camera_id=self.camera_id,
                            snapshot_path=plate_crop_path or snap_path,
                            extra_data={"plate": normalized_plate, "status": access_status}
                        ))
                except Exception as e:
                    print(f"[PipelineWorker] Dispatcher alert error: {e}")

    def _draw_overlays(self, frame, tracked_objects, lines, w, h):
        annotated = frame.copy()

        # 1. Draw Counting Lines (Modern Surveillance Tripwire Aesthetic)
        for line in lines:
            p1 = (int(line.x1 * w), int(line.y1 * h))
            p2 = (int(line.x2 * w), int(line.y2 * h))
            
            # Subtle dark contrast under-line
            cv2.line(annotated, p1, p2, (15, 23, 42), 5, cv2.LINE_AA)
            # Crisp cyan tripwire line
            cv2.line(annotated, p1, p2, (0, 220, 255), 2, cv2.LINE_AA)
            
            # Clean endpoint rings
            cv2.circle(annotated, p1, 5, (0, 220, 255), -1, cv2.LINE_AA)
            cv2.circle(annotated, p1, 5, (15, 23, 42), 1, cv2.LINE_AA)
            cv2.circle(annotated, p2, 5, (0, 220, 255), -1, cv2.LINE_AA)
            cv2.circle(annotated, p2, 5, (15, 23, 42), 1, cv2.LINE_AA)
            
            # Direction icon & pill badge at midpoint
            mid_x, mid_y = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
            dir_str = "<-> DUA ARAH" if line.direction_arrow == "BIDIRECTIONAL" else ("-> MASUK" if line.direction_arrow == "IN_ONLY" else "<- KELUAR")
            label_text = f"{line.line_name} [{dir_str}]"
            
            (tw, th), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_DUPLEX, 0.40, 1)
            bx1 = max(5, mid_x - tw // 2 - 6)
            by1 = max(5, mid_y - th - 10)
            bx2 = min(w - 5, bx1 + tw + 12)
            by2 = min(h - 5, by1 + th + 8)
            
            # Dark pill background
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (15, 23, 42), -1)
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (0, 220, 255), 1, cv2.LINE_AA)
            cv2.putText(
                annotated,
                label_text,
                (bx1 + 6, by1 + th + 2),
                cv2.FONT_HERSHEY_DUPLEX, 0.40, (255, 255, 255), 1, cv2.LINE_AA
            )

        CLASS_STYLE = {
            "car": {"label": "Mobil", "color": (255, 191, 0)},
            "motorcycle": {"label": "Motor", "color": (255, 105, 180)},
            "person": {"label": "Orang", "color": (0, 255, 128)},
            "bus": {"label": "Bus", "color": (0, 165, 255)},
            "truck": {"label": "Truk", "color": (0, 0, 255)},
            "bicycle": {"label": "Sepeda", "color": (0, 255, 255)}
        }

        # 2. Draw Bounding Boxes and IDs
        for obj in tracked_objects:
            x1, y1, x2, y2 = [int(v) for v in obj["bbox"]]
            cls_name = obj["class_name"]
            tid = obj.get("track_id", "N/A")
            conf = obj["confidence"]

            style = CLASS_STYLE.get(cls_name, {"label": cls_name.capitalize(), "color": (200, 200, 200)})
            color = style["color"]
            label_text = f"#{tid} {style['label']} {conf:.2f}"

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            t_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)[0]
            cv2.rectangle(annotated, (x1, y1 - 20), (x1 + t_size[0] + 6, y1), color, -1)
            cv2.putText(annotated, label_text, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 1)

            # Draw bottom-center contact point
            bx, by = int(obj["bottom_center"][0]), int(obj["bottom_center"][1])
            cv2.circle(annotated, (bx, by), 4, (0, 0, 255), -1)

        # 3. Draw Detailed Stats HUD on top-left
        hud_bg_w = 340
        hud_bg_h = 105
        sub_img = annotated[10:10+hud_bg_h, 10:10+hud_bg_w]
        white_rect = np.zeros(sub_img.shape, dtype=np.uint8)
        res = cv2.addWeighted(sub_img, 0.35, white_rect, 0.65, 1.0)
        annotated[10:10+hud_bg_h, 10:10+hud_bg_w] = res

        b = self.stats["class_breakdown"]
        cv2.putText(annotated, f"TOTAL: {self.stats['today_total']}  (IN: {self.stats['today_in']} | OUT: {self.stats['today_out']})", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 2)
        cv2.putText(annotated, f"Mobil: {b.get('car', 0)} | Motor: {b.get('motorcycle', 0)} | Orang: {b.get('person', 0)}", (18, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        cv2.putText(annotated, f"Bus: {b.get('bus', 0)} | Truk: {b.get('truck', 0)} | Sepeda: {b.get('bicycle', 0)}", (18, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        cv2.putText(annotated, f"FPS: {self.reader.fps_measured:.1f}", (18, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 0), 1)

        return annotated


class PipelineManager:
    def __init__(self):
        self.workers: Dict[str, CameraPipelineWorker] = {}
        self.detector: Optional[VisionDetector] = None

    def initialize_detector(self):
        if self.detector is None:
            self.detector = VisionDetector()

    def sync_cameras(self):
        """Sync running workers with cameras in Database."""
        self.initialize_detector()
        try:
            db = SessionLocal()
            cameras = db.query(Camera).all()
            db_cam_ids = {c.id for c in cameras}

            # Stop deleted cameras
            for cid in list(self.workers.keys()):
                if cid not in db_cam_ids:
                    print(f"[PipelineManager] Stopping camera worker {cid}")
                    self.workers[cid].stop()
                    del self.workers[cid]

            # Start new cameras or restart edited cameras
            for cam in cameras:
                # If camera is disabled by user, stop worker if running
                if not getattr(cam, 'is_enabled', True):
                    if cam.id in self.workers:
                        print(f"[PipelineManager] Camera {cam.id} ({cam.name}) is disabled. Stopping worker.")
                        self.workers[cam.id].stop()
                        del self.workers[cam.id]
                    continue

                if cam.id not in self.workers:
                    print(f"[PipelineManager] Starting camera worker {cam.id} ({cam.name})")
                    worker = CameraPipelineWorker(cam, self.detector)
                    worker.start()
                    self.workers[cam.id] = worker
                else:
                    w = self.workers[cam.id]
                    # Update dynamic AI inference flag without restarting stream connection!
                    w.ai_enabled = getattr(cam, 'ai_enabled', True)
                    w.is_enabled = getattr(cam, 'is_enabled', True)

                    # Check if stream parameters were modified
                    if (w.source_url != cam.source_url or
                        w.source_type != cam.source_type or
                        w.target_classes != cam.target_classes or
                        w.reader.fps_limit != (cam.fps_limit or 25) or
                        w.camera_name != cam.name):
                        print(f"[PipelineManager] Camera {cam.id} updated. Restarting worker...")
                        w.stop()
                        new_worker = CameraPipelineWorker(cam, self.detector)
                        new_worker.start()
                        self.workers[cam.id] = new_worker
            db.close()
        except Exception as e:
            print(f"[PipelineManager] Error syncing cameras: {e}")

    def get_worker(self, camera_id: str) -> Optional[CameraPipelineWorker]:
        return self.workers.get(camera_id)

    def stop_all(self):
        for worker in self.workers.values():
            worker.stop()
        self.workers.clear()

pipeline_manager = PipelineManager()
