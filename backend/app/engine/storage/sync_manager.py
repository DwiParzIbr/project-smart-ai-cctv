import os
import shutil
import psutil
from typing import Dict, Any, Optional
from datetime import datetime

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.db.base import VideoClip
from backend.app.engine.storage.gcs_manager import gcs_manager

class StorageSyncManager:
    """
    Manages automated cloud and NAS storage synchronization
    for evidence snapshots and event video clips.
    Supports Google Cloud Storage Bucket and Local NAS backup.
    """
    def __init__(self):
        self.provider = "GOOGLE_CLOUD_STORAGE"
        self.is_syncing = False
        self.last_sync_time: Optional[datetime] = None
        self.synced_count = 0

    def get_storage_status(self) -> Dict[str, Any]:
        disk = psutil.disk_usage(str(settings.STORAGE_PATH))
        snapshots_count = len(list(settings.SNAPSHOTS_PATH.glob("*.jpg")))
        clips_count = len(list(settings.CLIPS_PATH.glob("*.mp4")))
        gcs_stat = gcs_manager.get_status()

        provider_label = f"GCS: gs://{gcs_manager.bucket_name}" if gcs_manager.is_configured() else "Google Cloud Storage (Belum Dikonfigurasi)"

        return {
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "used_gb": round(disk.used / (1024 ** 3), 2),
            "free_gb": round(disk.free / (1024 ** 3), 2),
            "used_percent": disk.percent,
            "snapshots_stored": snapshots_count,
            "clips_stored": clips_count,
            "cloud_provider": provider_label,
            "gcs_configured": gcs_manager.is_configured(),
            "gcs_bucket": gcs_manager.bucket_name,
            "gcs_auto_delete_local": gcs_manager.auto_delete_local,
            "is_syncing": self.is_syncing,
            "last_sync": self.last_sync_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_sync_time else "Belum Pernah",
            "total_synced": self.synced_count + gcs_stat["total_synced"],
            "gcs_freed_mb": gcs_stat["freed_mb"]
        }

    def sync_pending_files(self) -> Dict[str, Any]:
        """
        Synchronizes un-synced clips and snapshots to backup target.
        If Google Cloud Storage Bucket is configured, uploads directly to GCS.
        Otherwise falls back to local NAS backup archive.
        """
        self.is_syncing = True
        try:
            if gcs_manager.is_configured():
                res = gcs_manager.sync_pending_clips(auto_delete_local=settings.GCS_AUTO_DELETE_LOCAL)
                if res.get("success"):
                    self.synced_count += res.get("files_synced", 0)
                    self.last_sync_time = datetime.now()
                return res

            # Fallback to local NAS archive
            backup_dir = settings.STORAGE_PATH / "backup_archive"
            backup_dir.mkdir(parents=True, exist_ok=True)

            copied = 0
            db = SessionLocal()
            unsynced_clips = db.query(VideoClip).filter(VideoClip.cloud_synced == False).all()
            for clip in unsynced_clips:
                if os.path.exists(clip.file_path):
                    dest = backup_dir / os.path.basename(clip.file_path)
                    shutil.copy2(clip.file_path, str(dest))
                    clip.cloud_synced = True
                    clip.cloud_url = f"file://{dest}"
                    copied += 1
            db.commit()
            db.close()

            self.synced_count += copied
            self.last_sync_time = datetime.now()
            return {
                "success": True,
                "files_synced": copied,
                "message": f"Berhasil mencadangkan {copied} berkas video ke NAS lokal. (Tip: Konfigurasikan GCS Bucket untuk backup awan)"
            }
        except Exception as e:
            return {"success": False, "files_synced": 0, "error": str(e)}
        finally:
            self.is_syncing = False

storage_sync_manager = StorageSyncManager()
