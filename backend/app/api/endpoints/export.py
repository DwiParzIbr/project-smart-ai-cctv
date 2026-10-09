import io
import pandas as pd
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.app.db.session import get_db
from backend.app.db.base import CrossingEvent, VehicleLog

router = APIRouter(prefix="/export", tags=["Export"])

@router.get("/excel")
def export_excel(db: Session = Depends(get_db)):
    events = db.query(CrossingEvent).order_by(CrossingEvent.timestamp.desc()).limit(1000).all()
    anpr_logs = db.query(VehicleLog).order_by(VehicleLog.timestamp.desc()).limit(1000).all()

    events_data = [{
        "Waktu": e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "",
        "ID Kamera": e.camera_id,
        "Track ID": e.track_id,
        "Objek": e.object_class,
        "Arah": e.direction
    } for e in events]

    anpr_data = [{
        "Waktu": v.timestamp.strftime("%Y-%m-%d %H:%M:%S") if v.timestamp else "",
        "ID Kamera": v.camera_id,
        "Plat Terbaca": v.plate_number,
        "Plat Ternormalisasi": v.normalized_plate,
        "Akurasi (%)": round(v.confidence_score * 100, 1),
        "Status Akses": v.access_status
    } for v in anpr_logs]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_events = pd.DataFrame(events_data)
        df_anpr = pd.DataFrame(anpr_data)
        df_events.to_excel(writer, sheet_name='Line Crossing', index=False)
        df_anpr.to_excel(writer, sheet_name='ANPR Logs', index=False)

    output.seek(0)
    filename = f"cctv_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/pdf")
def export_pdf(db: Session = Depends(get_db)):
    events_count = db.query(CrossingEvent).count()
    anpr_count = db.query(VehicleLog).count()
    recent_anpr = db.query(VehicleLog).order_by(VehicleLog.timestamp.desc()).limit(10).all()

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 750, "LAPORAN SURVEILLANCE SMART VISION AI CCTV")
    p.setFont("Helvetica", 10)
    p.drawString(50, 735, f"Dicetak pada: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    p.line(50, 725, 550, 725)

    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, 695, "Ringkasan Statistik Sistem:")
    p.setFont("Helvetica", 11)
    p.drawString(70, 675, f"• Total Kendaraan & Orang Melintas: {events_count}")
    p.drawString(70, 655, f"• Total Plat Nomor Terekam (ANPR): {anpr_count}")

    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, 615, "10 Deteksi Plat Terakhir:")
    
    y = 590
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Waktu")
    p.drawString(180, y, "Plat Nomor")
    p.drawString(300, y, "Status Akses")
    p.drawString(420, y, "Akurasi")
    p.line(50, y - 5, 550, y - 5)
    
    p.setFont("Helvetica", 9)
    y -= 20
    for item in recent_anpr:
        t_str = item.timestamp.strftime("%Y-%m-%d %H:%M") if item.timestamp else "-"
        p.drawString(50, y, t_str)
        p.drawString(180, y, item.normalized_plate)
        p.drawString(300, y, item.access_status)
        p.drawString(420, y, f"{round(item.confidence_score * 100, 1)}%")
        y -= 18

    p.showPage()
    p.save()
    buffer.seek(0)

    filename = f"cctv_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
