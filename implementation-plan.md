# Master Implementation Plan: Sistem Smart Vision AI CCTV Surveillance Web Application

> **Versi Dokumen:** 1.0.0  
> **Target Platform:** Web-Based Standalone & Edge Server Application  
> **Cakupan:** Konsolidasi Lengkap Tahap 1, Tahap 2, Tahap 3, dan Tahap 4  

---

## 1. Executive Summary & Visi Sistem

**Smart Vision AI CCTV Surveillance** adalah platform web terpadu yang mengubah infrastruktur CCTV konvensional (RTSP kamera lokal & HLS stream publik) menjadi sistem analitik berbasis *Edge & Vision AI*. Sistem ini menggabungkan:
1. **Multi-Source Video Ingestion**: Penarikan stream paralel dari IP Camera (Hikvision, Dahua, ONVIF) dan CCTV Publik (`.m3u8`).
2. **Real-Time Object Detection & Tracking**: Menggunakan model YOLOv11 dan ByteTrack untuk deteksi simultan (Orang, Mobil, Motor, Bus, Truk) tanpa *double counting*.
3. **Interactive Virtual Counting Line**: Kanvas web interaktif untuk menarik garis penghitung dan arah (IN/OUT) dengan kalkulasi matematika vektor langsung di browser dan server.
4. **Automatic Number Plate Recognition (ANPR / OCR)**: Pembacaan plat nomor otomatis (target akurasi $\ge 95\%$) berbasis *two-stage pipeline* yang hemat sumber daya.
5. **Real-Time Alerting Multi-Saluran**: Notifikasi instan via Web Popup Banner + Suara, Telegram Bot API, dan Webhook REST API.
6. **Enterprise Ready & Edge Optimized**: Akselerasi hardware (TensorRT / ONNX FP16), arsitektur Docker Compose, serta sinkronisasi *hybrid* (inferensi lokal di edge, pengiriman metadata ke pusat).

---

## 2. Arsitektur Sistem Terintegrasi (Full-Stack Architecture)

### 2.1 Diagram Alur Data & Pipeline Komprehensif

```
[ IP Cam Lokal (RTSP) ] ──┐
                          ├──► [ Video Ingestion Service ] (OpenCV / PyAV / Thread Pool)
[ CCTV Publik (HLS) ]   ──┘                 │
                                            ▼
                               [ Frame Sampler & Ring Buffer ] (Shared Memory / Dynamic Drop)
                                            │
                                            ▼
                           [ Core Vision: YOLOv11 + ByteTrack ]
                                  (TensorRT / CUDA / CPU)
                                            │
               ┌────────────────────────────┼────────────────────────────┐
               │                            │                            │
               ▼                            ▼                            ▼
      [ Bounding Box & ID ]       [ Virtual Line Math ]       [ Plate Triggered ROI ]
               │                 (Cross-Product Vector IN/OUT)           │
               │                            │                            ▼
               │                            ▼                 [ PaddleOCR / Image Deskew ]
               │                 [ Event: Line Crossing ]                │
               │                            │                            ▼
               │                            ├──────────────────► [ Plate Matching: ]
               │                            │                    (Blacklist / Whitelist)
               │                            ▼                            │
               │                 [ In-Memory Aggregator ]                ▼
               │                 (Redis / FastAPI State)     [ Multi-Channel Alert ]
               │                            │                (Telegram / Webhook / Web Audio)
               │                            ▼                            │
               └───────────────────► [ WebSocket Hub ] ◄─────────────────┘
                                            │
                                            ▼
                         [ Frontend Web UI: Dashboard Studio ]
              (Live View, Canvas Line Editor, Charts, ANPR Logs, Alert Center)
```

---

### 2.2 Tech Stack Terpilih

