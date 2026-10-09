from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.db.session import get_db
from backend.app.db.base import CountingLine, Camera

router = APIRouter(prefix="/lines", tags=["Counting Lines"])

class LineCreate(BaseModel):
    camera_id: str
    line_name: str = "Counting Line"
    x1: float
    y1: float
    x2: float
    y2: float
    direction_arrow: str = "BIDIRECTIONAL"  # IN_ONLY, OUT_ONLY, BIDIRECTIONAL

@router.get("")
def list_lines(camera_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(CountingLine)
    if camera_id:
        query = query.filter(CountingLine.camera_id == camera_id)
    lines = query.all()
    return [
        {
            "id": l.id,
            "camera_id": l.camera_id,
            "line_name": l.line_name,
            "x1": round(l.x1, 4),
            "y1": round(l.y1, 4),
            "x2": round(l.x2, 4),
            "y2": round(l.y2, 4),
            "direction_arrow": l.direction_arrow,
            "is_active": l.is_active
        }
        for l in lines
    ]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_line(payload: LineCreate, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == payload.camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    line = CountingLine(
        camera_id=payload.camera_id,
        line_name=payload.line_name,
        x1=max(0.0, min(1.0, payload.x1)),
        y1=max(0.0, min(1.0, payload.y1)),
        x2=max(0.0, min(1.0, payload.x2)),
        y2=max(0.0, min(1.0, payload.y2)),
        direction_arrow=payload.direction_arrow
    )
    db.add(line)
    db.commit()
    db.refresh(line)
    return {"message": "Counting line created successfully", "id": line.id}

class LineUpdate(BaseModel):
    line_name: Optional[str] = None
    x1: Optional[float] = None
    y1: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
    direction_arrow: Optional[str] = None
    is_active: Optional[bool] = None

@router.put("/{line_id}")
def update_line(line_id: str, payload: LineUpdate, db: Session = Depends(get_db)):
    line = db.query(CountingLine).filter(CountingLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")

    if payload.line_name is not None:
        line.line_name = payload.line_name
    if payload.x1 is not None:
        line.x1 = max(0.0, min(1.0, payload.x1))
    if payload.y1 is not None:
        line.y1 = max(0.0, min(1.0, payload.y1))
    if payload.x2 is not None:
        line.x2 = max(0.0, min(1.0, payload.x2))
    if payload.y2 is not None:
        line.y2 = max(0.0, min(1.0, payload.y2))
    if payload.direction_arrow is not None:
        line.direction_arrow = payload.direction_arrow
    if payload.is_active is not None:
        line.is_active = payload.is_active

    db.commit()
    db.refresh(line)
    return {"message": "Counting line updated successfully", "id": line.id}

@router.delete("/{line_id}")
def delete_line(line_id: str, db: Session = Depends(get_db)):
    line = db.query(CountingLine).filter(CountingLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")

    db.delete(line)
    db.commit()
    return {"message": "Counting line deleted successfully"}
