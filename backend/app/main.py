import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.core.config import settings, FRONTEND_DIR
from backend.app.db.session import engine, SessionLocal
from backend.app.db.base import Base, Camera, CountingLine, VehicleRegistry, AlertRule, User
from backend.app.engine.vision.pipeline_manager import pipeline_manager
from backend.app.core.auth import get_password_hash

from backend.app.api.endpoints.cameras import router as cameras_router
from backend.app.api.endpoints.lines import router as lines_router
from backend.app.api.endpoints.analytics import router as analytics_router
from backend.app.api.endpoints.anpr import router as anpr_router
from backend.app.api.endpoints.alerts import router as alerts_router
from backend.app.api.endpoints.clips import router as clips_router
from backend.app.api.endpoints.auth import router as auth_router
from backend.app.api.endpoints.audit import router as audit_router
from backend.app.api.endpoints.storage import router as storage_router
from backend.app.api.endpoints.export import router as export_router
from backend.app.api.endpoints.system import router as system_router
from backend.app.api.endpoints.ai_vision import router as ai_vision_router
from backend.app.api.websocket import router as ws_router

def seed_initial_demo_data():
    """Seed initial camera, counting line, and blacklist for instant testability."""
    db = SessionLocal()
    try:
        # 1. Seed Camera if empty
        if db.query(Camera).count() == 0:
            cam = Camera(
                name="CAM 01 - Gerbang Utama & Jalur Masuk",
                source_type="SYNTHETIC",
                source_url="demo",
                assigned_model="yolo11n",
                target_classes=["person", "car", "motorcycle", "bus", "truck", "bicycle"],
                fps_limit=25
            )
            db.add(cam)
            db.commit()
            db.refresh(cam)

            # 2. Add default virtual counting line across the road
            line = CountingLine(
                camera_id=cam.id,
                line_name="Garis Gerbang Utama",
                x1=0.15,
                y1=0.60,
                x2=0.85,
                y2=0.60,
                direction_arrow="BIDIRECTIONAL"
            )
            db.add(line)
            db.commit()
            print(f"[Seed] Created demo camera: {cam.id} with line {line.id}")

        # 3. Seed Blacklist & VIP vehicles
        if db.query(VehicleRegistry).count() == 0:
            reg1 = VehicleRegistry(
                plate_number="B 1234 CD",
                category="BLACKLIST",
                owner_name="Target Operasi / Suspicious Vehicle",
                notes="Mobil dilarang masuk area gerbang utama"
            )
            reg2 = VehicleRegistry(
                plate_number="D 9981 XY",
                category="WHITELIST",
                owner_name="Staff Direksi PT Utama",
                notes="Akses 24 Jam"
            )
            db.add_all([reg1, reg2])
            db.commit()
            print("[Seed] Created demo vehicle registry items")

        # 4. Seed Alert Rule
        if db.query(AlertRule).count() == 0:
            rule = AlertRule(
                rule_type="BLACKLIST_MATCH",
                channels=["web", "telegram"],
                is_active=True
            )
            db.add(rule)
            db.commit()
            print("[Seed] Created default alert rule")

        # 5. Seed Default Multi-Level Users (RBAC)
        if db.query(User).count() == 0:
            u_admin = User(username="admin", password_hash=get_password_hash("admin123"), full_name="Super Administrator", role="ADMIN")
            u_satpam = User(username="satpam", password_hash=get_password_hash("satpam123"), full_name="Petugas Satpam / Operator", role="OPERATOR")
            u_auditor = User(username="auditor", password_hash=get_password_hash("auditor123"), full_name="Auditor & Keuangan", role="AUDITOR")
            db.add_all([u_admin, u_satpam, u_auditor])
            db.commit()
            print("[Seed] Created default users: admin, satpam, auditor")

    except Exception as e:
        print(f"[Seed] Error seeding data: {e}")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[Server] Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    seed_initial_demo_data()

    print("[Server] Starting Vision Pipeline Manager...")
    pipeline_manager.sync_cameras()
    yield
    # Shutdown
    print("[Server] Stopping Vision Pipeline...")
    pipeline_manager.stop_all()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Full-Stack Web CCTV Surveillance with YOLOv11, ByteTrack, Virtual Counting Line & ANPR",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(cameras_router, prefix="/api")
app.include_router(lines_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(anpr_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(clips_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(storage_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(ai_vision_router, prefix="/api")
app.include_router(ws_router)

# Mount Storage for snapshots, plates, and clips
app.mount("/storage/snapshots", StaticFiles(directory=str(settings.SNAPSHOTS_PATH)), name="snapshots")
app.mount("/storage/plates", StaticFiles(directory=str(settings.PLATES_PATH)), name="plates")
app.mount("/storage/clips", StaticFiles(directory=str(settings.CLIPS_PATH)), name="clips")

# Mount Static Frontend
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

@app.middleware("http")
async def add_cache_control_header(request, call_next):
    response = await call_next(request)
    if request.url.path.endswith(".js") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return {"message": "Smart Vision AI CCTV Backend Running. Please build frontend."}
