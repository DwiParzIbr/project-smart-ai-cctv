import httpx
from typing import Optional
from pathlib import Path

class TelegramAlerter:
    def __init__(self, bot_token: Optional[str] = None, default_chat_id: Optional[str] = None):
        self.bot_token = bot_token
        self.default_chat_id = default_chat_id

    async def send_message(self, text: str, chat_id: Optional[str] = None) -> bool:
        cid = chat_id or self.default_chat_id
        if not self.bot_token or not cid:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                return res.status_code == 200
        except Exception as e:
            print(f"[Telegram] Failed to send message: {e}")
            return False

    async def send_photo(self, photo_path: str, caption: str, chat_id: Optional[str] = None) -> bool:
        cid = chat_id or self.default_chat_id
        if not self.bot_token or not cid:
            return False

        path = Path(photo_path)
        if not path.exists():
            return await self.send_message(caption, cid)

        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                with open(path, "rb") as f:
                    files = {"photo": (path.name, f, "image/jpeg")}
                    data = {"chat_id": cid, "caption": caption, "parse_mode": "Markdown"}
                    res = await client.post(url, data=data, files=files)
                    return res.status_code == 200
        except Exception as e:
            print(f"[Telegram] Failed to send photo: {e}")
            return False
