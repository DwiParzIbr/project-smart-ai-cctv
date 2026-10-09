# Implementation Plan — Tahap 1: Multi-Source Ingestion Engine & Core AI Vision Pipeline

## Executive Summary
Dokumen ini merupakan panduan implementasi komprehensif untuk **Tahap 1** dalam pembangunan **Sistem Vision AI Monitoring CCTV Standalone**. Tahap 1 berfokus pada pembangunan fondasi infrastruktur *ingestion* kamera yang fleksibel (mendukung kamera lokal kantor/rumah via RTSP serta CCTV publik via HLS) dan pemrosesan *core AI inference engine* berbasis Python, YOLO, dan Buffalo_S.

---

## 1. Tujuan & Cakupan Tahap 1

### 1.1 Tujuan Utama
- Membangun **Aplikasi Web HTML Standalone** yang dapat memproses dan menampilkan tayangan *live streaming* CCTV secara *real-time*.
- Menyediakan konektivitas **Multi-Source Camera Ingestion** yang mampu menangani:
  1. **Kamera Lokal (CCTV Kantor/Rumah)**: Menggunakan RTSP/ONVIF dari IP Camera, DVR, atau NVR.
  2. **Kamera Web Stream Remote**: Menggunakan protokol HLS (`.m3u8`) dari CCTV publik/daerah.
- Mengintegrasikan modul **AI Detection Engine** menggunakan pre-trained model (YOLO `yolo11m`, `yolo 26l`, dan COCO weights) serta kerangka Buffalo_S untuk pencegahan *double counting*.

### 1.2 Out of Scope (Untuk Tahap Berikutnya)
- Modul *Virtual Counting Line* interaktif & *Real-time Vehicle Analytics* (Tahap 2).
- Pemrosesan *High-Precision License Plate Recognition* (OCR 95%+ accuracy) (Tahap 3).
- Fitur *Notification Alert System* & *Export Report PDF/CSV* (Tahap 4).

---

## 2. Arsitektur Teknis & Komponen Sistem

### 2.1 Tech Stack
- **Frontend**: Standalone HTML5, CSS3 (Tailwind / Bootstrap), JavaScript (ES6+), WebSocket client.
- **Backend Service**: Python 3.10+ (FastAPI / Flask).
- **Video Processing Engine**: OpenCV, FFmpeg, PyAV (RTSP & HLS decoding/re-streaming).
- **AI Inference Engine**:
  - **Ultralytics YOLO**: `yolo11m` (objek mobil/kendaraan), `yolo 26l` (objek orang/pedestrian), COCO default weights.
  - **Object Tracking & Re-ID**: Buffalo_S framework / ByteTrack untuk koordinasi deteksi simultan dan eliminasi duplikasi data.
- **Database**: SQLite / PostgreSQL (Penyimpanan data kamera terdaftar dan konfigurasi AI).

### 2.2 Diagram Alur Data Tahap 1
```
[ Kamera IP Lokal (RTSP) ] ──┐
                             ├──> [ Video Ingestion Service ] ──> [ Frame Sampler ] ──> [ YOLO + Buffalo_S AI Engine ]
[ Web CCTV Remote (HLS) ]  ──┘        (OpenCV / FFmpeg)              (Python)             (Bounding Box & Classes)
                                                                                                    │
                                                                                                    ▼
[ Web Dashboard HTML ] <─── [ WebSocket / MJPEG Streamer ] <─── [ Multi-Stream Compositor ] ◄──────┘
```

---

## 3. Spesifikasi Fitur Ingestion & Manajemen Kamera

### 3.1 Formulir Pengaturan & Registrasi Kamera
Antarmuka web menyediakan modal/halaman **Tambah Kamera** dengan bidang isian:
1. **Nama Kamera**: Identifikasi unik (misal: *Pintu Depan Toko*, *Pasar Stan*, *Titik 0*).
2. **Jenis Sumber**:
   - `RTSP (Kamera IP / Hikvision / Dahua)`
   - `HLS / CCTV Web Stream (.m3u8)`
3. **URL Sumber**:
   - Format RTSP Lokal: `rtsp://[username]:[password]@[ip_address]:[port]/[stream_path]` (Contoh: `rtsp://admin:sandi@192.168.100.64:554/Streaming/Channels/101`).
   - Format HLS Remote: `https://.../chunklist_w1456794183.m3u8`.
