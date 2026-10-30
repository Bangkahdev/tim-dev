# Atelier AI Office

AI Coding Factory kini memiliki antarmuka kantor berbasis web lokal. Owner berdiskusi secara privat dengan Lead Manager, menyetujui arahan, lalu pipeline CrewAI yang sudah ada mengoordinasikan tim spesialis.

## Menjalankan

1. Pasang dependensi yang tercantum di `requirements.txt`.
2. Jalankan Ollama dan pastikan model `o` serta `llama3.2:3b` tersedia.
3. Dari folder proyek, jalankan `python office_server.py`.
4. Buka `http://127.0.0.1:8765` di browser.

Server hanya bind ke `127.0.0.1`. Percakapan dengan manager memakai model manager lokal. Tombol **Setujui & mulai pekerjaan** mengirim hasil diskusi ke pipeline yang membuat proyek, menjalankan QA, dan menulis laporan ke folder yang sama seperti sebelumnya.

## Ruang kantor

- **Ruang Owner**: ruang khusus untuk diskusi dan persetujuan pekerjaan.
- **Lead Manager**: memahami kebutuhan, menyusun arahan, dan mengoordinasikan tim.
- **COO / Project Manager**: perencanaan.
- **System Architect**: arsitektur.
- **Backend**, **API**, dan **Frontend**: implementasi per spesialisasi.
- **Quality Assurance**: pemeriksaan dan laporan QA.

Papan tugas dan linimasa membaca status `.factory/state.json` serta `logs/factory.log`, diperbarui otomatis. Untuk sekarang server menerima satu pekerjaan berjalan pada satu waktu; riwayat chat disimpan selama server hidup.