| Lapisan Sistem | Teknologi / Pustaka | Rationale & Fungsi |
| :--- | :--- | :--- |
| **Frontend Web** | **HTML5 Canvas, Tailwind CSS, Alpine.js / Vanilla ES6, Fabric.js, Chart.js** | Ringan, cepat dimuat tanpa build-step rumit, performa render kanvas interaktif 60 FPS. |
| **Backend Framework** | **Python 3.10+, FastAPI, Uvicorn, Asyncio** | Asynchronous I/O cepat, dukungan native WebSockets, dokumentasi Swagger/OpenAPI otomatis. |
| **Video Decoding** | **OpenCV (`cv2`), PyAV, FFmpeg** | Decoding stream RTSP TCP/UDP latensi rendah & parsing HLS segment playlist `.m3u8`. |
| **Core Vision & Tracking** | **Ultralytics YOLO (v11n / v11s / v11m), ByteTrack** | Akurasi SOTA untuk kelas COCO (Person, Car, Motorcycle, Bus, Truck), tracking ID persisten. |
| **ANPR / OCR Engine** | **PaddleOCR / EasyOCR + Custom Regex Normalizer** | Pembacaan karakter plat nomor, preprocessing OpenCV (*adaptive threshold*, *deskew*). |
| **Inference Acceleration** | **NVIDIA TensorRT, ONNX Runtime, CUDA Toolkit** | Pemangkasan latensi komputasi hingga 50-70% via presisi FP16/INT8 di GPU lokal / Jetson. |
| **Database & Cache** | **SQLite (Dev) / PostgreSQL (Prod), Redis (Optional Cache)** | Relational storage untuk konfigurasi kamera, koordinat garis, log kendaraan, dan time-series count. |
| **Alert & Integrasi** | **Python `python-telegram-bot` / HTTPX, WebSocket** | Pengiriman alert real-time beserta foto snapshot ke Telegram dan Dashboard Web. |
| **Deployment & Ops** | **Docker, Docker Compose, NVIDIA Container Toolkit** | Standarisasi deployment di Server On-Premises, Mini PC, atau NVIDIA Jetson. |

---

### 2.3 Desain Skema Database (Database Schema)

