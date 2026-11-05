# Bangkah AI Office

AI Coding Factory kini memiliki antarmuka kantor berbasis web lokal. Owner berdiskusi secara privat dengan Lead Manager, menyetujui arahan, lalu pipeline CrewAI yang sudah ada mengoordinasikan tim spesialis.

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

Virtual Office memiliki 11 lokasi yang tersimpan sebagai ID ruangan terstruktur di SQLite:

- **Ruang Owner** dan **Ruang Meeting**.
- **Ruang Lead Manager** untuk Arman.
- **Ruang Project Manager** untuk Sinta.
- **Ruang Arsitektur** untuk Raka.
- **Ruang Backend** untuk Bima.
- **Ruang API Studio** untuk Naya.
- **Ruang Frontend** untuk Dira.
- **Ruang Quality Assurance** untuk Tika.
- **Area Santai** dan **Dapur**.

Database lama dimigrasikan agar Arman/Sinta dan Raka/Bima tidak lagi berbagi satu ID ruangan. Perpindahan manual setelah migrasi tetap dipertahankan.

Papan tugas dan linimasa membaca status `.factory/state.json` serta `logs/factory.log`. Server menerima satu pipeline coding pada satu waktu; riwayat chat langsung masih tersimpan selama proses server hidup. Data kantor (ruangan, tugas, rapat, event, dan interaksi) persisten di SQLite.

## Virtual Office interaktif

Halaman **Virtual Office** menggunakan lingkungan kantor isometrik 2.5D bergaya diorama: ruang privat, meeting, workstation, partisi kaca, jendela, rak, pantry, printer, lounge, dan tanaman. Ilustrasi bangunan adalah layer visual; karakter game 3D-style, label ruangan, indikator okupansi, dan percakapan berada pada layer UI terpisah agar tetap interaktif dan tersinkron dengan database. Palet ruangan memakai warna pastel lembut. Nama ruangan, jumlah penghuni, nama karakter, dan aktivitas idle disembunyikan sampai pointer hover/focus agar peta tidak berserakan. Fitur operasionalnya:

- Klik ruangan untuk melihat penghuni, status, dan pilihan memindahkan setiap karyawan.
- Seret karakter ke ruangan tujuan atau gunakan dropdown pada panel inspector.
- Pilih **Pindahkan semua ke sini** untuk memindahkan seluruh tim.
- Perpindahan dicatat ke SQLite; karakter berjalan melalui waypoint koridor menuju posisi ruangan baru ketika snapshot backend menunjukkan perubahan lokasi. Animasi karakter meliputi idle, langkah kaki saat berjalan, gerakan tangan saat bekerja, serta gerakan bicara dan indikator mendengarkan.
- Klik karakter untuk membuka chat langsung dengan karyawan.
- Avatar Owner memakai karakter tersendiri. Gunakan **WASD / tombol panah** untuk berjalan, klik lantai untuk bergerak ke titik pilihan, dan tekan **E** saat berada dekat objek interaktif.
- Objek interaktif prototipe: workstation (membuka Pekerjaan/Knowledge Base), coffee station, meja meeting (Command Center/Ruang Chat), lounge, dan titik arsip (riwayat aktivitas/Knowledge Base).
- Posisi dan interaksi Owner disimpan melalui `/api/office/player` ke SQLite dan dicatat sebagai event perusahaan.
- Avatar agen dan Owner menggunakan aset 3D-style transparan di `web/assets/avatars/`; gerakan saat ini memakai animasi CSS ringan, belum menggunakan rig/skeleton 3D.
- Ruangan, status karyawan, okupansi, dan panel komunikasi diperbarui dari `/api/status`.

## Status bicara dan percakapan antar-karyawan

Setiap briefing rapat, balasan antar-agen, dan handoff dari pipeline disimpan ke tabel `employee_interactions`. API status mengirim pengirim, penerima, isi pesan, ruangan, dan masa aktif interaksi. Virtual Office menampilkan bubble pesan pada pembicara, indikator mendengarkan pada penerima, garis koneksi antar-karakter, dan feed **Live Communication**. Pesan yang kedaluwarsa tidak lagi ditampilkan sebagai percakapan aktif.

## AI Orchestrator, RAG, dan percakapan antar-karyawan

Chat dengan Arman sekarang melewati `core/orchestrator.py`. Arman meminta model menyusun JSON plan, kemudian backend hanya menjalankan tool yang masuk allowlist dan memvalidasi argumennya melalui `OfficeTools`. Fallback deterministik tetap tersedia untuk instruksi umum seperti mengumpulkan karyawan, membuat rapat, membuat laporan mingguan, dan menyiapkan pembagian kerja proyek.

Untuk memulai pipeline coding, Arman menyiapkan tugas per role dan meminta persetujuan melalui tombol **Mulai pipeline coding**. Persetujuan tersebut menjalankan `AICodingFactory`; status tugas dan interaksi antar-agen dicatat ke database. Tindakan kantor yang tidak menjalankan kode (pindah ruang, membuat rapat, membuat laporan) dijalankan langsung dan hasilnya dikembalikan ke chat.

