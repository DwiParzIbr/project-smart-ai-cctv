import os
import cv2
import base64
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.engine.vision.pipeline_manager import pipeline_manager
from backend.app.engine.vision.gemini_service import gemini_vision_service, DEFAULT_FORENSIC_PROMPT

router = APIRouter(prefix="/ai", tags=["AI Vision"])

class GeminiAnalyzeRequest(BaseModel):
    camera_id: Optional[str] = None
    snapshot_path: Optional[str] = None
    image_b64: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None

class GeminiTestRequest(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None

@router.get("/status")
def get_ai_status():
    api_key = (settings.GEMINI_API_KEY or "").strip()
    return {
        "configured": bool(api_key),
        "key_preview": f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else ("Set" if api_key else "Not Set"),
        "model": getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")
    }

@router.post("/test-connection")
async def test_gemini_api(payload: Optional[GeminiTestRequest] = None):
    key = payload.api_key if payload and payload.api_key else None
    model = payload.model if payload and payload.model else None
    result = await gemini_vision_service.test_connection(api_key=key, model=model)
    return result

@router.post("/gemini-analyze")
async def analyze_with_gemini(payload: GeminiAnalyzeRequest):
    """
    Analyze image using Google Gemini Multimodal Vision.
    Source can be camera_id (captures live frame), snapshot_path, or image_b64.
    """
    image_bytes = None
    source_info = ""

    # 1. From camera live stream
    if payload.camera_id:
        worker = pipeline_manager.get_worker(payload.camera_id)
        if not worker:
            raise HTTPException(status_code=404, detail=f"Kamera dengan ID {payload.camera_id} tidak aktif atau tidak ditemukan.")
        # Get raw clean frame
        image_bytes = worker.get_latest_jpeg(overlay=False)
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Belum ada frame gambar yang dapat diambil dari kamera ini.")
        source_info = f"Live Frame ({worker.camera_name})"

    # 2. From snapshot path / URL
    elif payload.snapshot_path:
        clean_path = payload.snapshot_path
        # Remove query params or URL domain if passed as web URL
        if "?" in clean_path:
            clean_path = clean_path.split("?")[0]
        
        # Check standard storage paths
        file_candidate = None
        if clean_path.startswith("/storage/"):
            rel = clean_path.replace("/storage/", "")
            file_candidate = settings.STORAGE_PATH / rel
        elif os.path.isabs(clean_path):
            file_candidate = Path(clean_path)
        else:
            file_candidate = settings.STORAGE_PATH / clean_path

        if file_candidate and file_candidate.exists():
            with open(file_candidate, "rb") as f:
                image_bytes = f.read()
            source_info = f"Snapshot ({file_candidate.name})"
        else:
            raise HTTPException(status_code=404, detail=f"Berkas snapshot tidak ditemukan: {clean_path}")

    # 3. From base64 encoded image
    elif payload.image_b64:
        b64_data = payload.image_b64
        if "," in b64_data:
            b64_data = b64_data.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(b64_data)
            source_info = "Image Upload / Canvas Snapshot"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Format data Base64 tidak valid: {str(e)}")
    else:
        raise HTTPException(
            status_code=400,
            detail="Harus menyertakan salah satu sumber gambar: camera_id, snapshot_path, atau image_b64."
        )

    result = await gemini_vision_service.analyze_image(
        image_bytes=image_bytes,
        prompt=payload.prompt,
        model=payload.model
    )

    if not result.get("success"):
        return {
            "success": False,
            "message": result.get("message", "Gagal memproses analisis gambar."),
            "source": source_info
        }

    return {
        "success": True,
        "source": source_info,
        "model": result.get("model"),
        "timestamp": result.get("timestamp"),
        "analysis": result.get("analysis")
    }