```sql
-- 1. Tabel Kamera Terdaftar
CREATE TABLE cameras (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    source_type VARCHAR(20) NOT NULL, -- 'RTSP' atau 'HLS'
    source_url TEXT NOT NULL,
    assigned_model VARCHAR(50) DEFAULT 'yolo11n',
    target_classes JSON NOT NULL, -- ["person", "car", "motorcycle", "bus", "truck"]
    status VARCHAR(20) DEFAULT 'ONLINE', -- 'ONLINE', 'OFFLINE', 'RECONNECTING'
    fps_limit INTEGER DEFAULT 15,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Konfigurasi Virtual Counting Line
CREATE TABLE counting_lines (
    id VARCHAR(36) PRIMARY KEY,
    camera_id VARCHAR(36) REFERENCES cameras(id) ON DELETE CASCADE,
    line_name VARCHAR(50) DEFAULT 'Line 1',
    x1 REAL NOT NULL, -- Koordinat ter-normalisasi 0.0 - 1.0
    y1 REAL NOT NULL,
    x2 REAL NOT NULL,
    y2 REAL NOT NULL,
    direction_arrow VARCHAR(20) DEFAULT 'BIDIRECTIONAL', -- 'IN_ONLY', 'OUT_ONLY', 'BIDIRECTIONAL'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Log Kejadian Perlintasan (Crossing Events)
CREATE TABLE crossing_events (
    id VARCHAR(36) PRIMARY KEY,
    camera_id VARCHAR(36) REFERENCES cameras(id) ON DELETE CASCADE,
    line_id VARCHAR(36) REFERENCES counting_lines(id) ON DELETE SET NULL,
    track_id INTEGER NOT NULL,
    object_class VARCHAR(30) NOT NULL,
    direction VARCHAR(10) NOT NULL, -- 'IN' atau 'OUT'
    snapshot_path TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabel Log Kendaraan & ANPR
CREATE TABLE vehicle_logs (
    id VARCHAR(36) PRIMARY KEY,
    camera_id VARCHAR(36) REFERENCES cameras(id) ON DELETE CASCADE,
    plate_number VARCHAR(20) NOT NULL,
    normalized_plate VARCHAR(20) NOT NULL,
    confidence_score REAL NOT NULL,
    access_status VARCHAR(20) DEFAULT 'UNREGISTERED', -- 'WHITELIST', 'BLACKLIST', 'VIP', 'UNREGISTERED'
    crop_image_path TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabel Daftar Plat Nomor Terdaftar (Registry)
CREATE TABLE vehicle_registry (
    id VARCHAR(36) PRIMARY KEY,
    plate_number VARCHAR(20) UNIQUE NOT NULL,
    category VARCHAR(20) NOT NULL, -- 'WHITELIST', 'BLACKLIST', 'VIP'
    owner_name VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabel Pengaturan Alert & Pengguna
CREATE TABLE alert_rules (
    id VARCHAR(36) PRIMARY KEY,
    rule_type VARCHAR(50) NOT NULL, -- 'BLACKLIST_MATCH', 'UNKNOWN_VEHICLE', 'VOLUME_THRESHOLD'
    threshold_value INTEGER,
    channels JSON NOT NULL, -- ["web", "telegram", "webhook"]
    telegram_chat_id VARCHAR(50),
    webhook_url TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL, -- 'SUPER_ADMIN', 'OPERATOR', 'VIEWER'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Struktur Direktori Proyek (Project Structure)

```
smart-ai-cctv/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── endpoints/
│   │   │   │   ├── cameras.py       # CRUD Kamera & stream status
│   │   │   │   ├── lines.py         # CRUD Virtual Counting Line
│   │   │   │   ├── analytics.py     # Aggregated stats & time-series
│   │   │   │   ├── anpr.py          # Log ANPR, Blacklist/Whitelist CRUD
│   │   │   │   ├── alerts.py        # Trigger & Notification configuration
│   │   │   │   ├── export.py        # PDF & Excel export generator
│   │   │   │   └── system.py        # CPU, GPU, RAM, Disk monitoring
│   │   │   ├── websocket.py         # Stream frame & live event socket
│   │   │   └── deps.py              # Auth & DB dependencies
│   │   ├── core/
│   │   │   ├── config.py            # App settings (.env parser)
│   │   │   ├── security.py          # JWT & Password hashing
│   │   │   └── events.py            # Startup/Shutdown lifecycle
│   │   ├── db/
│   │   │   ├── base.py              # SQLAlchemy base model
│   │   │   └── session.py           # DB connection engine & session
│   │   ├── engine/
│   │   │   ├── ingestion/
│   │   │   │   ├── stream_reader.py # Threaded RTSP & HLS capture
│   │   │   │   └── watchdog.py      # Auto-reconnect with exponential backoff
│   │   │   ├── vision/
│   │   │   │   ├── detector.py      # YOLOv11 inference manager
│   │   │   │   ├── tracker.py       # ByteTrack MOT integration
│   │   │   │   └── buffer.py        # Ring-buffer & dynamic frame dropper
│   │   │   ├── analytics/
│   │   │   │   ├── vector_math.py   # Cross-product line crossing math
│   │   │   │   └── counter.py       # Non-double counting state manager
│   │   │   ├── anpr/
│   │   │   │   ├── ocr_engine.py    # PaddleOCR pipeline & preprocessing
│   │   │   │   └── plate_parser.py  # Regex & format normalizer plat RI
│   │   │   └── alerts/
│   │   │       ├── dispatcher.py    # Multi-channel notification sender
│   │   │       └── telegram_bot.py  # Telegram client integration
│   │   └── main.py                  # FastAPI Application Entry
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html                   # Single Page App Shell
│   ├── css/
│   │   └── style.css                # Custom styling & animations
│   ├── js/
│   │   ├── app.js                   # State router & init
│   │   ├── stream_player.js         # WebSocket & MJPEG video renderer
│   │   ├── canvas_editor.js         # Fabric.js interactive line editor
│   │   ├── analytics_charts.js      # Chart.js time-series & donut charts
│   │   ├── anpr_manager.js          # Table search, fuzzy filter, badge
│   │   ├── alert_sound.js           # Web Audio API alert sound effects
│   │   └── system_monitor.js        # Resource dashboard live updater
│   └── assets/                      # Icons, logo, alert audio files
├── models/
│   ├── yolo11n.pt                   # Pretrained weights
│   ├── yolo11m.pt
│   └── ocr/                         # Pretrained OCR models
├── storage/
│   ├── snapshots/                   # Captured line-crossing frames
│   ├── plates/                      # Cropped license plate images
│   └── exports/                     # Generated PDF & Excel files
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 4. Rincian Fitur & Modul Berdasarkan Tahap 1–4