### RAG lokal

- Dokumen disimpan sebagai chunks di SQLite.
- Bila Ollama embedding tersedia, sistem memakai vector cosine similarity.
- Bila model embedding tidak tersedia, retrieval turun ke SQLite FTS5/BM25 (atau LIKE bila SQLite tanpa FTS5).
- Tambahkan dokumen dari menu **Knowledge Base** atau endpoint `POST /api/knowledge/documents` dengan JSON `{ "title": "...", "source": "...", "content": "..." }`.
- Cari dokumen melalui `GET /api/knowledge/search?q=...`.
- Roster dan README diindeks otomatis sebagai dokumen awal.
- Dokumen Markdown/text/YAML di `docs/`, `reports/`, dan `workspace/projects/` juga ditemukan dan diindeks otomatis. File baru atau versi file yang berubah akan menjadi sumber index baru.

RAG adalah lapisan pencarian konteks, bukan mesin untuk menjalankan tindakan. Instruksi operasional ditangani oleh Orchestrator dan tool yang tervalidasi; RAG menyediakan dokumen/riwayat yang relevan agar keputusan agen lebih grounded.

Untuk semantic retrieval, jalankan:

```bash
ollama pull nomic-embed-text
```

Lalu pastikan `OLLAMA_EMBED_MODEL=nomic-embed-text` dan `OLLAMA_URL` menunjuk ke instance Ollama, kemudian restart Bangkah. Jika model embedding belum tersedia, RAG masih bekerja dengan full-text retrieval, tetapi pemahaman semantiknya lebih terbatas.


## Bangkah Company Simulator

Virtual Office menggunakan mode immersive dengan navigasi ikon dan panel detail yang hanya dibuka ketika diperlukan. Nama ruangan, okupansi, nama karyawan dan aktivitas idle ditampilkan saat hover/focus, bukan terus-menerus di atas peta.

Karakter agen dan Owner menggunakan aset gambar 3D-style yang terpisah dari lingkungan kantor. Owner dapat berjalan memakai **WASD / tombol panah**, klik lantai untuk bergerak, dan menekan **E** untuk berinteraksi dengan workstation, coffee station, meja meeting, lounge, serta titik arsip. Posisi Owner dan event interaksi tersimpan di SQLite melalui `/api/office/player`. Workstation membuka halaman Pekerjaan/Knowledge Base; meeting membuka Command Center/Ruang Chat; titik arsip mengarah ke riwayat aktivitas dan Knowledge Base yang tersedia saat ini.

### Legacy browser 3D prototype

Bagian 3D berbasis Three.js di folder `backend/web/` adalah prototype browser lama yang dipertahankan sebagai referensi dan fallback eksperimen. Ia bukan client utama untuk pengembangan baru. Client 3D utama sekarang adalah proyek native Godot di folder `godot/` pada root repository, dengan dokumentasi desain dan integrasi di `docs/`.

Untuk menjalankan client utama, buka `godot/project.godot` melalui Godot 4.3+. Kamera default first-person; tekan `V` untuk beralih ke third-person follow camera. Detail kontrol dan batas integrasi ada di root `README.md`, `docs/CONTROLS-AND-CAMERA.md`, serta `docs/BACKEND-INTEGRATION.md`.

Rutinitas idle pada prototype lama bersifat kosmetik dan tidak mengubah status pekerjaan. Prototype Three.js lama masih memakai polling dan API legacy. Jangan menganggapnya memenuhi SRS v1.3 atau menjadi implementasi Paper Workflow / transactional approval.

Prinsip produk tetap sama: Bangkah adalah perusahaan sungguhan. Project, source code, task, meeting, laporan, keputusan, dan arsip harus tetap menjadi data backend yang nyata. Dunia game hanya menjadi antarmuka untuk mengakses dan mengamati pekerjaan tersebut.


## Company Operations API (Final Desktop MVP 1.0)

The native Godot client is the primary game interface. The legacy browser office remains for compatibility. The Python backend now also exposes persisted department, employee, project, task, meeting, Paper, print job, approval, outbox, audit / event cursor and usage APIs. See `../docs/API-REFERENCE.md` for request and response contracts.

Important operational behavior:

- Task completion requires evidence with a non-empty reference.
- Meeting completion requires minutes; decisions and follow-ups are stored.
- Paper can be rendered to PDF through ReportLab and downloaded by the Godot client.
- Email and website deployment are queued only after explicit approval. A separate outbox execute action is required.
- `unknown` external delivery results require manual reconciliation. Purchase actions remain manual and are never reported automatically as completed.
- `BANGKAH_API_TOKEN` protects all API GET / POST / download endpoints when configured. The server binds to loopback only; use a TLS reverse proxy for remote access.

Optional integration variables for SMTP, deployment webhook and API token are listed in `.env.example`. Do not commit `.env`.
