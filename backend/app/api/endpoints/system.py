import psutil
import torch
import time
from datetime import datetime
from fastapi import APIRouter
from backend.app.engine.vision.pipeline_manager import pipeline_manager

router = APIRouter(prefix="/system", tags=["System"])

START_TIME = time.time()

@router.get("/metrics")
def get_system_metrics():
    # CPU & Memory
    cpu_percent = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    # GPU
    gpu_info = "CPU Only"
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_allocated = torch.cuda.memory_allocated(0) / (1024 ** 2)
        vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        gpu_info = f"{gpu_name} (VRAM: {vram_allocated:.0f}/{vram_total:.0f} MB)"
    elif torch.backends.mps.is_available():
        gpu_info = "Apple Silicon GPU (MPS Accelerated)"

    uptime_sec = int(time.time() - START_TIME)
    uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m {uptime_sec % 60}s"

    active_streams = sum(1 for w in pipeline_manager.workers.values() if w.running)

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": mem.percent,
        "ram_used_gb": round((mem.total - mem.available) / (1024 ** 3), 2),
        "ram_total_gb": round(mem.total / (1024 ** 3), 2),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024 ** 3), 1),
        "gpu_info": gpu_info,
        "uptime": uptime_str,
        "active_cameras": active_streams
    }


from pydantic import BaseModel
from typing import Optional
from backend.app.core.config import settings, save_env_settings
from backend.app.engine.alerts.dispatcher import alert_dispatcher
from backend.app.engine.vision.gemini_service import gemini_vision_service

class ServerSettingsUpdate(BaseModel):
    project_name: Optional[str] = None
    default_stream_fps: Optional[int] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    data_retention_days: Optional[int] = None
    detection_conf_threshold: Optional[float] = None
    anpr_conf_threshold: Optional[float] = None

@router.get("/settings")
def get_server_settings():
    return {
        "project_name": settings.PROJECT_NAME,
        "default_stream_fps": settings.DEFAULT_STREAM_FPS,
        "telegram_bot_token": settings.TELEGRAM_BOT_TOKEN,
        "telegram_chat_id": settings.TELEGRAM_CHAT_ID,
        "gemini_api_key": getattr(settings, "GEMINI_API_KEY", ""),
        "gemini_model": getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash"),
        "data_retention_days": settings.DATA_RETENTION_DAYS,
        "detection_conf_threshold": getattr(settings, "DETECTION_CONF_THRESHOLD", 0.35),
        "anpr_conf_threshold": getattr(settings, "ANPR_CONF_THRESHOLD", 0.30)
    }

@router.put("/settings")
def update_server_settings(payload: ServerSettingsUpdate):
    env_updates = {}

    if payload.project_name is not None:
        settings.PROJECT_NAME = payload.project_name
        env_updates["PROJECT_NAME"] = payload.project_name
    if payload.default_stream_fps is not None:
        settings.DEFAULT_STREAM_FPS = payload.default_stream_fps
        env_updates["DEFAULT_STREAM_FPS"] = payload.default_stream_fps
    if payload.telegram_bot_token is not None:
        settings.TELEGRAM_BOT_TOKEN = payload.telegram_bot_token
        alert_dispatcher.telegram.bot_token = payload.telegram_bot_token
        env_updates["TELEGRAM_BOT_TOKEN"] = payload.telegram_bot_token
    if payload.telegram_chat_id is not None:
        settings.TELEGRAM_CHAT_ID = payload.telegram_chat_id
        alert_dispatcher.telegram.default_chat_id = payload.telegram_chat_id
        env_updates["TELEGRAM_CHAT_ID"] = payload.telegram_chat_id
    if payload.gemini_api_key is not None:
        settings.GEMINI_API_KEY = payload.gemini_api_key
        env_updates["GEMINI_API_KEY"] = payload.gemini_api_key
    if payload.gemini_model is not None:
        settings.GEMINI_MODEL = payload.gemini_model
        env_updates["GEMINI_MODEL"] = payload.gemini_model
    if payload.data_retention_days is not None:
        settings.DATA_RETENTION_DAYS = payload.data_retention_days
        env_updates["DATA_RETENTION_DAYS"] = payload.data_retention_days
    if payload.detection_conf_threshold is not None:
        settings.DETECTION_CONF_THRESHOLD = payload.detection_conf_threshold
        env_updates["DETECTION_CONF_THRESHOLD"] = payload.detection_conf_threshold
    if payload.anpr_conf_threshold is not None:
        settings.ANPR_CONF_THRESHOLD = payload.anpr_conf_threshold
        env_updates["ANPR_CONF_THRESHOLD"] = payload.anpr_conf_threshold

    if env_updates:
        try:
            save_env_settings(env_updates)
        except Exception as e:
            print(f"[Settings] Error saving to .env: {e}")

    return {
        "message": "Pengaturan server berhasil diperbarui dan disimpan secara permanen",
        "settings": get_server_settings()
    }

@router.post("/test-telegram")
async def test_telegram_connection():
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return {"success": False, "message": "Bot Token atau Chat ID Telegram belum diatur."}
    
    success = await alert_dispatcher.telegram.send_message(
        "🔔 *Tes Notifikasi Smart Vision AI CCTV*\nKoneksi bot Telegram berhasil terhubung ke server surveillance edge!"
    )
    if success:
        return {"success": True, "message": "Pesan tes berhasil dikirim ke Telegram!"}
    else:
        return {"success": False, "message": "Gagal mengirim pesan. Pastikan Token Bot dan Chat ID valid."}

@router.post("/test-gemini")
async def test_gemini_connection(payload: Optional[dict] = None):
    api_key = payload.get("api_key") if payload else None
    model = payload.get("model") if payload else None
    result = await gemini_vision_service.test_connection(api_key=api_key, model=model)
    return result

@router.post("/restart-streams")
def restart_streams():
    pipeline_manager.sync_cameras()
    return {"message": "Pipeline worker kamera berhasil dimuat ulang."}

