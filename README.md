# 🐾 PAWGRESS
### Performance Gamification Dashboard
> Streamlit · Google Sheets Backend · v2.5 | Season April

Dashboard gamifikasi performa tim berbasis poin XP, level kucing, streak harian, dan sistem Weekend Allowance — dirancang untuk tim travel agent yang bekerja dengan task booking, QC, dan follow-up.

---

## ✨ Fitur Utama

| Fitur | Deskripsi |
|---|---|
| 📋 My Tasks | Input, edit, dan mark task sebagai Done dengan kalkulasi XP otomatis |
| ✅ QC Antrian | Review dan validasi task rekan tim |
| 🔍 Status QC Saya | Pantau hasil QC task milik sendiri |
| 🏆 Leaderboard | Ranking XP seluruh tim secara real-time |
| ⭐ Quest & Streak | Misi harian/mingguan/bulanan dan evolusi kucing 7 level |
| ⭐ XP Control | Approval XP, Weekend Allowance, dan bonus/penalti manual (Manager) |
| 📊 Performa Tim | Analitik performa per staff (Manager) |
| 📁 Kelola Project | Manajemen project aktif tim (Manager) |
| 🎁 Weekend Allowance | Bonus XP otomatis untuk task di Sabtu, Minggu, dan tanggal merah |

---

## 🐱 Sistem Evolusi Kucing (Level)

| Level | Nama | XP Minimum |
|---|---|---|
| 0 | 🐾 Kitten | 0 XP |
| 1 | 🐱 Kucing Kampung | 100 XP |
| 2 | 🐈 Oyen | 300 XP |
| 3 | 🐈 Kucing Garong | 600 XP |
| 4 | 🐆 Kucing Elite | 1,000 XP |
| 5 | 🐅 Kucing Sultan | 1,800 XP |
| 6 | 👑 King of Paw | 3,000 XP |

---

## 🎁 Weekend & Holiday Allowance

Bonus XP flat **per task Done** di hari libur. Dicatat otomatis ke XP Log dengan status `PENDING`, aktif setelah disetujui Manager.

| Hari | Bonus XP | Bonus Coin |
|---|---|---|
| Sabtu | +15 XP | +5 Coin |
| Minggu | +20 XP | +8 Coin |
| Tanggal Merah | +25 XP | +10 Coin |

Tanggal merah yang sudah terdaftar: 28 hari libur nasional Indonesia 2026.

---

## 🚀 Cara Install & Jalankan

### 1. Clone / Download

```bash
git clone <repo-url>
cd pawgress
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Setup Google Sheets API

**Buat Service Account:**
1. Buka [Google Cloud Console](https://console.cloud.google.com)
2. Buat project baru atau gunakan yang ada
3. Aktifkan **Google Sheets API** dan **Google Drive API**
4. Buat **Service Account** → buat key → download JSON

**Share Spreadsheet:**
- Buka Google Spreadsheet
- Klik Share → tambahkan email service account dengan role **Editor**

### 4. Setup Secrets

Buat file `.streamlit/secrets.toml`:

```toml
[gcp_service_account]
type = "service_account"
project_id = "nama-project-anda"
private_key_id = "key-id"
private_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email = "nama@project.iam.gserviceaccount.com"
client_id = "123456789"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

### 5. Konfigurasi Aplikasi

Edit konstanta di bagian atas `pawgress_app.py`:

```python
SHEET_ID = "ID_SPREADSHEET_ANDA"   # dari URL spreadsheet

ALL_STAFF = {
    "Manager": ["Manager"],
    "Finance": ["Nama1", "Nama2"],
    "Booker":  ["Nama3", "Nama4", "Nama5"],
}

PASSWORDS = {
    "Manager": "password_manager",
    "Nama1":   "nama1123",
    # dst...
}
```

### 6. Jalankan

```bash
streamlit run pawgress_app.py
```

Buka browser: `http://localhost:8501`

---

## 📊 Struktur Google Sheets

Aplikasi otomatis membuat 5 sheet jika belum ada:

| Sheet | Kolom | Fungsi |
|---|---|---|
| **Task Log** | Date, Staff, Role, Task Type, Booking ID, Hotel, Client, Notes, Status, SLA Minutes, XP, Coin, QC Status, QC By, QC Notes, Ref ID, Timestamp, Timestamp Edit | Log semua task |
| **QC Log** | Date, QC By, QC Role, Target Staff, Ref ID, Task Type, QC Status, QC Notes, XP Awarded, Timestamp | Log aktivitas QC |
| **Session Log** | Date, Staff, Role, Login Time, Logout Time, Duration Minutes, Status | Log sesi login |
| **Projects** | Project ID, Name, Category, Deadline, Staff, Target XP, Progress, Status, Created | Manajemen project |
| **XP Log** | Timestamp, Staff, Type, Amount, Reason, Applied By | Log semua XP bonus/penalti/allowance |

