from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.db.session import get_db
from backend.app.db.base import CrossingEvent
from backend.app.engine.vision.pipeline_manager import pipeline_manager

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/summary")
def get_analytics_summary(camera_id: Optional[str] = None, db: Session = Depends(get_db)):
    today_start = datetime.combine(date.today(), datetime.min.time())
    query = db.query(CrossingEvent).filter(CrossingEvent.timestamp >= today_start)

    if camera_id:
        query = query.filter(CrossingEvent.camera_id == camera_id)

    events = query.all()

    total = len(events)
    total_in = sum(1 for e in events if e.direction == "IN")
    total_out = sum(1 for e in events if e.direction == "OUT")

    classes = {"car": 0, "motorcycle": 0, "person": 0, "bus": 0, "truck": 0, "bicycle": 0}
    for e in events:
        if e.object_class in classes:
            classes[e.object_class] += 1

    return {
        "today_total": total,
        "today_in": total_in,
        "today_out": total_out,
        "class_breakdown": classes
    }

@router.get("/hourly")
def get_hourly_analytics(camera_id: Optional[str] = None, db: Session = Depends(get_db)):
    today_start = datetime.combine(date.today(), datetime.min.time())
    query = db.query(CrossingEvent).filter(CrossingEvent.timestamp >= today_start)

    if camera_id:
        query = query.filter(CrossingEvent.camera_id == camera_id)

    events = query.all()

    # 24 hours buckets
    hourly_in = [0] * 24
    hourly_out = [0] * 24

    for e in events:
        hr = e.timestamp.hour
        if 0 <= hr < 24:
            if e.direction == "IN":
                hourly_in[hr] += 1
            else:
                hourly_out[hr] += 1

    labels = [f"{h:02d}:00" for h in range(24)]
    return {
        "labels": labels,
        "incoming": hourly_in,
        "outgoing": hourly_out
    }

@router.get("/recent")
def get_recent_events(limit: int = 15, db: Session = Depends(get_db)):
    events = db.query(CrossingEvent).order_by(CrossingEvent.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "camera_id": e.camera_id,
            "track_id": e.track_id,
            "object_class": e.object_class,
            "direction": e.direction,
            "snapshot_path": e.snapshot_path,
            "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else None
        }
        for e in events
    ]
