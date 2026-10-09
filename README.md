# 📹 Smart Vision AI CCTV Surveillance Web Application

Sistem Surveillance Cerdas berbasis Web Standalone & Edge Server yang mengintegrasikan seluruh kapabilitas dari **Tahap 1, Tahap 2, Tahap 3, hingga Tahap 4**:
- **Multi-Source Ingestion Engine (Tahap 1)**: Mendukung RTSP (IP Camera Dahua/Hikvision/ONVIF), HLS (`.m3u8` CCTV publik), WebCam, dan Simulated Demo Feed.
- **AI Core Vision & Tracking (Tahap 1 & 2)**: Ultralytics YOLOv11 + ByteTrack MOT untuk deteksi simultan orang & kendaraan tanpa *double counting*.
- **Interactive Virtual Counting Line Studio (Tahap 2)**: Drag-and-drop kanvas HTML5 langsung di browser untuk mengatur garis penghitung, koordinat ter-normalisasi ($0.0 - 1.0$), dan arah perlintasan (IN/OUT) dengan matematika vektor *cross-product*.
- **Real-Time Traffic Analytics Dashboard (Tahap 2)**: Kartu metrik live, grafik tren arus per jam (*Hourly Traffic Flow*), diagram donat komposisi jenis kendaraan, dan feed log kejadian dengan foto snapshot.
- **Triggered ANPR & License Plate Recognition (Tahap 3)**: OCR plat nomor otomatis (target akurasi $\ge 95\%$) berbasis EasyOCR/PaddleOCR + normalizer regex plat Indonesia, pencarian plat dengan *Fuzzy Matching*, dan pengawasan daftar **Blacklist / Whitelist / VIP**.
- **Pusat Alerting & Notifikasi Darurat (Tahap 3)**: Notifikasi banner & audio sirine di web, bot Telegram otomatis, dan integrasi webhook gerbang.
- **Ekspor Laporan (Tahap 3)**: Unduh data log dan analitik dalam format **Excel (.xlsx)** dan **PDF**.
- **Akselerasi & Edge Ready (Tahap 4)**: Penjadwalan buffer video, auto-reconnect dengan exponential backoff, Dockerfile & `docker-compose.yml` (mendukung `nvidia-docker` GPU passthrough), dan pemantauan beban hardware (CPU, RAM, GPU, Disk).
- **Google Cloud Storage (GCS) Bucket**: Penyimpanan rekaman video kejadian langsung di cloud bucket (*Zero Local Disk footprint*).
- **Google Gemini Multimodal Vision Forensics**: Integrasi Gemini Flash untuk analisis situasional frame CCTV cerdas.
- **Vercel Web Client Ready**: Frontend dapat dideploy ke Vercel Cloud dan terhubung ke backend FastAPI lokal maupun remote.

---

## ☁️ Deployment ke Vercel

Frontend web aplikasi ini dapat dideploy ke **Vercel** dengan satu perintah:

```bash
# Deploy ke Vercel
npx vercel --prod
```

Setelah dideploy, buka URL Vercel Anda dan gunakan tombol **🌐 API Host** di sudut kanan atas untuk mengarahkan ke alamat server backend CCTV Anda (contoh: `http://localhost:8000` atau URL server publik / tunnel).

---

## 🚀 Panduan Menjalankan Aplikasi Secara Lokal

### 1. Prasyarat Sistem
- Python 3.10 / 3.11
- Node.js & npm (opsional, untuk Vercel CLI)
- macOS (Apple Silicon / Intel) atau Linux Ubuntu 20.04/22.04 LTS

### 2. Mengaktifkan Virtual Environment & Menjalankan Server
```bash
# Masuk ke direktori proyek
cd "/Users/dwifiparizzaibrahim/Documents/Project Smart AI CCTV"

# Salin file konfigurasi environment
cp .env.example .env

# Aktifkan virtual environment
source .venv/bin/activate

# Jalankan server aplikasi
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Membuka Antarmuka Web
Buka browser modern (Google Chrome / Safari / Edge / Firefox) dan akses:
```
http://localhost:8000
```

---

## 🎯 Panduan Fitur & Penggunaan

1. **Live Multi-View (`/`)**:
   - Tampilan grid tayangan CCTV langsung dengan overlay kotak deteksi (*bounding box*), Track ID unik, koordinat garis, dan indikator FPS.
   - Mendukung streaming HLS langsung (contoh CCTV publik Kota Bengkulu: Simpang Kominfo, Simpang SKIP Jl. Jati, Simpang SKIP S. Parman).
2. **Virtual Line Studio**:
   - Klik dan seret mouse pada tayangan video untuk menggambar garis penghitung.
   - Sistem otomatis mendeteksi arah perlintasan kendaraan dan menghitung volume lalu lintas real-time.
3. **Penyimpanan Google Cloud Storage (GCS) Bucket**:
   - Konfigurasikan nama GCS Bucket dan Service Account Key di tab Pengaturan Server.
   - Video kejadian otomatis tersimpan di bucket Google Cloud dan hard disk lokal tetap bersih.
4. **Forensik Google Gemini Multimodal**:
   - Klik tombol **✨ Gemini AI** pada kartu kamera atau snapshot untuk menganalisis pelanggaran lalu lintas dan kondisi cuaca/jalan secara otomatis.

---

## 📁 Struktur Direktori
```
Project Smart AI CCTV/
├── backend/
│   ├── app/
│   │   ├── api/endpoints/    # REST API: cameras, lines, analytics, anpr, alerts, storage, ai_vision
│   │   ├── core/             # Konfigurasi & settings
│   │   ├── db/               # SQLite database & models
│   │   ├── engine/
│   │   │   ├── ingestion/    # VideoStreamReader (RTSP, HLS, Demo)
│   │   │   ├── vision/       # YOLOv11 + ByteTrack & PipelineManager
│   │   │   ├── analytics/    # Vector Math (Line Crossing)
│   │   │   ├── anpr/         # EasyOCR Engine & Indonesian Plate Regex
│   │   │   ├── alerts/       # Dispatcher notifikasi
│   │   │   ├── storage/      # Google Cloud Storage Manager & Sync
│   │   │   └── vms/          # Event Clipper & Rolling Ring Buffer
│   │   └── main.py           # FastAPI Application Entry
│   └── requirements.txt
├── frontend/
│   ├── index.html            # Unified Dark Surveillance UI Dashboard
│   ├── js/
│   │   ├── app.js            # Controller, WebSocket hub, GCS config
│   │   ├── canvas_editor.js  # Interactive HTML5 Canvas Line Studio
│   │   ├── analytics_charts.js # Chart.js Hourly & Donut Charts
│   │   ├── anpr_manager.js   # ANPR table, search & registry
│   │   └── alert_sound.js    # Web Audio API Synthesizer
│   └── assets/
├── models/
├── storage/
│   ├── snapshots/
│   ├── plates/
│   └── clips/
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── vercel.json
├── requirements.txt
└── README.md
```
