import os
from datetime import datetime, date, timedelta
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.db.session import get_db
from backend.app.db.base import VideoClip, Camera
from backend.app.core.config import settings
from backend.app.engine.vision.pipeline_manager import pipeline_manager
from backend.app.engine.vms.clipper import clip_recorder

router = APIRouter(prefix="/clips", tags=["Video Clips & VMS"])

@router.get("")
def list_clips(
    camera_id: Optional[str] = None,
    event_type: Optional[str] = None,
    date_str: Optional[str] = None,  # YYYY-MM-DD
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(VideoClip).order_by(VideoClip.created_at.desc())
    if camera_id:
        query = query.filter(VideoClip.camera_id == camera_id)
    if event_type:
        query = query.filter(VideoClip.event_type == event_type)
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start = datetime.combine(target_date, datetime.min.time())
            end = datetime.combine(target_date, datetime.max.time())
            query = query.filter(VideoClip.start_time >= start, VideoClip.start_time <= end)
        except ValueError:
            pass

    clips = query.limit(limit).all()
    results = []
    for c in clips:
        cam = db.query(Camera).filter(Camera.id == c.camera_id).first()
        results.append({
            "id": c.id,
            "camera_id": c.camera_id,
            "camera_name": cam.name if cam else "Kamera Tidak Dikenal",
            "event_type": c.event_type,
            "start_time": c.start_time.isoformat() if c.start_time else None,
            "end_time": c.end_time.isoformat() if c.end_time else None,
            "duration_sec": c.duration_sec,
            "file_url": f"/api/clips/{c.id}/stream",
            "thumbnail_url": f"/storage/clips/{Path(c.thumbnail_path).name}" if c.thumbnail_path and Path(c.thumbnail_path).exists() else None,
            "cloud_synced": c.cloud_synced,
            "created_at": c.created_at.isoformat() if c.created_at else None
        })
    return results

@router.get("/timeline")
def get_timeline_events(
    camera_id: Optional[str] = None,
    date_str: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Returns 24-hour timeline markers formatted with minutes from midnight (0 - 1440)
    for interactive timeline scrubber rendering.
    """
    target_date = date.today()
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    query = db.query(VideoClip).filter(VideoClip.start_time >= start, VideoClip.start_time <= end)
    if camera_id:
        query = query.filter(VideoClip.camera_id == camera_id)

    clips = query.order_by(VideoClip.start_time.asc()).all()
    markers = []
    for c in clips:
        # Calculate minutes from 00:00
        delta = c.start_time - start
        minutes = delta.total_seconds() / 60.0
        markers.append({
            "id": c.id,
            "camera_id": c.camera_id,
            "event_type": c.event_type,
            "time_str": c.start_time.strftime("%H:%M:%S"),
            "minutes": round(minutes, 2),
            "duration_sec": c.duration_sec,
            "color": "#ef4444" if "BLACKLIST" in c.event_type else "#38bdf8"
        })
    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "total_clips": len(markers),
        "markers": markers
    }

from fastapi.responses import FileResponse, RedirectResponse

@router.get("/{clip_id}/stream")
def stream_clip_video(clip_id: str, db: Session = Depends(get_db)):
    clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Video clip not found")

    # If file was uploaded to Google Cloud Storage and local copy was removed:
    if clip.cloud_synced and clip.cloud_url and (not os.path.exists(clip.file_path)):
        return RedirectResponse(url=clip.cloud_url)

    if not os.path.exists(clip.file_path):
        if clip.cloud_url:
            return RedirectResponse(url=clip.cloud_url)
        raise HTTPException(status_code=404, detail="Video clip file not found")

    return FileResponse(
        clip.file_path,
        media_type="video/mp4",
        filename=os.path.basename(clip.file_path)
    )

@router.post("/trigger-manual")
def trigger_manual_clip(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    worker = pipeline_manager.get_worker(camera_id)
    if not worker or not worker.running:
        raise HTTPException(
            status_code=400,
            detail=f"Camera worker is not currently running (found={worker is not None}, running={worker.running if worker else False}, registered={list(pipeline_manager.workers.keys())})"
        )

    pre_frames = worker.rolling_buffer.get_pre_event_frames()
    clip_recorder.record_event_clip(
        camera_id=camera_id,
        event_type="MANUAL_TRIGGER",
        pre_frames=pre_frames,
        get_current_frame_fn=worker.reader.get_latest_frame,
        post_duration_sec=10.0,
        fps=worker.reader.fps_limit or 25
    )

    return {"message": "Manual video clipping initiated (10s pre + 10s post buffer)"}

@router.delete("/{clip_id}")
def delete_clip(clip_id: str, db: Session = Depends(get_db)):
    clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    # Delete files
    try:
        if os.path.exists(clip.file_path):
            os.remove(clip.file_path)
        if clip.thumbnail_path and os.path.exists(clip.thumbnail_path):
            os.remove(clip.thumbnail_path)
    except Exception as e:
        print(f"[Clips] File deletion error: {e}")

    db.delete(clip)
    db.commit()
    return {"message": "Clip deleted successfully"}
