import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.db.session import get_db
from backend.app.db.base import Camera
from backend.app.engine.vision.pipeline_manager import pipeline_manager

router = APIRouter(prefix="/cameras", tags=["Cameras"])

class CameraCreate(BaseModel):
    name: str
    source_type: str = "RTSP"  # RTSP, HLS, SYNTHETIC, 0
    source_url: str
    assigned_model: Optional[str] = "yolo11n"
    target_classes: Optional[List[str]] = ["person", "car", "motorcycle", "bus", "truck"]
    fps_limit: Optional[int] = 15

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    assigned_model: Optional[str] = None
    target_classes: Optional[List[str]] = None
    fps_limit: Optional[int] = None

@router.get("")
def list_cameras(db: Session = Depends(get_db)):
    # Prioritize real cameras (HLS/RTSP) at the top of the dashboard over synthetic demos
    cameras = db.query(Camera).order_by(
        (Camera.source_type == 'SYNTHETIC').asc(),
        Camera.created_at.desc()
    ).all()
    results = []
    for c in cameras:
        worker = pipeline_manager.get_worker(c.id)
        is_active = worker is not None and worker.running
        fps = worker.reader.fps_measured if worker else 0.0
        is_en = getattr(c, 'is_enabled', True)
        if is_en is None: is_en = True
        ai_en = getattr(c, 'ai_enabled', True)
        if ai_en is None: ai_en = True

        if not is_en:
            cam_status = "DISABLED"
        elif not ai_en:
            cam_status = "AI_PAUSED"
        else:
            cam_status = "ONLINE" if is_active else "OFFLINE"

        results.append({
            "id": c.id,
            "name": c.name,
            "source_type": c.source_type,
                "source_url": c.source_url,
                "assigned_model": c.assigned_model,
                "target_classes": c.target_classes,
                "status": cam_status,
                "is_enabled": is_en,
                "ai_enabled": ai_en,
                "fps_limit": c.fps_limit,
                "current_fps": round(fps, 1),
                "created_at": c.created_at.isoformat() if c.created_at else None
            })
    return results

@router.post("", status_code=status.HTTP_201_CREATED)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    cam = Camera(
        name=payload.name,
        source_type=payload.source_type,
        source_url=payload.source_url,
        assigned_model=payload.assigned_model,
        target_classes=payload.target_classes,
        fps_limit=payload.fps_limit,
        is_enabled=True,
        ai_enabled=True
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)

    # Sync worker
    pipeline_manager.sync_cameras()
    return {"message": "Camera registered successfully", "id": cam.id}

@router.get("/{camera_id}")
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    worker = pipeline_manager.get_worker(cam.id)
    is_active = worker is not None and worker.running
    fps = worker.reader.fps_measured if worker else 0.0

    is_en = getattr(cam, 'is_enabled', True)
    if is_en is None: is_en = True
    ai_en = getattr(cam, 'ai_enabled', True)
    if ai_en is None: ai_en = True

    if not is_en:
        cam_status = "DISABLED"
    elif not ai_en:
        cam_status = "AI_PAUSED"
    else:
        cam_status = "ONLINE" if is_active else "OFFLINE"

    return {
        "id": cam.id,
        "name": cam.name,
        "source_type": cam.source_type,
        "source_url": cam.source_url,
        "assigned_model": cam.assigned_model,
        "target_classes": cam.target_classes,
        "status": cam_status,
        "is_enabled": is_en,
        "ai_enabled": ai_en,
        "fps_limit": cam.fps_limit,
        "current_fps": round(fps, 1),
        "created_at": cam.created_at.isoformat() if cam.created_at else None
    }

@router.put("/{camera_id}")
def update_camera(camera_id: str, payload: CameraUpdate, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    if payload.name is not None:
        cam.name = payload.name
    if payload.source_type is not None:
        cam.source_type = payload.source_type
    if payload.source_url is not None:
        cam.source_url = payload.source_url
    if payload.assigned_model is not None:
        cam.assigned_model = payload.assigned_model
    if payload.target_classes is not None:
        cam.target_classes = payload.target_classes
    if payload.fps_limit is not None:
        cam.fps_limit = payload.fps_limit

    db.commit()
    db.refresh(cam)
    pipeline_manager.sync_cameras()
    return {"message": "Camera updated successfully", "id": cam.id}

@router.patch("/{camera_id}/toggle-stream")
def toggle_camera_stream(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    cam.is_enabled = not getattr(cam, 'is_enabled', True)
    db.commit()
    db.refresh(cam)
    pipeline_manager.sync_cameras()
    return {"message": "Stream state toggled", "is_enabled": cam.is_enabled}

@router.patch("/{camera_id}/toggle-ai")
def toggle_camera_ai(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    cam.ai_enabled = not getattr(cam, 'ai_enabled', True)
    db.commit()
    db.refresh(cam)
    pipeline_manager.sync_cameras()
    return {"message": "AI inference state toggled", "ai_enabled": cam.ai_enabled}

@router.delete("/{camera_id}")
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    db.delete(cam)
    db.commit()
    pipeline_manager.sync_cameras()
    return {"message": "Camera deleted successfully"}

from fastapi import Request
import asyncio

@router.get("/{camera_id}/stream")
async def stream_camera(camera_id: str, request: Request, overlay: bool = True):
    worker = pipeline_manager.get_worker(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Camera worker is not active")

    async def mjpeg_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                w = pipeline_manager.get_worker(camera_id)
                if not w or not w.running:
                    break
                jpeg = w.get_latest_jpeg(overlay=overlay)
                if jpeg:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
                await asyncio.sleep(0.035)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
