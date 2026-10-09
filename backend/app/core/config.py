import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
STORAGE_DIR = BASE_DIR / "storage"
MODELS_DIR = BASE_DIR / "models"
FRONTEND_DIR = BASE_DIR / "frontend"

os.environ["YOLO_CONFIG_DIR"] = str(STORAGE_DIR / "ultralytics")
os.environ["TORCH_HOME"] = str(STORAGE_DIR / "torch")

class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Vision AI CCTV Surveillance"
    API_V1_STR: str = "/api"
    SECRET_KEY: str = "smart-ai-cctv-surveillance-super-secret-key-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/smart_cctv.db"

    # Storage paths
    STORAGE_PATH: Path = STORAGE_DIR
    SNAPSHOTS_PATH: Path = STORAGE_DIR / "snapshots"
    PLATES_PATH: Path = STORAGE_DIR / "plates"
    EXPORTS_PATH: Path = STORAGE_DIR / "exports"
    CLIPS_PATH: Path = STORAGE_DIR / "clips"
    MODELS_PATH: Path = MODELS_DIR

    # Video stream settings
    DEFAULT_STREAM_FPS: int = 25
    FRAME_WIDTH: int = 1280
    FRAME_HEIGHT: int = 720
    MAX_QUEUE_SIZE: int = 5

    # Telegram defaults
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Google Gemini AI settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"

    # Google Cloud Console Storage (GCS)
    GCS_ENABLED: bool = True
    GCS_BUCKET_NAME: str = ""
    GCS_PROJECT_ID: str = ""
    GCS_CREDENTIALS_JSON: str = ""
    GCS_AUTO_DELETE_LOCAL: bool = True

    # Retention
    DATA_RETENTION_DAYS: int = 30

    # Detection & AI thresholds
    DETECTION_CONF_THRESHOLD: float = 0.35
    ANPR_CONF_THRESHOLD: float = 0.30

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()

def save_env_settings(updates: dict):
    """Safely update key-values in .env file and in-memory settings."""
    env_file = BASE_DIR / ".env"
    lines = []
    existing_keys = set()
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in line_stripped:
            k, v = line_stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                new_val = str(updates[k])
                # Quote if string with spaces or special chars
                if " " in new_val or not new_val.isalnum():
                    new_lines.append(f'{k}="{new_val}"\n')
                else:
                    new_lines.append(f'{k}={new_val}\n')
                existing_keys.add(k)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    for k, val in updates.items():
        if k not in existing_keys:
            new_val = str(val)
            if " " in new_val or not new_val.isalnum():
                new_lines.append(f'{k}="{new_val}"\n')
            else:
                new_lines.append(f'{k}={new_val}\n')

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

# Ensure directories exist
for p in [settings.SNAPSHOTS_PATH, settings.PLATES_PATH, settings.EXPORTS_PATH, settings.CLIPS_PATH, settings.MODELS_PATH]:
    p.mkdir(parents=True, exist_ok=True)

