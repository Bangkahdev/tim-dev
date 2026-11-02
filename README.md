# Atelier AI Office

AI Coding Factory kini memiliki antarmuka kantor berbasis web lokal. Owner berdiskusi secara privat dengan Lead Manager, menyetujui arahan, lalu pipeline CrewAI yang sudah ada mengoordinasikan tim spesialis.

Backend `backend/` adalah sumber kebenaran untuk organisasi, task, paper, persetujuan, audit, dan event. UI lama tetap kompatibel; Command Center baru memakai API domain di bawah ini.

## Backend Bangkah

- **Sesi Owner**: `POST /api/session` (lokal, token `API_AUTH_TOKEN` bila diisi). Semua mutasi memakai `Authorization: Bearer <token>`.
- **Organisasi**: `/api/departments`, `/api/employees`.
- **Task**: `/api/tasks`, `/api/tasks/{id}/transition`. Hanya matriks 4.6.1 yang sah; `COMPLETED` hanya ditetapkan backend setelah bukti PRJ-11 valid.
- **Rapat**: `/api/meetings`, `/api/meetings/{id}/run`, `/api/meetings/{id}/interject`. Notulen disimpan ke `docs/meetings/`, diindeks ke knowledge base, dan dikirim ke tray sebagai paper `meeting_minutes`.
- **Proyek paralel**: `/api/projects` (antrean dan batas `MAX_CONCURRENT_PROJECTS`), `request-start` (butuh persetujuan Owner), `complete` (arsip akhir + task Promosi + laporan), `fail`, dan `report`/`report/export`. Proyek `QUEUED` naik otomatis saat slot kosong.
- **Laporan dan aktivitas**: `/api/reports/divisions` (kinerja per divisi), `/api/reports/divisions/{id}` dan `export` (PDF), `/api/activity` (filter divisi/karyawan/jenis), `/api/usage` (per karyawan, model, proyek, dan hari), `POST /api/usage/record`.
- **Command Center**: `/api/command-center` merangkum proyek, task, tray, karyawan, usage, kinerja divisi, dan audit; `/api/employees/{id}/monitor` menampilkan state, task aktif, file terakhir, terminal, dan hasil tes.
- **Paper dan persetujuan**: `/api/papers` (tray, dengan `limit`/`overflow`), `print`, `deliver`, `decision`, `revise`, `pdf`; `/api/approvals`, `/api/approvals/{id}/execute`.
- **Email**: `/api/inbox` (baca), `POST /api/inbox/sync` (tarik IMAP; juga berkala tiap `EMAIL_SYNC_MINUTES`), `/api/outbox` (draf), `POST /api/outbox/process`. Draf menjadi Paper dan hanya dikirim setelah Owner menyetujui; email masuk selalu ditandai tak tepercaya.
- **Website**: `/api/website/deployments` (paket rilis), `publish`, `rollback`, `reconcile`. Publikasi hanya setelah persetujuan, dengan backup otomatis dan pemeriksaan pasca-publikasi.
- **Sekretaris**: `/api/secretary/command` (kirim `preview: true` untuk pratinjau rencana sebelum eksekusi), `/api/secretary/agenda`.
- **Audit, usage, event**: `/api/audit`, `/api/usage`, `/api/events`, `/ws/events`.

Aturan penting:

- Tool hanya dapat dipanggil lewat allowlist per karyawan (`backend/tools.py`).
- Approval mengikat hash payload; payload yang berubah membatalkan persetujuan.
- Audit append-only dijaga trigger SQLite.
- Event memiliki ID monoton dan mendukung replay/gap.
- Subprocess memakai env allowlist dan redaksi rahasia (`backend/sandbox.py`).

## Menjalankan backend dan tes

```powershell
pip install -r requirements.txt
$env:BANGKAH_SKIP_MODEL_CHECK="1"   # opsional saat tidak memakai Ollama
python office_server.py             # http://127.0.0.1:8765
python -m pytest -q
```

Database default `data/bangkah.db`; PDF di `data/prints/`; notulen di `docs/meetings/`; backup website di `data/website-backups/`. Ubah lewat variabel `BANGKAH_*` di `.env.example`. `PAPER_TRAY_LIMIT` (default 15) membatasi paper yang tampil di tray; sisanya dilaporkan sebagai `overflow`. `MAX_MEETING_ROUNDS` (default 3) dan `MAX_MEETING_TOKENS` (default 4000) membatasi rapat.

