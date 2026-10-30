# Atelier AI Office

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

- **Ruang Owner**: ruang khusus untuk diskusi dan persetujuan pekerjaan.
- **Lead Manager**: memahami kebutuhan, menyusun arahan, dan mengoordinasikan tim.
- **COO / Project Manager**: perencanaan.
- **System Architect**: arsitektur.
- **Backend**, **API**, dan **Frontend**: implementasi per spesialisasi.
- **Quality Assurance**: pemeriksaan dan laporan QA.

Papan tugas dan linimasa membaca status `.factory/state.json` serta `logs/factory.log`, diperbarui otomatis. Untuk sekarang server menerima satu pekerjaan berjalan pada satu waktu; riwayat chat disimpan selama server hidup.

Karakter kantor memakai animasi CSS untuk mengetik saat tugas aktif dan mengambil jeda kopi saat idle, dengan gerakan dihentikan bila perangkat meminta reduced motion. Ruang Kesehatan AI menyimpan nama, role, model, aktivitas, jumlah tugas, durasi kerja, serta penggunaan token per karyawan di `logs/employee_health.json`. Token ditampilkan hanya jika CrewAI/provider melaporkan metriknya; bila tidak, UI menyebutnya belum tersedia alih-alih menampilkan estimasi.