### 4.1 Modul 1: Ingestion Kamera & Streaming Video (Tahap 1)
* **Koneksi Dual-Source**:
  * **RTSP**: Menggunakan `cv2.VideoCapture` dengan backend FFmpeg melalui opsi `rtsp_transport=tcp` untuk mencegah *packet loss / artifacting* pada IP Cam lokal.
  * **HLS (`.m3u8`)**: Parsing playlist segment otomatis dengan penanganan buffer dinamis.
* **Stream Watchdog & Auto-Reconnect**:
  * Loop terpisah mengecek ketersediaan frame setiap 2 detik.
  * Jika stream terputus, sistem mengaktifkan *exponential backoff* ($1\text{s}, 2\text{s}, 4\text{s}, \dots, 30\text{s}$) hingga stream pulih secara mandiri.
* **Streaming ke Frontend**:
  * Dual-mode: WebSocket binary transfer (efisien & latensi rendah) atau MJPEG Streamer endpoint `/api/stream/{camera_id}` untuk kompatibilitas universal tag `<img>`.

---

### 4.2 Modul 2: AI Core Vision & Object Tracking (Tahap 1 & 2)
* **Model Inference Pipeline**:
  * Pemuatan model Ultralytics YOLO (`yolo11n` / `yolo11m`) dengan filter kelas terkonfigurasi per kamera: `[person, car, motorcycle, bus, truck]`.
* **Multi-Object Tracking (ByteTrack)**:
  * Memberikan `track_id` unik pada setiap objek.
  * Menyimpan jejak koordinat riwayat (*trajectory history* hingga 30 frame terakhir) untuk analisis lintasan pergerakan.
* **Pencegahan Double-Counting**:
  * Objek yang telah dihitung diberi status `counted = True` di dalam dictionary state memori tracker hingga objek meninggalkan frame (*age-out*).

---

### 4.3 Modul 3: Kanvas Interaktif Virtual Counting Line (Tahap 2)
* **Interactive Canvas Studio (Frontend)**:
  * Pengguna memilih kamera dari dropdown, video live ditampilkan sebagai latar belakang.
  * Pengguna dapat mengklik dan menarik garis pada video:
    * Titik awal: $(x_1, y_1)$
    * Titik akhir: $(x_2, y_2)$
    * Panah Arah: Menandai arah **IN (Masuk)** dan **OUT (Keluar)**.
  * Koordinat otomatis dinormalisasi menjadi rentang $0.0 - 1.0$ sebelum disimpan ke database melalui endpoint `POST /api/lines`.
* **Vektor Intersection Math (Backend)**:
  * Posisi objek ditentukan dari **titik tengah bawah (*bottom-center*) dari bounding box**:
    $$P_{\text{obj}} = \left( \frac{x_{\min} + x_{\max}}{2}, y_{\max} \right)$$
  * Menghitung nilai *cross-product* antara vektor garis penghitung $\vec{L} = (P_2 - P_1)$ dengan pergerakan titik objek $\vec{M} = (P_{\text{obj}, t} - P_{\text{obj}, t-1})$:
    $$\text{Side}(P) = (x_2 - x_1)(y - y_1) - (y_2 - y_1)(x - x_1)$$
  * Jika nilai $\text{Side}(P_{t-1})$ dan $\text{Side}(P_t)$ berlawanan tanda, perlintasan terdeteksi. Orientasi tanda positif/negatif menentukan arah **IN** atau **OUT**.

---

### 4.4 Modul 4: Real-Time Traffic Analytics Dashboard (Tahap 2)
* **Metric Summary Cards**:
  * **Today's Total Movement**: Akumulasi seluruh kendaraan & orang.
  * **Incoming Traffic**: Total kendaraan/orang masuk.
  * **Outgoing Traffic**: Total kendaraan/orang keluar.
  * **Active Rate**: Rata-rata perlintasan per menit saat ini.
