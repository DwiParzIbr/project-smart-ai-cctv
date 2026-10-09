from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.app.core.config import settings, save_env_settings
from backend.app.engine.storage.sync_manager import storage_sync_manager
from backend.app.engine.storage.gcs_manager import gcs_manager

router = APIRouter(prefix="/storage", tags=["Storage & Cloud Sync"])

class GCSConfigRequest(BaseModel):
    bucket_name: str
    project_id: Optional[str] = ""
    credentials_json: Optional[str] = None  # File path or raw JSON
    auto_delete_local: Optional[bool] = True
    enabled: Optional[bool] = True

class GCSTestRequest(BaseModel):
    bucket_name: Optional[str] = None
    project_id: Optional[str] = None
    credentials_json: Optional[str] = None

@router.get("/status")
def get_storage_status():
    return storage_sync_manager.get_storage_status()

@router.get("/gcs-config")
def get_gcs_config():
    """Retrieve current Google Cloud Storage configuration (safe view)."""
    has_creds = bool(settings.GCS_CREDENTIALS_JSON)
    creds_preview = ""
    if has_creds:
        c = settings.GCS_CREDENTIALS_JSON.strip()
        if c.startswith("{"):
            creds_preview = "{ Service Account Key JSON terpasang }"
        else:
            creds_preview = c

    return {
        "enabled": getattr(settings, "GCS_ENABLED", True),
        "bucket_name": getattr(settings, "GCS_BUCKET_NAME", ""),
        "project_id": getattr(settings, "GCS_PROJECT_ID", ""),
        "has_credentials": has_creds,
        "credentials_preview": creds_preview,
        "auto_delete_local": getattr(settings, "GCS_AUTO_DELETE_LOCAL", True),
        "synced_count": gcs_manager.total_synced,
        "freed_mb": round(gcs_manager.bytes_freed / (1024 * 1024), 2)
    }

@router.post("/gcs-config")
def save_gcs_config(payload: GCSConfigRequest):
    """Save Google Cloud Storage settings to environment and active runtime."""
    updates = {
        "GCS_BUCKET_NAME": payload.bucket_name.strip(),
        "GCS_PROJECT_ID": (payload.project_id or "").strip(),
        "GCS_AUTO_DELETE_LOCAL": payload.auto_delete_local if payload.auto_delete_local is not None else True,
        "GCS_ENABLED": payload.enabled if payload.enabled is not None else True
    }

    if payload.credentials_json is not None and payload.credentials_json.strip():
        updates["GCS_CREDENTIALS_JSON"] = payload.credentials_json.strip()

    # Update in-memory settings
    for k, v in updates.items():
        setattr(settings, k, v)

    # Persist to .env
    save_env_settings(updates)

    return {
        "success": True,
        "message": f"Konfigurasi Google Cloud Storage Bucket '{payload.bucket_name}' berhasil disimpan!",
        "bucket_name": payload.bucket_name,
        "auto_delete_local": payload.auto_delete_local
    }

@router.post("/test-gcs")
def test_gcs_connection(payload: GCSTestRequest):
    """Test connectivity and write permissions to Google Cloud Storage bucket."""
    bucket = payload.bucket_name or settings.GCS_BUCKET_NAME
    project = payload.project_id if payload.project_id is not None else settings.GCS_PROJECT_ID
    creds = payload.credentials_json if (payload.credentials_json and payload.credentials_json.strip()) else settings.GCS_CREDENTIALS_JSON

    res = gcs_manager.test_connection(bucket_name=bucket, project_id=project, credentials_json=creds)
    return res

@router.post("/sync-now")
def trigger_sync_now():
    """Trigger synchronization of evidence and clips to configured target (GCS / NAS)."""
    return storage_sync_manager.sync_pending_files()

@router.post("/sync-to-gcs")
def trigger_sync_to_gcs():
    """Trigger explicit synchronization of video recordings to Google Cloud Storage."""
    return gcs_manager.sync_pending_clips(auto_delete_local=settings.GCS_AUTO_DELETE_LOCAL)
