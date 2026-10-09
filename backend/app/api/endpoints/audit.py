from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.db.session import get_db, SessionLocal
from backend.app.db.base import AuditLog

router = APIRouter(prefix="/audit", tags=["Audit Trail & Security Logs"])

class AuditLogCreate(BaseModel):
    username: str
    action_type: str
    entity_name: str
    entity_id: Optional[str] = None
    description: str

def log_audit_event(
    action_type: str,
    entity_name: str,
    description: str,
    entity_id: Optional[str] = None,
    username: str = "admin",
    ip_address: Optional[str] = None
):
    """Utility to quickly insert an audit log event from anywhere in the app."""
    try:
        db = SessionLocal()
        entry = AuditLog(
            username=username,
            action_type=action_type,
            entity_name=entity_name,
            entity_id=entity_id,
            ip_address=ip_address,
            description=description
        )
        db.add(entry)
        db.commit()
        db.close()
    except Exception as e:
        print(f"[AuditLog] Failed to record audit log: {e}")

@router.get("/logs")
def list_audit_logs(
    action_type: Optional[str] = None,
    entity_name: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if action_type:
        query = query.filter(AuditLog.action_type == action_type)
    if entity_name:
        query = query.filter(AuditLog.entity_name == entity_name)

    logs = query.limit(limit).all()
    return [{
        "id": l.id,
        "username": l.username,
        "action_type": l.action_type,
        "entity_name": l.entity_name,
        "entity_id": l.entity_id,
        "ip_address": l.ip_address,
        "description": l.description,
        "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else None
    } for l in logs]

@router.post("/logs")
def add_audit_log(payload: AuditLogCreate, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    entry = AuditLog(
        username=payload.username,
        action_type=payload.action_type,
        entity_name=payload.entity_name,
        entity_id=payload.entity_id,
        ip_address=client_ip,
        description=payload.description
    )
    db.add(entry)
    db.commit()
    return {"message": "Audit log saved", "id": entry.id}