Email dan website memakai kredensial `.env` (`EMAIL_*`, `WEBSITE_*`). Tanpa kredensial email, draf tetap dibuat sebagai Paper tetapi pengiriman ditolak sampai akun dikonfigurasi. Website dipublikasikan dengan menyalin `BANGKAH_WEBSITE_SOURCE_DIR` ke `BANGKAH_WEBSITE_DEPLOY_DIR` setelah backup; setiap rilis menulis penanda `.bangkah-release` untuk rekonsiliasi dan rollback.

Dokumen yang mengandung pola rahasia (API key, password, token, private key) ditolak saat ditambahkan ke knowledge dan dilewati saat pencarian (KNW-04).

## Menjalankan

1. Pasang dependensi: `pip install -r requirements.txt`.
2. Salin `.env.example` menjadi `.env`, lalu atur model (lihat bagian **Konfigurasi model**).
3. Jika memakai model `ollama/...`, jalankan Ollama dan pastikan modelnya sudah di-pull.
4. Dari folder proyek, jalankan `python office_server.py`.
5. Buka `http://127.0.0.1:8765` di browser.

Server hanya bind ke `127.0.0.1`. Tombol **Setujui & mulai pekerjaan** mengirim hasil diskusi ke pipeline yang membuat proyek, menjalankan QA, dan menulis laporan ke folder `reports/`.

## Konfigurasi model

Semua pengaturan model ada di `.env` (dibaca oleh `config.py`). Format model: `provider/nama-model`.

| Variabel | Fungsi |
| --- | --- |
| `MODEL_MANAGER` | Lead Manager dan COO |
| `MODEL_CODER` | Architect, Backend, Frontend |
| `MODEL_SPECIALIST` | API Specialist dan QA |
| `MODEL_<ROLE>` | Override per karyawan: `LEAD`, `COO`, `ARCHITECT`, `BACKEND`, `API`, `FRONTEND`, `QA` |
| `OLLAMA_URL` | Alamat Ollama (default `http://localhost:11434`) |
| `MAX_REPAIR_ROUNDS` | Batas ronde perbaikan otomatis |
| `*_API_KEY` | API key provider cloud yang dipakai |

Model lokal dan cloud boleh dicampur. Contoh: Lead dan Backend di cloud, QA tetap di Ollama.

**Catatan:**

- Jangan commit `.env`. File itu sudah ada di `.gitignore`.
- Model cloud berarti kode dan percakapan dikirim ke provider. Mode "sepenuhnya lokal" hanya berlaku jika semua model memakai `ollama/...`.
- Pemakaian cloud berbayar per token. Satu run melibatkan banyak agen dan putaran perbaikan, jadi batasi dengan `MAX_REPAIR_ROUNDS`.

## Ruang kantor

- **Ruang Owner**: ruang khusus untuk diskusi dan persetujuan pekerjaan.
- **Lead Manager**: memahami kebutuhan, menyusun arahan, dan mengoordinasikan tim.
- **COO / Project Manager**: perencanaan.
- **System Architect**: arsitektur.
- **Backend**, **API**, dan **Frontend**: implementasi per spesialisasi.
- **Quality Assurance**: pemeriksaan dan laporan QA.

Papan tugas dan linimasa membaca status `.factory/state.json` serta `logs/factory.log`, diperbarui otomatis. Untuk sekarang server menerima satu pekerjaan berjalan pada satu waktu; riwayat chat disimpan selama server hidup.

Karakter kantor memakai animasi CSS untuk mengetik saat tugas aktif dan mengambil jeda kopi saat idle, dengan gerakan dihentikan bila perangkat meminta reduced motion. Ruang Kesehatan AI menyimpan nama, role, model, aktivitas, jumlah tugas, durasi kerja, serta penggunaan token per karyawan di `logs/employee_health.json`. Token ditampilkan hanya jika CrewAI/provider melaporkan metriknya; bila tidak, UI menyebutnya belum tersedia alih-alih menampilkan estimasi.
