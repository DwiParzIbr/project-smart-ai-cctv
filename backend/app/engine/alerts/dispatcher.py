import httpx
from typing import Dict, Any, Optional
from backend.app.core.config import settings
from backend.app.engine.alerts.telegram_bot import TelegramAlerter
from backend.app.db.session import SessionLocal
from backend.app.db.base import AlertHistory, AlertRule

class AlertDispatcher:
    def __init__(self):
        self.telegram = TelegramAlerter(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            default_chat_id=settings.TELEGRAM_CHAT_ID
        )
        self.ws_broadcast_callback = None

    def set_ws_broadcast_callback(self, callback):
        self.ws_broadcast_callback = callback

    async def broadcast_alert(
        self,
        rule_type: str,
        message: str,
        camera_id: Optional[str] = None,
        snapshot_path: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        # 1. Save to Database AlertHistory
        try:
            db = SessionLocal()
            history = AlertHistory(
                rule_type=rule_type,
                message=message,
                camera_id=camera_id,
                snapshot_path=snapshot_path
            )
            db.add(history)

            # Check matching rules in DB
            rules = db.query(AlertRule).filter(
                AlertRule.rule_type == rule_type,
                AlertRule.is_active == True
            ).all()
            db.commit()
        except Exception as e:
            print(f"[AlertDispatcher] DB Error: {e}")
            rules = []
        finally:
            db.close()

        payload = {
            "type": "ALERT",
            "rule_type": rule_type,
            "message": message,
            "camera_id": camera_id,
            "snapshot_path": snapshot_path,
            "extra": extra_data or {}
        }

        # 2. Web Broadcast via WebSocket
        if self.ws_broadcast_callback:
            try:
                await self.ws_broadcast_callback(payload)
            except Exception as e:
                print(f"[AlertDispatcher] WebSocket Broadcast error: {e}")

        # 3. Process Rules for Telegram & Webhook
        for rule in rules:
            channels = rule.channels or ["web"]
            if "telegram" in channels:
                tg_chat_id = rule.telegram_chat_id or settings.TELEGRAM_CHAT_ID
                if snapshot_path:
                    caption = f"🚨 *SECURITY ALERT: {rule_type}*\n\n{message}"
                    await self.telegram.send_photo(snapshot_path, caption, tg_chat_id)
                else:
                    text = f"🚨 *SECURITY ALERT: {rule_type}*\n\n{message}"
                    await self.telegram.send_message(text, tg_chat_id)

            if "webhook" in channels and rule.webhook_url:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.post(rule.webhook_url, json=payload)
                except Exception as e:
                    print(f"[AlertDispatcher] Webhook error: {e}")

alert_dispatcher = AlertDispatcher()