* **Visualisasi Grafik Interaktif**:
  * **Hourly Traffic Flow (Line/Bar Chart)**: Grafik komparasi per jam antara arus Masuk vs Keluar hari ini.
  * **Object Composition (Donut Chart)**: Persentase sebaran jenis objek (Mobil, Motor, Truk, Bus, Orang).
* **Recent Activity Feed**:
  * Menampilkan 10 perlintasan terakhir lengkap dengan snapshot thumbnail, timestamp, jenis objek, dan arah.

---

### 4.5 Modul 5: ANPR & License Plate Recognition Pipeline (Tahap 3)
* **Triggered OCR (Hemat Komputasi)**:
  * Tidak menjalankan OCR di setiap frame. OCR hanya aktif saat:
    1. Kendaraan berstatus valid melintasi Virtual Counting Line, ATAU
    2. Kendaraan memasuki area ROI ANPR yang ditentukan.
* **Stage 1 (Plate Crop & Enhancer)**:
  * Lokalisasi area plat nomor menggunakan sub-detector atau crop rasio standar bagian bawah kendaraan.
  * Preprocessing OpenCV: *Grayscale*, *Bilateral Filtering* (denoising tanpa merusak tepi), *Adaptive Thresholding*, dan *Perspective Deskewing*.
* **Stage 2 (OCR & Format Normalizer)**:
  * Inferensi teks menggunakan PaddleOCR.
  * Pembersihan karakter non-alfanumerik dan validasi regex pola plat nomor Indonesia:
    `^[A-Z]{1,2}\s?[0-9]{1,4}\s?[A-Z]{1,3}$`
  * Pemetaan karakter membingungkan (misal: angka `0` vs huruf `O`, angka `8` vs huruf `B`, angka `1` vs huruf `I`) berdasarkan posisi indeks plat.
* **Target Akurasi**: Mencapai $\ge 95\%$ pada plat dengan pencahayaan cukup dan orientasi standar.

---

### 4.6 Modul 6: Sistem Alerting Real-Time Multi-Saluran (Tahap 3)
* **Kategori Aturan Alert**:
  * **Blacklist Detection**: Munculnya plat nomor yang terdaftar di daftar buron / dilarang.
  * **Unregistered Ingress**: Kendaraan tak dikenal memasuki gerbang/area terbatas pada jam malam.
  * **Congestion / Threshold Exceeded**: Volume perlintasan melebihi ambang batas (misal $> 50$ kendaraan/menit).
* **Saluran Distribusi**:
  1. **Web Dashboard**: Banner modal merah menyala + efek audio beep peringatan via Web Audio API.
  2. **Telegram Bot**: Mengirim pesan darurat instan berisikan nama kamera, plat nomor, status daftar, timestamp, dan lampiran foto crop plat.
  3. **Webhook REST**: Mengirimkan payload JSON ke sistem gerbang/palang parkir otomatis (`/api/gate/trigger`).

---

### 4.7 Modul 7: Search Engine, Audit Trail, & Ekspor Laporan (Tahap 3)
* **Smart Plate Search**:
  * Pencarian berbasis *fuzzy matching* menggunakan algoritma *Levenshtein Distance* (toleransi beda 1 karakter) untuk mengantisipasi kesalahan OCR kecil.
  * Filter rentang tanggal/jam, filter kamera, dan filter status (Blacklist, Whitelist, VIP, Unregistered).
* **Ekspor Laporan**:
  * **Excel (.xlsx)**: Data log lengkap dengan detail waktu, kamera, plat, status, dan confidence score.
  * **PDF Summary**: Dokumen laporan resmi berisikan ringkasan statistik, grafik tren harian, dan tabel perlintasan penting.

---

### 4.8 Modul 8: Akselerasi Hardware & High Performance Pipeline (Tahap 4)
* **Model Quantization & TensorRT**:
  * Skrip konversi otomatis dari `.pt` $\to$ `.onnx` $\to$ `.engine` (TensorRT) dengan presisi FP16 di lingkungan GPU NVIDIA.
  * Mengurangi waktu inferensi frame dari $\sim 35\text{ ms}$ menjadi $\le 8\text{ ms}$.