4. **Pilihan Bobot AI (Assigned Weights)**:
   - `yolo11m` (Fokus Deteksi Kendaraan)
   - `yolo 26l` (Fokus Deteksi Orang/Manusia)
   - `Bobot Bawaan Sistem (COCO)`
5. **Target Objek Dideteksi (Checkbox Multi-Select)**:
   - `[ ] Orang` | `[ ] Mobil` | `[ ] Motor` | `[ ] Bus` | `[ ] Truk`

---

## 4. Langkah Implementasi (Implementation Steps)

### Langkah 1: Setup Environment & Dependensi Core
1. Inisialisasi struktur proyek backend Python dan frontend HTML.
2. Instalasi pustaka utama: `ultralytics`, `opencv-python`, `fastapi`, `uvicorn`, `pydantic`, `pyav`, `torch`.
3. Menyiapkan repositori *pre-trained model weights* (`yolo11m.pt`, `yolo26l.pt`, `yolov8n.pt`/COCO) tanpa *training from scratch*.

### Langkah 2: Pembangunan Multi-Source Stream Reader
1. Membuat modul `StreamReader` yang meng-handle koneksi RTSP (lokal) dan HLS (remote) secara asinkron.
2. Menerapkan penanganan Re-connection Otomatis (*auto-reconnect*) jika jaringan IP Camera lokal atau stream web terputus.
3. Mengimplementasikan buffer manajemen frame agar penggunaan RAM tetap stabil.

### Langkah 3: Integrasi YOLO Inference Engine & Buffalo_S Tracking
1. Mengembangkan kelas `AIVisionEngine` yang memuat bobot model YOLO sesuai konfigurasi kamera.
2. Menggabungkan pustaka **Buffalo_S** untuk menjaga ID objek tetap konsisten antar-frame dan mencegah pencatatan ganda (*double counting*).
3. Menerapkan pemrosesan deteksi multi-objek (Orang, Mobil, Motor, Bus, Truk) secara simultan.

### Langkah 4: Development Backend API & WebSocket Server
1. Membuat endpoint REST API:
   - `POST /api/cameras` (Tambah Kamera Baru)
   - `GET /api/cameras` (Daftar Kamera Terdaftar)
   - `DELETE /api/cameras/{id}` (Hapus Kamera)
2. Membuat endpoint *streaming real-time* (WebSocket/MJPEG) untuk menyalurkan tayangan video dengan *overlay bounding box* dan indikator FPS ke frontend.

### Langkah 5: Pembangunan Antarmuka Web Dashboard Standalone (HTML/JS)
1. Mendesain tata letak **Grid Dashboard View** untuk menampilkan *multi-camera live feed*.
2. Membangun halaman/tab **Pengaturan Kamera** sesuai desain spesifikasi rujukan.
3. Memastikan responsivitas dan kelancaran putar video pada browser modern.

---

## 5. Standar Kualitas & Kriteria Keberhasilan (Quality Gates)

| Parameter | Target Kriteria | Keterangan |
| :--- | :--- | :--- |
| **Konektivitas RTSP** | Latensi < 500ms pada jaringan lokal | Mendukung IP Cam Hikvision, Dahua, Bardi, NVR |
| **Konektivitas HLS** | Smooth playback (.m3u8) | Auto-buffering & re-connect jika stream putus |
| **Pencegahan Duplikasi** | Zero duplicate tracking ID per-object | Menggunakan Buffalo_S / ByteTrack tracker |
| **Performa FPS** | Minimal 15–30 FPS per stream | Disesuaikan dengan kapasitas GPU/CPU server |
| **Antarmuka (UI)** | Presisi sesuai spesifikasi rujukan | Standalone HTML web application |

---

## 6. Persiapan Lanjut Ke Tahap 2
Setelah Tahap 1 selesai dan diverifikasi:
1. Pipa data *live stream* dan deteksi AI dasar siap digunakan.
2. Pengembang dapat melanjutkan ke **Tahap 2**, yaitu pembuatan modul visualisasi *Virtual Counting Line* interaktif pada kanvas HTML5 dan pengolahan data statistik masuk/keluar secara *real-time*.
