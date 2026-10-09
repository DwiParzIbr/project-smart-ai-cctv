# Implementation Plan — Tahap 3: License Plate Recognition (OCR/ANPR) & Real-Time Alerting System

## 📌 Deskripsi Singkat
Tahap 3 berfokus pada integrasi tingkat lanjut untuk pengenalan plat nomor kendaraan secara otomatis (**Automatic Number Plate Recognition / ANPR**) menggunakan teknologi **OCR (Optical Character Recognition)** berakurasi tinggi (minimal 95%), serta pembangunan **Sistem Notifikasi & Alerting Real-Time** berbasis aturan (*rule-based*) untuk meningkatkan keamanan dan pemantauan lalu lintas.

---

## 🎯 Tujuan Utama Tahap 3
1. Mengintegrasikan *pipeline* ekstraksi dan pembacaan plat nomor dari *stream* video CCTV.
2. Memenuhi kriteria standar industri dengan akurasi pembacaan karakter plat nomor minimal **95%**.
3. Menyediakan manajemen daftar kendaraan (*Blacklist*, *Whitelist*, *Visitor*, *VIP*).
4. Pembangunan *engine* notifikasi multi-saluran (*Web Dashboard*, *Telegram Bot*, *Email/Webhook*).
5. Modul pencarian riwayat plat nomor (*Search & Audit Log*) beserta ekspor laporan.

---

## 🏗️ Komponen Utama & Langkah Kerja Technical

### 1. License Plate Detection & OCR Pipeline (Backend AI)
* **Two-Stage Detection Pipeline**:
  1. **Stage 1 (Vehicle & Plate Localization)**:
     * Menggunakan **YOLO** (`yolo11m`) untuk mendeteksi lokasi kendaraan pada *frame*.
     * Ekstraksi Sub-ROI (*Region of Interest*) khusus area plat nomor kendaraan.
  2. **Stage 2 (Image Pre-processing & OCR Engine)**:
     * *Image Enhancer*: Pembersihan citra plat (*grayscale*, *adaptive thresholding*, *deskewing*, dan *denoising*) untuk mengatasi kondisi pencahayaan minim/malam atau sudut kamera miring.
     * *OCR Engine Integration*: Mengintegrasikan kerangka kerja OCR (seperti PaddleOCR / EasyOCR / Custom Fine-Tuned OCR Model) yang di-bantu *pre-training* tambahan untuk format plat nomor lokal.
     * Target Akurasi: Pemastian tingkat presisi pembacaan karakter $\ge 95\%$.

### 2. Database Log Kendaraan & Manajemen Daftar (*Blacklist/Whitelist*)
* **Skema Tabel Database (`vehicle_logs`)**:
  * `id`: Primary Key
  * `timestamp`: Waktu deteksi
  * `camera_id`: ID Kamera sumber
  * `plate_number`: Teks hasil OCR (contoh: `B 1234 CD`)
  * `confidence_score`: Tingkat kepercayaan pembacaan OCR (%)
  * `crop_image_path`: Path penyimpanan foto *crop* plat nomor
  * `access_status`: Status (`WHITELIST`, `BLACKLIST`, `UNREGISTERED`, `VIP`)
* **Modul Manajemen Kendaraan**:
  * Antarmuka admin untuk pendaftaran plat nomor ke dalam kategori tertentu (*Whitelist/Blacklist*) beserta catatan (*reason/owner*).

### 3. Engine Notifikasi & Alerting System Real-Time
* **Alert Trigger Rules**:
  * **Blacklist Alert**: Notifikasi instan saat plat nomor berstatus *Blacklist*/dilarang terdeteksi oleh kamera.
  * **Unregistered/Unknown Vehicle Alert**: Peringatan untuk kendaraan tidak dikenal yang masuk ke area terbatas.
  * **Threshold Traffic Alert**: Peringatan jika volume kendaraan melampaui batas kapasitas per menit/jam.
* **Multi-Channel Dispatcher**:
  * **Web Dashboard Alert**: *Pop-up banner* merah mencolok beserta efek suara (*sound alert*) di antarmuka web.
  * **Telegram Bot / WhatsApp Gateway**: Pengiriman pesan peringatan otomatis berisi informasi lokasi kamera, waktu, teks plat nomor, dan foto bukti *crop* plat.
  * **Webhook API**: Dukungan integrasi ke sistem pihak ketiga (misal: *Pintu Palang Otomatis / Boom Gate*).

### 4. Modul Search, Audit Log, dan Ekspor Laporan
* **Smart Search Engine**:
  * Pencarian riwayat melintas berdasarkan input nomor plat dengan dukungan *fuzzy matching* / *partial string search* (mencegah kegagalan pencarian akibat kesalahan 1 karakter OCR).
  * Filter pencarian berdasarkan rentang tanggal/jam, lokasi kamera, dan status kendaraan.
* **Reporting & Export**:
  * Fitur cetak/unduh laporan aktivitas kendaraan dan statistik dalam format **PDF** dan **Excel (.xlsx)**.

---

## 🛠️ Stack Teknologi Tahap 3
* **AI & OCR Framework**: OpenCV, Python, PaddleOCR / EasyOCR, PyTorch.
* **Backend API & WebSocket**: FastAPI / Python, SQLite / PostgreSQL.
* **Notification Integration**: Telegram Bot API, Webhook REST API, Web Notification WebSockets.
* **Frontend Components**: HTML5, Tailwind CSS, JavaScript ES6 (Modal Alert, Audio Context Alert, DataTables with Image Preview).

---

## 📋 Deliverables (Hasil Akhir) Tahap 3
1. Pipeline OCR otomatis yang mampu membaca gambar plat nomor dari *live stream* CCTV menjadi teks terstruktur.
2. Modul pengelola *Blacklist/Whitelist* kendaraan.
3. Notifikasi *real-time* multi-saluran (*Web Pop-up* & *Telegram Bot*) saat terjadi insiden/terdeteksi plat nomor tertentu.
4. Antarmuka pencarian riwayat plat nomor lengkap dengan bukti tangkapan gambar (*snapshot*) dan ekspor laporan.

---

## ⏩ Langkah Selanjutnya (Tahap 4 Preview)
Setelah Tahap 3 selesai, sistem dapat dilanjutkan ke **Tahap 4: System Optimization, Multi-Camera Central Node, Edge Deployment, & Final Polish**.