* **Adaptive Frame Dropping & Ring Buffer**:
  * Buffer video berbasis antrean berukuran terbatas (`maxsize=3`).
  * Jika waktu komputasi GPU melonjak, frame lama dibuang secara otomatis (*drop oldest*) agar latensi video stream tetap *real-time* ($< 500\text{ ms}$) tanpa penumpukan memori.

---

### 4.9 Modul 9: Edge Deployment & Central Hybrid Sync (Tahap 4)
* **Dukungan Edge Devices**:
  * Kompatibel dengan NVIDIA Jetson Orin Nano / Orin NX dan PC Industri berbasis Ubuntu 22.04 LTS.
* **Hybrid Data Sync**:
  * Inferensi video 100% diproses di perangkat lokal tanpa perlu upload video mentah ke cloud.
  * Penghematan bandwidth: Hanya metadata JSON (log crossing, teks plat, dan thumbnail terkompresi) yang disinkronisasikan ke Central Server.
* **Docker Compose Multi-Container**:
  * Pengemasan terisolasi: `cctv-backend`, `cctv-frontend-nginx`, dan `cctv-db`.

---

### 4.10 Modul 10: Keamanan, RBAC, & Resource Monitoring (Tahap 4)
* **Role-Based Access Control (RBAC)**:
  * **Super Admin**: Akses penuh ke manajemen kamera, model AI, aturan alert, dan akun pengguna.
  * **Operator**: Dapat mengelola Virtual Counting Line, input data plat nomor, dan memantau alert.
  * **Viewer**: Akses *read-only* ke Live Stream dan Analytics Dashboard.
* **Automated Data Purge**:
  * Background task otomatis menghapus snapshot foto perlintasan yang berumur lebih dari 30 hari (dapat disesuaikan) untuk menjaga kapasitas hard disk.
* **System Health Widget**:
  * Menampilkan metrik live penggunaan CPU %, GPU VRAM %, Suhu GPU, RAM %, dan sisa kapasitas penyimpanan Disk di sudut navigasi.

---

## 5. Rincian Antarmuka Web (UI/UX Specification)

