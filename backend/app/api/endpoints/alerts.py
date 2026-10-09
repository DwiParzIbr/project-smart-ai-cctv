from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.db.session import get_db
from backend.app.db.base import AlertHistory, AlertRule
from backend.app.engine.alerts.dispatcher import alert_dispatcher

router = APIRouter(prefix="/alerts", tags=["Alerts"])

class AlertRuleCreate(BaseModel):
    rule_type: str = "BLACKLIST_MATCH"
    threshold_value: Optional[int] = 0
    channels: Optional[List[str]] = ["web", "telegram"]
    telegram_chat_id: Optional[str] = None
    webhook_url: Optional[str] = None
    is_active: Optional[bool] = True

class TestAlertPayload(BaseModel):
    rule_type: str = "TEST_ALERT"
    message: str = "Uji coba sistem notifikasi Smart Vision AI CCTV"

@router.get("/history")
def list_alert_history(limit: int = 50, db: Session = Depends(get_db)):
    alerts = db.query(AlertHistory).order_by(AlertHistory.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": a.id,
            "rule_type": a.rule_type,
            "message": a.message,
            "camera_id": a.camera_id,
            "snapshot_path": a.snapshot_path,
            "timestamp": a.timestamp.strftime("%Y-%m-%d %H:%M:%S") if a.timestamp else None
        }
        for a in alerts
    ]

@router.get("/rules")
def list_alert_rules(db: Session = Depends(get_db)):
    rules = db.query(AlertRule).all()
    return [
        {
            "id": r.id,
            "rule_type": r.rule_type,
            "threshold_value": r.threshold_value,
            "channels": r.channels,
            "telegram_chat_id": r.telegram_chat_id,
            "webhook_url": r.webhook_url,
            "is_active": r.is_active
        }
        for r in rules
    ]

@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_alert_rule(payload: AlertRuleCreate, db: Session = Depends(get_db)):
    rule = AlertRule(
        rule_type=payload.rule_type,
        threshold_value=payload.threshold_value,
        channels=payload.channels,
        telegram_chat_id=payload.telegram_chat_id,
        webhook_url=payload.webhook_url,
        is_active=payload.is_active
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"message": "Alert rule created", "id": rule.id}

@router.post("/test")
async def trigger_test_alert(payload: TestAlertPayload):
    await alert_dispatcher.broadcast_alert(
        rule_type=payload.rule_type,
        message=payload.message
    )
    return {"message": "Test alert triggered successfully"}
