from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.db.session import get_db
from backend.app.db.base import VehicleLog, VehicleRegistry
from backend.app.engine.anpr.plate_parser import normalize_indonesian_plate, match_plate_fuzzy

router = APIRouter(prefix="/anpr", tags=["ANPR"])

class RegistryCreate(BaseModel):
    plate_number: str
    category: str = "WHITELIST"  # WHITELIST, BLACKLIST, VIP
    owner_name: Optional[str] = None
    notes: Optional[str] = None

@router.get("/logs")
def list_vehicle_logs(
    query: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    q = db.query(VehicleLog).order_by(VehicleLog.timestamp.desc())
    if category:
        q = q.filter(VehicleLog.access_status == category)

    all_logs = q.limit(200).all()

    results = []
    for item in all_logs:
        if query:
            if not match_plate_fuzzy(query, item.normalized_plate) and query.upper() not in item.plate_number.upper():
                continue

        results.append({
            "id": item.id,
            "camera_id": item.camera_id,
            "plate_number": item.plate_number,
            "normalized_plate": item.normalized_plate,
            "confidence_score": round(item.confidence_score * 100, 1),
            "access_status": item.access_status,
            "crop_image_path": item.crop_image_path,
            "timestamp": item.timestamp.strftime("%Y-%m-%d %H:%M:%S") if item.timestamp else None
        })
        if len(results) >= limit:
            break

    return results

@router.get("/registry")
def list_registry(db: Session = Depends(get_db)):
    items = db.query(VehicleRegistry).order_by(VehicleRegistry.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "plate_number": r.plate_number,
            "category": r.category,
            "owner_name": r.owner_name,
            "notes": r.notes,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None
        }
        for r in items
    ]

@router.post("/registry", status_code=status.HTTP_201_CREATED)
def add_to_registry(payload: RegistryCreate, db: Session = Depends(get_db)):
    normalized, _ = normalize_indonesian_plate(payload.plate_number)
    target_plate = normalized if normalized else payload.plate_number.upper()

    existing = db.query(VehicleRegistry).filter(VehicleRegistry.plate_number == target_plate).first()
    if existing:
        existing.category = payload.category
        existing.owner_name = payload.owner_name
        existing.notes = payload.notes
        db.commit()
        return {"message": "Vehicle registry updated", "id": existing.id}

    item = VehicleRegistry(
        plate_number=target_plate,
        category=payload.category,
        owner_name=payload.owner_name,
        notes=payload.notes
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"message": "Vehicle added to registry", "id": item.id}

@router.delete("/registry/{reg_id}")
def delete_from_registry(reg_id: str, db: Session = Depends(get_db)):
    item = db.query(VehicleRegistry).filter(VehicleRegistry.id == reg_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registry item not found")

    db.delete(item)
    db.commit()
    return {"message": "Registry item deleted"}