Aplikasi dibangun sebagai **Unified Web Dashboard** dengan navigasi bilah samping (*Sidebar Navigation*):

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ [Logo] SMART VISION AI CCTV                     [CPU: 18%] [GPU: 42%] [Admin v] │
├──────────────┬──────────────────────────────────────────────────────────────────┤
│ 🎥 Live View │ [ + Tambah Kamera ]  [ Tampilan: 2x2 Grid v ]   [ Filter: Semua] │
│ 📐 Line Canvas│ ┌───────────────────────┬───────────────────────┐                │
│ 📊 Analitik  │ │ CAM 01 - Pintu Masuk  │ CAM 02 - Parkir Barat │                │
│ 🚗 ANPR Hub  │ │ [ Live Feed + Boxes ] │ [ Live Feed + Boxes ] │                │
│ 🚨 Alert Log │ │ FPS: 25 | In: 142     │ FPS: 22 | In: 85      │                │
│ ⚙️ Pengaturan│ ├───────────────────────┼───────────────────────┤                │
│              │ │ CAM 03 - Jalur Keluar │ CAM 04 - Lobby Utama  │                │
│              │ │ [ Live Feed + Boxes ] │ [ Live Feed + Boxes ] │                │
│              │ │ FPS: 28 | Out: 130    │ FPS: 30 | People: 12  │                │
│              │ └───────────────────────┴───────────────────────┘                │
└──────────────┴──────────────────────────────────────────────────────────────────┘
```

### Halaman-Halaman Utama:
1. **Live Feed View**:
   * Pilihan Grid: $1\times 1$, $2\times 2$, $3\times 3$.
   * Toggle visual: Tampilkan/Sembunyikan Bounding Box, Track ID, dan Counting Line.
2. **Virtual Line & ROI Canvas Studio**:
   * Mode interaktif drag-and-drop titik garis.
   * Kontrol arah: Arah panah Masuk/Keluar.
   * Tombol: "Simpan Garis", "Hapus Garis", "Reset Koordinat".
3. **Analytics Dashboard Studio**:
   * Baris 1: Kartu Metrik (Total Lalu Lintas, Masuk, Keluar, Objek Aktif).
   * Baris 2: Grafik Garis Tren Jam Lalu Lintas & Grafik Donut Komposisi Kendaraan.
   * Baris 3: Tabel 10 Riwayat Perlintasan Terakhir dengan Foto Thumbnail.
4. **ANPR & Vehicle Registry Hub**:
   * Modal "Tambah Kendaraan" (Plat, Pemilik, Kategori: Whitelist/Blacklist/VIP).
   * Tabel Log Deteksi Plat: Thumbnail, Jam, Plat Nomor, Status Akses, Confidence %.
   * Fitur Search & Filter Cepat (Fuzzy Plate Search).
   * Tombol "Ekspor Excel" & "Ekspor PDF".
5. **Alert & Notification Center**:
   * Riwayat alert darurat berurut waktu (*chronological*).
   * Form pengaturan token Telegram Bot & Chat ID tujuan.
   * Form pengaturan URL Webhook endpoint eksternal.
6. **Hardware & Camera Management**:
   * Form pendaftaran kamera (Nama, RTSP/HLS URL, Pilihan Bobot YOLO, Target Kelas).
   * Indikator status koneksi (Hijau = Online, Merah = Offline/Reconnecting).
   * Grafik mini beban GPU VRAM dan CPU.

---

## 6. Spesifikasi Kontrak API & WebSocket

### 6.1 REST API Endpoints

| Method | Endpoint | Fungsi |
| :--- | :--- | :--- |
| `GET` | `/api/cameras` | Mengambil seluruh daftar kamera dan status koneksinya |
| `POST` | `/api/cameras` | Mendaftarkan kamera baru (RTSP / HLS) |
| `PUT` | `/api/cameras/{id}` | Mengubah konfigurasi kamera |
| `DELETE`| `/api/cameras/{id}` | Menghapus kamera dan melepaskan worker stream |
| `GET` | `/api/cameras/{id}/lines` | Mengambil konfigurasi garis pada kamera terkait |
| `POST` | `/api/cameras/{id}/lines` | Menyimpan koordinat garis dan arah perlintasan |
| `GET` | `/api/analytics/summary` | Mengambil data metrik hari ini (Total, In, Out, Breakdown) |
| `GET` | `/api/analytics/hourly` | Mengambil data tren time-series per jam |
| `GET` | `/api/anpr/logs` | Mengambil log deteksi plat dengan filter query & pagination |
| `POST` | `/api/anpr/registry` | Menambahkan plat ke daftar Whitelist/Blacklist |
| `GET` | `/api/alerts/history` | Mengambil riwayat alert yang pernah terpicu |
| `POST` | `/api/alerts/config` | Menyimpan konfigurasi Telegram dan Webhook |
| `GET` | `/api/export/excel` | Menghasilkan dan mengunduh berkas laporan `.xlsx` |
| `GET` | `/api/export/pdf` | Menghasilkan dan mengunduh berkas laporan `.pdf` |
| `GET` | `/api/system/metrics` | Mengambil data beban CPU, GPU VRAM, Disk, dan Uptime |

### 6.2 WebSocket Streams

* **`/ws/stream/{camera_id}`**:
  * Mengalirkan frame terkompresi (JPEG/WebP) dengan overlay bounding box langsung ke frontend untuk latensi terendah.
* **`/ws/events`**:
  * Mengirimkan broadcast event instan ke frontend saat terjadi perlintasan garis (*line crossing*) atau deteksi alert plat nomor (*blacklist alert*).

---

## 7. Rencana Tahapan Eksekusi Pembangunan (Step-by-Step Roadmap)

```
Minggu 1-2: Ingestion & Core Vision  ──► Minggu 3-4: Virtual Line & Analytics
                │                                    │
                ▼                                    ▼
