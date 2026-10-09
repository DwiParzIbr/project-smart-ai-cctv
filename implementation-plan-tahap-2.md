# Implementation Plan — Tahap 2: Virtual Counting Line & Real-Time Analytics Dashboard

## 1. Executive Summary
Tahap 2 berfokus pada pengembangan fitur utama **Virtual Counting Line (Garis Penghitung Interaktif)**, **Logic Deteksi Perlintasan (Crossing & Direction Tracking)**, serta **Dashboard Analitik Real-Time**. Tahap ini mengubah *live stream* bertanda *bounding box* (dari Tahap 1) menjadi sistem cerdas yang mampu menghitung, mengklasifikasikan, dan menyajikan metrik statistik lalu lintas/pengunjung secara presisi tanpa duplikasi data.

---

## 2. Fitur & Komponen Utama Tahap 2

### A. Modul Interactive Virtual Counting Line (Frontend UI)
1. **Interactive Canvas Overlay**:
   * Penambahan layer *HTML5 Canvas / Fabric.js* di atas pemutar video *live feed* pada menu **Pengaturan Kamera**.
   * Pengguna dapat menggambar, menggeser, dan menyesuaikan posisi titik koordinat garis penghitung (*Counting Line*) atau area pemantauan (*Region of Interest / ROI*) secara *drag-and-drop*.
2. **Atribut Garis & Direction**:
   * **Garis Penghitung (Line)**: Koordinat $(x_1, y_1)$ ke $(x_2, y_2)$ untuk memotong pergerakan objek.
   * **Arah Deteksi (Directional Arrow)**: Menentukan vektor *IN* (Masuk) dan *OUT* (Keluar) berdasarkan orientasi garis.
3. **Penyimpanan Konfigurasi Koordinat**:
   * Menyimpan koordinat titik ter-normalisasi ($0.0 - 1.0$ terhadap resolusi video) ke dalam database via REST API agar fleksibel untuk berbagai resolusi kamera.

---

### B. Logic Deteksi Perlintasan & Tracking (Backend Core Engine)
1. **Multi-Object Tracking (MOT) Pipeline**:
   * Mengintegrasikan algoritma *object tracking* (seperti **BYTETrack** / **SORT**) berpasangan dengan YOLO (`yolo11m` / `yolo 26l`) untuk memberikan `track_id` unik pada setiap objek terpantau.
   * Menggunakan pustaka **Buffalo_S** / kerangka pendukung untuk memastikan konsistensi ID objek saat terjadi *occlusion* (objek tertutup sementara).
2. **Line Crossing Detection Algorithm**:
   * **Vektor Intersection Math**: Menghitung perkalian silang (*cross-product*) antara vektor lintasan pusat objek (*centroid trajectory*) dengan vektor Garis Penghitung.
   * **Pencegahan Double Counting**: Setiap `track_id` yang telah memotong garis akan ditandai (*flagged*) sebagai `counted = True` untuk garis/arah tersebut, mencegah hitungan ganda saat objek berhenti atau bergerak lambat di sekitar garis.
3. **Kategori Objek yang Dihitung**:
   * Klasifikasi terpisah berdasarkan hasil *bounding box*: **Mobil, Motor, Bus, Truk, dan Orang/Pedestrian**.

---

### C. Real-Time Event & Aggregation Engine
1. **Event Data Model**:
   * Setiap kejadian perlintasan memicu pembuatan log event (*Line Crossing Event*):
     * `event_id` (UUID)
     * `camera_id` (FK)
     * `timestamp` (ISO-8601)
     * `object_class` (Mobil / Motor / Bus / Truk / Orang)
     * `direction` (MASUK / KELUAR)
     * `snapshot_path` (Gambar tangkapan layar kendaraan/orang saat melintas)
2. **In-Memory & Database Aggregation**:
   * **In-Memory Cache (FastAPI State / Redis)**: Menyimpan akumulator hitungan *real-time* harian (*Today's Total, Incoming, Outgoing*) agar respon dashboard sangat cepat.
   * **Persistent Storage (PostgreSQL/SQLite)**: Penyimpanan agregat berkala (per 15 menit/jam) untuk analisis tren historis.

---

### D. Real-Time Analytics Dashboard UI
1. **Atas (Summary Metrics Cards)**:
   * **Total Movement Today**: Akumulasi seluruh perlintasan.
   * **Total Incoming (Masuk)**: Jumlah total objek yang masuk.
   * **Total Outgoing (Keluar)**: Jumlah total objek yang keluar.
2. **Tengah (Live Feed & Active Counters Overlay)**:
   * Tampilan *video stream* utama dengan *overlay* visual garis penghitung berwarna terang dan indikator angka hitungan *real-time* pada sudut *stream*.
3. **Bawah/Samping (Analytical Visualizations & Breakdown)**:
   * **Grafik Tren Perlintasan (Time Series Chart)**: Grafik batang/garis per jam (*hourly traffic flow*) menunjukkan tren *Masuk vs Keluar*.
   * **Diagram Komposisi Objek (Pie/Donut Chart)**: Persentase sebaran jenis kendaraan/orang yang melintas (Mobil vs Motor vs Bus vs Truk vs Orang).
   * **Tabel Log Kejadian Terakhir (Recent Activity Log)**: Menampilkan 10 perlintasan terbaru lengkap dengan jam, jenis objek, arah, dan thumbnail foto *snapshot*.

---

## 3. Tahapan Implementasi & Timeline Tahap 2

| Minggu | Fokus Modul | Tugas Spesifik | Deliverables |
| :--- | :--- | :--- | :--- |
| **Minggu 1** | **UI Canvas & Line Config** | Membangun komponen UI menggambar garis interaktif & API simpan koordinat. | Antarmuka garis hitung interaktif di halaman Pengaturan Kamera. |
| **Minggu 2** | **MOT & Line Crossing Engine** | Integrasi BYTETrack + YOLO + Buffalo_S & algoritma kalkulasi perlintasan vektor. | Engine Python yang mampu menghitung objek melintas tanpa *double counting*. |
| **Minggu 3** | **Event Logging & WebSocket** | Pengiriman *event real-time* via WebSocket & perekaman *database/snapshot*. | Stream event hitungan secara *real-time* ke backend/frontend. |
| **Minggu 4** | **Analytics Dashboard UI & Chart** | Pembuatan widget statistik, time-series chart, dan pengujian end-to-end. | Dashboard analitik lengkap dengan grafik & statistik *real-time*. |

---

## 4. Kriteria Keberhasilan (Acceptance Criteria) Tahap 2
* **Presisi Garis Penghitung**: Garis dapat ditarik dan disesuaikan dengan mudah pada berbagai resolusi kamera.
* **Akurasi Penghitungan**: Tingkat akurasi hitung perlintasan $\ge 92\%$ pada kondisi pencahayaan normal.
* **Zero Double Counting**: Tidak ada pengulangan hitung untuk objek yang berhenti di atas garis.
* **Latency Dashboard**: Pembaruan angka pada *Dashboard* berlangsung $\le 500\text{ ms}$ setelah objek melintasi garis.