---

## ⚙️ Sistem XP

```
XP = (Base + Speed + Accuracy + Streak) × Multiplier
```

| Komponen | Kondisi | Nilai |
|---|---|---|
| Base | Sesuai jenis task | 5–25 XP |
| Speed | ≤ 50% waktu ideal | +15 |
| Speed | ≤ waktu ideal | +10 |
| Speed | ≤ 80% waktu maks | +5 |
| Speed | ≤ waktu maks | 0 |
| Speed | > waktu maks | -10 |
| Accuracy | Selalu | +20 |
| Streak | ≥ 3 hari | +10 |
| Streak | ≥ 7 hari | +25 |
| Streak | ≥ 14 hari | +50 |
| Multiplier Pro | AI type Pro | ×1.2 |
| Multiplier Balanced | AI type Balanced | ×1.0 |
| Multiplier Slow | AI type Slow | ×0.9 |
| Multiplier Risky | AI type Risky | ×0.8 |

---

## 👥 Role & Akses

| Role | Halaman yang Bisa Diakses |
|---|---|
| **Staff (Booker/Finance)** | My Tasks, QC Antrian, Status QC Saya, Leaderboard, Quest & Streak |
| **Manager** | Semua halaman + Dashboard, Session Monitor, Semua Task, XP Control, Kelola Project, Performa Tim, Activity Log |

---

## 📁 Struktur File

```
pawgress/
├── pawgress_app.py       # Aplikasi utama (semua dalam 1 file)
├── requirements.txt      # Dependencies Python
├── README.md             # Dokumentasi ini
└── .streamlit/
    └── secrets.toml      # Kredensial Google (JANGAN di-commit ke git)
```

---

## 🔒 Keamanan

- **Jangan** commit `secrets.toml` ke repository publik
- Tambahkan `.streamlit/secrets.toml` ke `.gitignore`
- Password staff tersimpan di kode — pertimbangkan hash untuk produksi
- Service account hanya perlu akses ke spreadsheet spesifik, bukan seluruh Drive

```gitignore
# .gitignore
.streamlit/secrets.toml
__pycache__/
*.pyc
.env
```

---

## 🛠️ Troubleshooting

| Masalah | Solusi |
|---|---|
| `Gagal koneksi ke Google Sheets` | Cek secrets.toml, pastikan service account punya akses Editor ke spreadsheet |
| `Sheet tidak ditemukan` | Aplikasi otomatis membuat sheet saat pertama login — tunggu sebentar |
| `XP tidak bertambah` | Pastikan task di-mark Done, bukan hanya disimpan |
| `Weekend Allowance tidak muncul` | Cek apakah tanggal di kolom Date Task Log sudah terisi format YYYY-MM-DD |
| `Kucing tidak muncul` | Refresh halaman, pastikan browser mendukung SVG inline |

---

## 📝 Changelog

### v2.5 — Weekend & Holiday Allowance
- ✅ Sistem Weekend Allowance: Sabtu +15 XP, Minggu +20 XP, Tanggal Merah +25 XP per task
- ✅ Banner otomatis di My Tasks saat hari libur aktif
- ✅ Badge 🎁 pada task yang eligible allowance
- ✅ Section baru di XP Control untuk approval allowance per staff
- ✅ Ringkasan allowance mingguan di panel Manager
- ✅ 28 tanggal merah Indonesia 2026 built-in

### v2.4.1 — Bug Fixes
- ✅ Workbook di-cache → koneksi lebih cepat
- ✅ Batch update menggantikan 9 API calls terpisah
- ✅ DataFrame.get() → df["col"] fix
- ✅ Race condition JS canvas → SVG Python-side

### v2.4 — Major Redesign
- ✅ Tema oranye/amber menggantikan navy
- ✅ Evolusi kucing 7 level dengan SVG inline
- ✅ Jalur level horizontal di Quest & Streak
- ✅ Layout sidebar yang lebih rapi

---

*Built with ❤️ for tim travel agent yang tetap semangat kerja bahkan saat weekend 🐾*