Minggu 7-8: TensorRT, Edge & Polish  ◄── Minggu 5-6: ANPR & Alerting System
```

### Fase 1: Fondasi Proyek, Ingestion, & Streaming Dasar (Tahap 1)
1. **Inisialisasi Project Skeleton**: Penyiapan FastAPI, dependensi Python, konfigurasi database SQLite/PostgreSQL.
2. **Stream Ingestion Engine**: Pembangunan modul `StreamReader` dengan auto-reconnect untuk RTSP lokal dan HLS.
3. **Core Vision Pipeline**: Integrasi Ultralytics YOLOv11 dan filter kelas objek.
4. **Web UI Shell & Stream Viewer**: Pembuatan frontend HTML/Tailwind dengan tampilan grid pemutar video.

### Fase 2: Kanvas Interaktif, Vektor Perlintasan, & Live Analytics (Tahap 2)
1. **Interactive Canvas Studio**: Integrasi Fabric.js pada web untuk menggambar garis penghitung dan arah panah.
2. **Line Crossing Algorithm**: Implementasi matematika vektor *cross-product* dan pelindung *anti-double counting*.
3. **In-Memory & Database Aggregator**: Pencatatan log event perlintasan dan snapshot foto kendaraan.
4. **Analytics Dashboard UI**: Pembuatan kartu metrik statistik dan grafik tren jam dengan Chart.js.

### Fase 3: ANPR OCR Pipeline, Alerting, & Pelaporan (Tahap 3)
1. **Triggered OCR Integration**: Ekstraksi crop plat nomor yang dipicu oleh event perlintasan garis.
2. **OCR Preprocessing & Parser**: Integrasi PaddleOCR dan regex pembersihan plat nomor Indonesia.
3. **Vehicle Registry & Blacklist Matching**: Manajemen daftar plat nomor kendaraan di web UI.
4. **Multi-Channel Alert Dispatcher**: Pengiriman alert suara di web, notifikasi bot Telegram, dan webhook API.
5. **Search & Report Generator**: Mesin pencari plat berbasis fuzzy matching dan ekspor PDF/Excel.

### Fase 4: Akselerasi TensorRT, Dockerization, Edge Deploy, & RBAC (Tahap 4)
1. **Akselerasi Model**: Konversi model YOLO ke TensorRT/ONNX FP16 untuk memangkas latensi komputasi.
2. **Buffer Optimization**: Penerapan *dynamic frame dropping* dan *shared memory buffer*.
3. **Security & RBAC**: Sistem login JWT, enkripsi sandi, dan pembagian hak akses (Admin, Operator, Viewer).
4. **Data Retention & Resource Monitor**: Background task pembersihan snapshot 30 hari dan dashboard kesehatan server.
5. **Packaging & Deployment**: Pembuatan Dockerfile, `docker-compose.yml`, dan panduan instalasi di NVIDIA Jetson / Ubuntu Server.

---

## 8. Kriteria Penerimaan & Matriks Keberhasilan (Quality Gates)

| Parameter / Fitur | Target Kriteria | Metode Verifikasi |
| :--- | :--- | :--- |
| **Latensi Streaming** | $< 500\text{ ms}$ pada jaringan lokal | Uji coba RTSP stream lokal di browser |
| **Ketahanan Ingestion** | Pulih otomatis dalam $< 5\text{ detik}$ pasca putus jaringan | Simulasi cabut-colok kabel LAN / reboot kamera |
| **Akurasi Penghitungan** | $\ge 92\%$ akurasi hitung perlintasan | Uji lalu lintas 100 kendaraan melintas |
| **Pencegahan Double-Counting** | $0$ duplikasi saat objek berhenti di atas garis | Pengujian kendaraan berhenti selama 10 detik di atas garis |
| **Akurasi ANPR / OCR** | $\ge 95\%$ pembacaan karakter plat standar | Uji dataset 100 sampel plat nomor kendaraan |
| **Kecepatan Alert** | Notifikasi Telegram terkirim $< 2\text{ detik}$ | Pengujian plat Blacklist melintasi kamera |
| **Efisiensi Edge Server** | Penggunaan GPU VRAM $\le 4\text{ GB}$, FPS $\ge 20$ | Monitoring via `nvidia-smi` pada 4 stream bersamaan |
| **Stabilitas Sistem** | Operasional stabil 24/7 tanpa kebocoran memori | Stress test streaming berkelanjutan selama 48 jam |
