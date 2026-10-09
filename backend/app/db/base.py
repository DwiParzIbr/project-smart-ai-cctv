import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.db.session import Base

def generate_uuid():
    return str(uuid.uuid4())

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    source_type = Column(String(20), nullable=False, default="RTSP")  # RTSP, HLS, WEBCAM, FILE
    source_url = Column(Text, nullable=False)
    assigned_model = Column(String(50), default="yolo11n")
    target_classes = Column(JSON, default=lambda: ["person", "car", "motorcycle", "bus", "truck", "bicycle"])
    status = Column(String(20), default="ONLINE")  # ONLINE, OFFLINE, RECONNECTING, DISABLED, AI_PAUSED
    fps_limit = Column(Integer, default=25)
    is_enabled = Column(Boolean, default=True)   # Stream ingestion toggle
    ai_enabled = Column(Boolean, default=True)   # AI inference toggle (efficiency mode)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lines = relationship("CountingLine", back_populates="camera", cascade="all, delete-orphan")
    crossing_events = relationship("CrossingEvent", back_populates="camera", cascade="all, delete-orphan")
    vehicle_logs = relationship("VehicleLog", back_populates="camera", cascade="all, delete-orphan")
    video_clips = relationship("VideoClip", back_populates="camera", cascade="all, delete-orphan")

class CountingLine(Base):
    __tablename__ = "counting_lines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    camera_id = Column(String(36), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    line_name = Column(String(50), default="Line 1")
    x1 = Column(Float, nullable=False)  # Normalized 0.0 - 1.0
    y1 = Column(Float, nullable=False)
    x2 = Column(Float, nullable=False)
    y2 = Column(Float, nullable=False)
    direction_arrow = Column(String(20), default="BIDIRECTIONAL")  # IN_ONLY, OUT_ONLY, BIDIRECTIONAL
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    camera = relationship("Camera", back_populates="lines")
    events = relationship("CrossingEvent", back_populates="line")

class CrossingEvent(Base):
    __tablename__ = "crossing_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    camera_id = Column(String(36), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    line_id = Column(String(36), ForeignKey("counting_lines.id", ondelete="SET NULL"), nullable=True)
    track_id = Column(Integer, nullable=False)
    object_class = Column(String(30), nullable=False)
    direction = Column(String(10), nullable=False)  # IN or OUT
    snapshot_path = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    camera = relationship("Camera", back_populates="crossing_events")
    line = relationship("CountingLine", back_populates="events")

class VehicleLog(Base):
    __tablename__ = "vehicle_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    camera_id = Column(String(36), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    plate_number = Column(String(20), nullable=False)
    normalized_plate = Column(String(20), nullable=False)
    confidence_score = Column(Float, nullable=False)
    access_status = Column(String(20), default="UNREGISTERED")  # WHITELIST, BLACKLIST, VIP, UNREGISTERED
    crop_image_path = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    camera = relationship("Camera", back_populates="vehicle_logs")

class VehicleRegistry(Base):
    __tablename__ = "vehicle_registry"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    plate_number = Column(String(20), unique=True, nullable=False)
    category = Column(String(20), nullable=False)  # WHITELIST, BLACKLIST, VIP
    owner_name = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    rule_type = Column(String(50), nullable=False)  # BLACKLIST_MATCH, UNKNOWN_VEHICLE, VOLUME_THRESHOLD
    threshold_value = Column(Integer, default=0)
    channels = Column(JSON, default=lambda: ["web", "telegram"])  # ["web", "telegram", "webhook"]
    telegram_chat_id = Column(String(50), nullable=True)
    webhook_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

class AlertHistory(Base):
    __tablename__ = "alert_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    rule_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    camera_id = Column(String(36), nullable=True)
    snapshot_path = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    full_name = Column(String(100), default="Administrator")
    role = Column(String(20), default="ADMIN")  # ADMIN, OPERATOR, AUDITOR
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class VideoClip(Base):
    __tablename__ = "video_clips"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    camera_id = Column(String(36), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)  # BLACKLIST_HIT, LINE_CROSS, MANUAL
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, default=datetime.utcnow)
    duration_sec = Column(Float, default=20.0)
    file_path = Column(Text, nullable=False)
    thumbnail_path = Column(Text, nullable=True)
    cloud_synced = Column(Boolean, default=False)
    cloud_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    camera = relationship("Camera", back_populates="video_clips")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), nullable=True)
    username = Column(String(50), nullable=False)
    action_type = Column(String(50), nullable=False)  # CREATE, UPDATE, DELETE, TOGGLE, EXPORT, ALARM_ACK, LOGIN
    entity_name = Column(String(50), nullable=False)  # CAMERA, VIRTUAL_LINE, SERVER_CONFIG, REGISTRY, ALARM
    entity_id = Column(String(50), nullable=True)
    ip_address = Column(String(45), nullable=True)
    description = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
