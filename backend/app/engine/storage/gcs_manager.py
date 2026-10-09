import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.db.base import VideoClip

logger = logging.getLogger("gcs_manager")

class GCSStorageManager:
    """
    Manages direct integration with Google Cloud Console Storage (GCS) Buckets
    for recording video clips, snapshots, and eliminating local disk footprint.
    """
    def __init__(self):
        self.total_synced = 0
        self.bytes_freed = 0

    @property
    def enabled(self) -> bool:
        return getattr(settings, "GCS_ENABLED", True)

    @property
    def bucket_name(self) -> str:
        return getattr(settings, "GCS_BUCKET_NAME", "").strip()

    @property
    def project_id(self) -> str:
        return getattr(settings, "GCS_PROJECT_ID", "").strip()

    @property
    def credentials_json(self) -> str:
        return getattr(settings, "GCS_CREDENTIALS_JSON", "").strip()

    @property
    def auto_delete_local(self) -> bool:
        return getattr(settings, "GCS_AUTO_DELETE_LOCAL", True)

    def is_configured(self) -> bool:
        return bool(self.bucket_name)

    def get_client(self, credentials_json: Optional[str] = None, project_id: Optional[str] = None):
        """
        Instantiate google.cloud.storage.Client with credentials if provided,
        or environment credentials / default gcloud credentials.
        """
        from google.cloud import storage
        from google.oauth2 import service_account

        creds_str = credentials_json if credentials_json is not None else self.credentials_json
        proj = project_id if project_id is not None else (self.project_id or None)

        if creds_str:
            # Check if it's a file path
            creds_path = Path(creds_str)
            if creds_path.is_file():
                creds = service_account.Credentials.from_service_account_file(str(creds_path))
                return storage.Client(credentials=creds, project=proj or creds.project_id)
            
            # Check if it's a JSON string
            try:
                info = json.loads(creds_str)
                if isinstance(info, dict) and "type" in info:
                    creds = service_account.Credentials.from_service_account_info(info)
                    return storage.Client(credentials=creds, project=proj or creds.project_id)
            except Exception as e:
                logger.warning(f"Failed to parse credentials JSON string: {e}")

        # Fallback to default credentials
        return storage.Client(project=proj)

    def test_connection(
        self,
        bucket_name: Optional[str] = None,
        project_id: Optional[str] = None,
        credentials_json: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify connection and read/write permissions to the specified GCS Bucket.
        """
        target_bucket = (bucket_name or self.bucket_name).strip()
        if not target_bucket:
            return {
                "success": False,
                "message": "Nama GCS Bucket belum ditentukan. Silakan isi nama bucket di form konfigurasi."
            }

        try:
            client = self.get_client(credentials_json=credentials_json, project_id=project_id)
            bucket = client.get_bucket(target_bucket)

            # Test write & delete temporary check blob
            test_blob_name = f"_healthcheck/ping_{int(datetime.now().timestamp())}.txt"
            blob = bucket.blob(test_blob_name)
            blob.upload_from_string("Smart CCTV surveillance probe OK", content_type="text/plain")
            blob.delete()

            return {
                "success": True,
                "message": f"Koneksi ke Google Cloud Storage Bucket '{target_bucket}' Berhasil! Akses Read & Write terverifikasi.",
                "bucket": target_bucket,
                "project_id": client.project
            }
        except Exception as e:
            error_str = str(e)
            logger.error(f"[GCS] Connection test failed: {error_str}")
            hint = ""
            if "403" in error_str or "Forbidden" in error_str:
                hint = " (Periksa peran IAM Service Account: butuh Storage Object Admin / Storage Admin)"
            elif "404" in error_str or "Not Found" in error_str:
                hint = f" (Bucket '{target_bucket}' tidak ditemukan di Google Cloud Console)"

            return {
                "success": False,
                "message": f"Gagal menghubungkan ke GCS Bucket: {error_str}{hint}",
                "error": error_str
            }

    def upload_file(
        self,
        local_path: str,
        blob_name: str,
        content_type: str = "video/mp4",
        make_public: bool = False
    ) -> Dict[str, Any]:
        """
        Uploads a local file to the configured GCS bucket.
        """
        if not self.is_configured():
            return {"success": False, "error": "GCS Bucket belum dikonfigurasi"}

        if not os.path.exists(local_path):
            return {"success": False, "error": f"Berkas lokal tidak ditemukan: {local_path}"}

        try:
            client = self.get_client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)

            blob.upload_from_filename(local_path, content_type=content_type)
            if make_public:
                try:
                    blob.make_public()
                except Exception:
                    pass

            cloud_url = f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
            file_size = os.path.getsize(local_path)
            self.total_synced += 1

            return {
                "success": True,
                "blob_name": blob_name,
                "cloud_url": cloud_url,
                "size_bytes": file_size
            }
        except Exception as e:
            logger.error(f"[GCS] Upload failed for {local_path} -> {blob_name}: {e}")
            return {"success": False, "error": str(e)}

    def generate_signed_url(self, blob_name: str, expiration_minutes: int = 120) -> Optional[str]:
        """
        Generate a signed URL for secure, temporary playback access from GCS.
        """
        if not self.is_configured():
            return None
        try:
            client = self.get_client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(blob_name)
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="GET"
            )
            return url
        except Exception as e:
            logger.warning(f"[GCS] Could not generate signed URL: {e}, falling back to direct URL")
            return f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"

    def upload_video_clip(
        self,
        clip_id: str,
        file_path: str,
        thumbnail_path: Optional[str] = None,
        auto_delete_local: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Uploads an event video clip to GCS, updates database metadata,
        and optionally deletes the local video file to free up local disk space.
        """
        if not self.is_configured():
            return {"success": False, "message": "GCS Bucket belum dikonfigurasi"}

        should_delete = auto_delete_local if auto_delete_local is not None else self.auto_delete_local
        filename = os.path.basename(file_path)
        blob_name = f"clips/{filename}"

        # 1. Upload video
        res = self.upload_file(file_path, blob_name, content_type="video/mp4")
        if not res.get("success"):
            return res

        cloud_url = res["cloud_url"]

        # 2. Upload thumbnail if provided
        thumb_cloud_url = None
        if thumbnail_path and os.path.exists(thumbnail_path):
            thumb_blob = f"clips/{os.path.basename(thumbnail_path)}"
            t_res = self.upload_file(thumbnail_path, thumb_blob, content_type="image/jpeg")
            if t_res.get("success"):
                thumb_cloud_url = t_res["cloud_url"]

        # 3. Update database
        freed_bytes = 0
        try:
            db = SessionLocal()
            clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
            if clip:
                clip.cloud_synced = True
                clip.cloud_url = cloud_url

                # If auto-delete local is active, remove local video file to save disk space
                if should_delete and os.path.exists(file_path):
                    freed_bytes = os.path.getsize(file_path)
                    try:
                        os.remove(file_path)
                        self.bytes_freed += freed_bytes
                        logger.info(f"[GCS] Local video file removed to save disk: {file_path} ({freed_bytes / (1024*1024):.2f} MB)")
                    except Exception as del_err:
                        logger.warning(f"[GCS] Could not delete local file: {del_err}")

                db.commit()
            db.close()
        except Exception as db_err:
            logger.error(f"[GCS] Database update error for clip {clip_id}: {db_err}")

        return {
            "success": True,
            "cloud_url": cloud_url,
            "thumbnail_url": thumb_cloud_url,
            "local_deleted": should_delete,
            "freed_bytes": freed_bytes
        }

    def sync_pending_clips(self, auto_delete_local: Optional[bool] = None) -> Dict[str, Any]:
        """
        Synchronizes all unsynced clips from SQLite database to GCS Bucket.
        """
        if not self.is_configured():
            return {
                "success": False,
                "message": "Google Cloud Storage Bucket belum dikonfigurasi. Silakan tentukan nama bucket di pengaturan."
            }

        should_delete = auto_delete_local if auto_delete_local is not None else self.auto_delete_local
        synced_count = 0
        total_freed = 0
        errors = []

        try:
            db = SessionLocal()
            clips = db.query(VideoClip).filter(VideoClip.cloud_synced == False).all()

            for c in clips:
                if os.path.exists(c.file_path):
                    res = self.upload_video_clip(
                        clip_id=c.id,
                        file_path=c.file_path,
                        thumbnail_path=c.thumbnail_path,
                        auto_delete_local=should_delete
                    )
                    if res.get("success"):
                        synced_count += 1
                        total_freed += res.get("freed_bytes", 0)
                    else:
                        errors.append(res.get("error", "Unknown error"))
            db.close()

            return {
                "success": True,
                "files_synced": synced_count,
                "freed_mb": round(total_freed / (1024 * 1024), 2),
                "message": f"Berhasil mengunggah {synced_count} klip video ke GCS Bucket '{self.bucket_name}'. Ruang lokal dihemat: {round(total_freed / (1024 * 1024), 2)} MB.",
                "errors": errors
            }
        except Exception as e:
            return {"success": False, "error": str(e), "files_synced": synced_count}

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": self.is_configured(),
            "bucket_name": self.bucket_name,
            "project_id": self.project_id,
            "has_credentials": bool(self.credentials_json),
            "auto_delete_local": self.auto_delete_local,
            "total_synced": self.total_synced,
            "freed_mb": round(self.bytes_freed / (1024 * 1024), 2),
            "storage_type": "GOOGLE_CLOUD_STORAGE"
        }

gcs_manager = GCSStorageManager()
