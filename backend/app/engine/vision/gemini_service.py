import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_FORENSIC_PROMPT = """Anda adalah Sistem AI Analis Forensik Pengawasan CCTV (Smart CCTV Vision Intelligence).
Analisis rekaman visual / snapshot CCTV ini secara profesional, akurat, dan mendalam.
Sajikan laporan investigasi terstruktur dalam Bahasa Indonesia dengan format Markdown berikut:

### 1. 📌 Ringkasan Adegan & Kondisi
- Deskripsi singkat adegan yang tertangkap di kamera
- Pencahayaan, cuaca, dan visibilitas lingkungan

### 2. 🚗 Identifikasi Kendaraan & Karakteristik
- Jenis kendaraan (Mobil / Motor / Bus / Truk / Sepeda)
- Perkiraan warna dominan bodi kendaraan dan tipe/model
- Keterbacaan plat nomor kendaraan (tuliskan jika terbaca, atau sebutkan kondisi jika buram/jauh)

### 3. 👤 Analisis Aktivitas Orang & Perilaku
- Orang yang berada dalam frame (jumlah, estimasi pakaian/warna baju, helm/atribut)
- Aktivitas dan arah pergerakan

### 4. ⚠️ Evaluasi Keamanan & Deteksi Anomali
- Potensi pelanggaran lalu lintas / aturan area (arah berlawanan, parkir sembarangan, helm)
- Potensi ancaman keamanan (penyusupan, mencurigakan, kemacetan, barang tertinggal)

### 5. 💡 Rekomendasi Tindakan Cepat Petugas
- Instruksi praktis untuk operator ruang kontrol CCTV atau petugas keamanan lapangan
"""

DEFAULT_RECEIPT_PROMPT = """Anda adalah Sistem AI Vision Khusus Ekstraksi & Deteksi Struk Kasir / Bukti Transaksi POS.
Analisis gambar struk kasir ini secara mendalam, presisi tinggi, dan secepat kilat.
Sajikan laporan ekstraksi data terstruktur dalam Bahasa Indonesia dengan format Markdown berikut:

### 1. 🏪 Informasi Toko & Merchant
- Nama Toko / Merchant:
- Cabang / Alamat:
- No. Kasir / Petugas:
- ID Terminal / POS:

### 2. 📅 Waktu & Identitas Transaksi
- Tanggal Transaksi:
- Jam / Waktu:
- No. Transaksi / Resi / Struk:

### 3. 🛒 Rincian Item Belanja & Produk
| No | Nama Item / Produk | Qty | Harga Satuan | Subtotal |
|---|---|---|---|---|
(Tuliskan seluruh item produk/belanjaan yang tertera pada struk)

### 4. 💰 Rincian Finansial & Pembayaran
- Subtotal:
- Diskon / Potongan Harga:
- Pajak / PPN:
- Biaya Layanan (jika ada):
- **TOTAL TAGIHAN**:
- Metode Pembayaran (Tunai / QRIS / Kartu Debit / Kartu Kredit / E-Wallet):
- Uang Diterima & Kembalian (jika ada):

### 5. 🔍 Evaluasi Kejelasan & Integritas Dokumen
- Keterbacaan teks (Jelas / Buram / Terlipat)
- Catatan verifikasi keaslian / perhitungan transaksi
"""

class GeminiVisionService:
    def __init__(self):
        self.api_base = "https://generativelanguage.googleapis.com/v1beta/models"

    def get_api_key(self, override_key: Optional[str] = None) -> str:
        key = (override_key or settings.GEMINI_API_KEY or "").strip()
        return key

    def get_model(self, override_model: Optional[str] = None) -> str:
        model = (override_model or getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash") or "gemini-3.6-flash").strip()
        if model.startswith("models/"):
            model = model.replace("models/", "")
        return model


    async def test_connection(self, api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
        """Test API Key validity and access to Gemini Model."""
        key = self.get_api_key(api_key)
        target_model = self.get_model(model)

        if not key:
            return {
                "success": False,
                "message": "Google Gemini API Key belum diisi. Silakan masukkan API Key Anda dari https://aistudio.google.com/app/api-keys"
            }

        url = f"{self.api_base}/{target_model}:generateContent?key={key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": "Pemeriksaan koneksi API Smart CCTV Vision. Jawab hanya dengan: OK - Terhubung"}
                    ]
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload
                )

                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    reply = ""
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            reply = parts[0].get("text", "").strip()

                    return {
                        "success": True,
                        "message": f"Koneksi Google Gemini API ({target_model}) Berhasil! Status: Terverifikasi Aktif.",
                        "model": target_model,
                        "reply": reply
                    }
                else:
                    error_data = {}
                    try:
                        error_data = res.json().get("error", {})
                    except Exception:
                        pass
                    err_msg = error_data.get("message") or f"HTTP {res.status_code}: {res.text[:200]}"
                    return {
                        "success": False,
                        "message": f"Gagal menghubungkan ke Google Gemini API ({res.status_code}): {err_msg}"
                    }
        except httpx.TimeoutException:
            return {
                "success": False,
                "message": "Koneksi ke Google Gemini API waktu habis (Timeout 15 detik). Periksa koneksi internet server."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Terjadi kesalahan koneksi: {str(e)}"
            }

    async def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze an image using Google Gemini Multimodal Vision."""
        key = self.get_api_key(api_key)
        target_model = self.get_model(model)

        if not key:
            return {
                "success": False,
                "message": "Google Gemini API Key belum diatur di Pengaturan Server. Dapatkan kunci API gratis di https://aistudio.google.com/app/api-keys"
            }

        if not image_bytes:
            return {
                "success": False,
                "message": "Gambar tidak tersedia atau kosong untuk dianalisis."
            }

        # Encode image to base64
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        query_prompt = (prompt or DEFAULT_FORENSIC_PROMPT).strip()

        url = f"{self.api_base}/{target_model}:generateContent?key={key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": query_prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_img
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1500
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload
                )

                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        text_parts = [p.get("text", "") for p in parts if "text" in p]
                        full_text = "\n".join(text_parts).strip()
                        return {
                            "success": True,
                            "analysis": full_text,
                            "model": target_model,
                            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                        }
                    else:
                        return {
                            "success": False,
                            "message": "Gemini tidak mengembalikan kandidat teks untuk gambar ini."
                        }
                else:
                    error_data = {}
                    try:
                        error_data = res.json().get("error", {})
                    except Exception:
                        pass
                    err_msg = error_data.get("message") or f"HTTP {res.status_code}: {res.text[:200]}"
                    return {
                        "success": False,
                        "message": f"Google Gemini API Error ({res.status_code}): {err_msg}"
                    }
        except httpx.TimeoutException:
            return {
                "success": False,
                "message": "Permintaan ke Google Gemini waktu habis (30s). Coba ulangi dengan model flash."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Terjadi kesalahan saat memproses analisis: {str(e)}"
            }

gemini_vision_service = GeminiVisionService()
