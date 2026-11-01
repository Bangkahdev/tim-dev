SRS — Bangkah Company Simulator
Spesifikasi Kebutuhan Perangkat Lunak · Versi 1.3 (Final) · 31 Oktober 2026 · Pemilik produk: Owner Bangkah
1. Pendahuluan
1.1 Tujuan
Dokumen ini menetapkan kebutuhan fungsional dan non-fungsional Bangkah Company Simulator, yaitu game simulator perusahaan yang sekaligus menjadi antarmuka kerja untuk perusahaan sungguhan yang dijalankan oleh karyawan AI. Dokumen menjadi acuan pengembangan, pengujian, dan penerimaan. Pembaca: Owner, pengembang, dan penguji.
1.2 Ruang lingkup
Owner (pengguna manusia tunggal, posisi tertinggi) berjalan di kantor virtual 3D, berinteraksi dengan karyawan AI dan fasilitas kantor, memberi perintah, mengadakan rapat, dan mengamati pekerjaan nyata. Fokus utama perusahaan adalah rekayasa perangkat lunak. Divisi lain (misalnya Promosi) bekerja pada hasil proyek setelah proyek selesai. Perusahaan memiliki email dan website asli; kredensialnya disimpan di .env.
Di luar lingkup versi 1.0: multiplayer, build mobile, monetisasi, pengguna manusia selain Owner, serta pengiriman email atau publikasi website tanpa persetujuan Owner.
1.3 Definisi dan singkatan
Istilah
Arti
Owner
Pengguna manusia, pimpinan tertinggi perusahaan
Karyawan AI
Agen berbasis LLM dengan peran, persona, dan izin tool tertentu
Sekretaris
Karyawan AI yang menjadi pintu utama perintah Owner
Orchestrator
Modul backend yang mengubah instruksi menjadi rencana tool tervalidasi
Tool
Aksi backend dalam allowlist (pindah ruang, buat task, kirim draf email, dll.)
Persetujuan (Approval)
Konfirmasi eksplisit Owner sebelum aksi berdampak keluar dijalankan
WorldEvent
Catatan kejadian di dunia/kantor yang tersimpan di database
RAG
Pencarian konteks dari dokumen perusahaan
M / S / C
Prioritas: Must (wajib), Should (sebaiknya), Could (opsional)
1.4 Referensi
README.md (root), backend/README.md, backend/docs/BANGKAH_COMPANY_SIMULATOR_ROADMAP.md, serta kode di backend/ dan godot/.
1.5 Prinsip produk (mengikat seluruh kebutuhan)
• P1. Kantor adalah antarmuka, bukan pengganti sistem nyata. Proyek, kode, task, rapat, laporan, dan arsip adalah data backend yang nyata.
• P2. Tidak ada visual kerja tanpa kejadian nyata: status working hanya bila ada task atau sesi aktif; bubble chat hanya dari interaksi tersimpan; karakter ke meja kerja hanya karena task atau perintah.
• P3. Aksi berdampak keluar (email, website, biaya di atas batas) selalu melalui persetujuan Owner.
• P4. LLM mengusulkan; kode tervalidasi mengeksekusi (allowlist).
• P5. Rahasia tidak pernah masuk prompt, RAG, log, respons API, maupun lingkungan subprocess agen.
• P6. Semua tindakan dan keputusan penting tercatat di audit log; pergerakan karakter disimpan sebagai state berkala, bukan sebagai audit.
2. Deskripsi Umum
2.1 Arsitektur
• Klien Godot 4.3+ (renderer GL Compatibility): dunia 3D, input, dan panel UI. Tidak menyimpan logika bisnis; mode offline hanya untuk menjelajah.
• Backend Python (office_server): API HTTP/WebSocket, Orchestrator, OfficeTools, pipeline CrewAI, SQLite, RAG, dan lapisan integrasi.
• Layanan eksternal: LLM (Ollama lokal atau cloud via litellm), email (IMAP/SMTP), website perusahaan.
2.2 Aktor
Aktor
Peran
Owner
Memberi perintah, menyetujui aksi, berjalan di kantor, menghadiri rapat
Sekretaris (AI)
Menerima perintah, menjadwalkan, merangkum, menyusun draf, mengelola antrean persetujuan
Manajer Divisi (AI)
Memecah tugas dan mengawasi anggota divisinya
Karyawan AI
Mengerjakan task sesuai peran dan izin tool
Sistem eksternal
LLM, server email, website
2.3 Kondisi saat ini dan target
Area
Saat ini
Target
Organisasi
7 karyawan engineering, roster tertulis di kode
Departemen dan karyawan di database, multi-divisi
Sekretaris
Tidak ada di backend (Mira hanya di Godot)
Agen Sekretaris sebagai gerbang perintah
Rapat
Record dan briefing
Rapat multi-agen, notulen, task turunan
Proyek
Satu pipeline pada satu waktu
Proyek paralel, dependensi lintas divisi
Email
Belum ada
Inbox/outbox dengan persetujuan
Website
Belum ada
Publikasi dengan persetujuan dan rollback
Objek
Workstation, kopi, meeting, lounge, arsip
Ditambah printer, layar komputer, meja Sekretaris
Riwayat chat
Hanya selama proses server hidup
Persisten di database
Sinkronisasi
Polling 3,5 detik
WebSocket
Keamanan
Bind localhost; seluruh env diteruskan ke subprocess
Env disaring, token API, redaksi rahasia
2.4 Lingkungan operasi
Desktop Windows/Linux, Godot 4.3+, Python 3.10+ (konfirmasi terhadap versi CrewAI yang dipakai), SQLite, Ollama opsional. Backend bind ke 127.0.0.1 secara default.
2.5 Batasan, asumsi, ketergantungan
• Satu Owner; backend berjalan di mesin Owner.
• Owner memiliki domain, akun email, dan akses deploy website.
• Model lokal kecil terbatas kualitasnya; model cloud berbayar per token dan mengirim data ke penyedia.
• Antarmuka berbahasa Indonesia.
• Bergantung pada CrewAI, litellm, Godot, dan layanan email/hosting pilihan Owner.
3. Struktur Organisasi Target
Divisi
Pimpinan
Anggota
Status
Eksekutif
Owner
Sekretaris
Sekretaris baru
Front Office
Sekretaris
Mira (Resepsionis): sambutan tamu, pencatatan pesan masuk
Didaftarkan ke backend
Engineering
Arman (Lead Manager)
Sinta (COO/PM), Raka (Arsitek), Bima (Backend), Naya (API), Dira (Frontend), Tika (QA)
Ada
Promosi
Manajer Promosi
Content writer, social media (jumlah dan peran ditentukan Owner)
Baru
Divisi lain
Ditentukan Owner
Ditentukan Owner
Opsional
Rantai komando: Owner → Sekretaris → Manajer Divisi → Karyawan. Owner tetap bisa memerintah siapa pun secara langsung. Semua jalur, termasuk perintah langsung, melewati Orchestrator untuk validasi dan pencatatan. Sekretaris dan Mira adalah dua agen terpisah dengan peran, izin, dan prompt berbeda.
4. Kebutuhan Fungsional
Kolom Status: Ada (sudah di kode), Sebagian, Baru.
4.1 Dunia dan kontrol (WLD)
ID
Kebutuhan
Prior.
Status
WLD-01
Owner bergerak third-person (WASD/panah), lari (Shift), lompat (Space), kamera mouse dan zoom
M
Ada
WLD-02
Tabrakan dengan dinding, partisi, dan furnitur
M
Ada
WLD-03
NPC berjalan antar ruang dengan navmesh dan menghindari rintangan
S
Sebagian
WLD-04
NPC hanya menuju meja kerja bila ada task atau perintah nyata; gerak ambient ditandai kosmetik
M
Sebagian
WLD-05
Posisi, ruangan, dan aktivitas Owner tersimpan dan dipulihkan saat game dibuka
M
Ada
WLD-06
Mode offline: kantor dapat dijelajahi saat backend mati, dengan indikator koneksi
M
Ada
WLD-07
Siklus siang/malam dan jam kerja perusahaan
C
Baru
WLD-08
Posisi Owner dan NPC disimpan sebagai state berkala (maksimal sekali per 5 detik), bukan sebagai record audit
M
Baru
4.2 Interaksi objek (OBJ)
Semua objek diakses dengan tombol E dalam jarak interaksi dan menampilkan prompt.
ID
Kebutuhan
Prior.
Status
OBJ-01
Komputer Owner membuka Company Command Center (bagian 4.14), termasuk daftar proyek, task, status, file, dan hasil QA
M
Sebagian
OBJ-02
Meja meeting membuat atau menggabung rapat nyata
M
Sebagian
OBJ-03
Mesin kopi: aksi Owner dicatat sebagai event; karyawan di pantry dapat diajak bicara
S
Sebagian
OBJ-04
Printer kantor menghasilkan dokumen nyata (laporan task, proposal, notulen) sebagai file PDF di folder keluaran; setiap cetakan tercatat sebagai PrintJob dan dapat dipakai karyawan maupun Owner
M
Baru
OBJ-05
Rak arsip menelusuri arsip proyek, laporan, dan keputusan (baca saja)
M
Sebagian
OBJ-06
Lounge: istirahat dan event kehadiran
C
Ada
OBJ-07
Meja Sekretaris membuka agenda, persetujuan tertunda, dan ringkasan harian
M
Baru
OBJ-08
Komputer karyawan menampilkan pekerjaan terbaru karyawan tersebut (baca saja)
S
Baru
OBJ-09
Setiap interaksi objek dicatat sebagai WorldEvent
M
Ada
OBJ-10
Tray masuk di meja Owner menampung kertas dari karyawan; tekan E untuk mengambil dan memeriksa satu per satu (bagian 4.16)
M
Baru
OBJ-11
Ruang Owner memiliki meja kerja, komputer monitoring (Command Center), dan tray masuk; letaknya berdekatan dengan meja Sekretaris
M
Sebagian
4.3 Organisasi dan karyawan (ORG)
ID
Kebutuhan
Prior.
Status
ORG-01
Departemen dan karyawan disimpan di database; roster awal berupa seed
M
Baru
ORG-02
Owner dapat menambah, mengubah, dan menonaktifkan karyawan dan departemen lewat panel
S
Baru
ORG-03
Atribut karyawan: nama, jabatan, departemen, atasan, model LLM, skill, izin tool, ruang/meja, avatar
M
Sebagian
ORG-04
Tugas mengalir mengikuti rantai komando
M
Baru
ORG-05
Model per karyawan lewat .env (MODEL_<ROLE>) tetap didukung; kunci API tidak pernah disimpan di database
M
Ada
ORG-06
Migrasi data lama tanpa kehilangan riwayat
M
Sebagian
4.4 Sekretaris (SEC)
ID
Kebutuhan
Prior.
Status
SEC-01
Sekretaris terdaftar sebagai agen dengan ruang dan meja dekat ruang Owner
M
Baru
SEC-02
Perintah bahasa natural Owner diterima Sekretaris, yang menentukan penerima dan membuat task
M
Baru
SEC-03
Mengelola jadwal rapat, tenggat, dan pengingat Owner
M
Baru
SEC-04
Ringkasan harian/mingguan: kemajuan, hambatan, persetujuan menunggu
M
Baru
SEC-05
Tumpukan persetujuan: semua aksi berdampak keluar menjadi proposal kertas di tray Owner; Sekretaris mengurutkan menurut prioritas dan merangkum bila melebihi batas
M
Baru
SEC-06
Menyusun draf email dan balasan; tidak pernah mengirim tanpa persetujuan
M
Baru
SEC-07
Memilah email masuk (kategori, prioritas, ringkasan) dan mengusulkan task
S
Baru
SEC-08
Bila instruksi ambigu, mengajukan satu pertanyaan klarifikasi sebelum bertindak
S
Baru
SEC-09
Sekretaris dan Resepsionis Mira adalah dua agen terpisah dengan peran, izin tool, dan prompt berbeda
M
Baru
4.5 Perintah dan orkestrasi (CMD)
ID
Kebutuhan
Prior.
Status
CMD-01
Orchestrator menghasilkan rencana JSON; hanya tool allowlist dengan argumen tervalidasi yang dijalankan
M
Ada
CMD-02
Tool minimal: pindah karyawan, buat/ubah task, buat rapat, laporan; baru: buat proyek, draf email, ajukan publikasi website, cari knowledge
M
Sebagian
CMD-03
Fallback deterministik bila LLM gagal
M
Ada
CMD-04
Rencana berdampak ditampilkan ke Owner sebagai pratinjau sebelum dijalankan
M
Sebagian
CMD-05
Perintah langsung ke karyawan lewat percakapan tatap muka di game
M
Ada
CMD-06
Semua perintah, termasuk perintah langsung Owner ke karyawan, melewati Orchestrator untuk validasi dan pencatatan
M
Baru
CMD-07
Izin tool per karyawan ditegakkan di backend: pemanggilan di luar izin ditolak apa pun isi prompt atau keluaran LLM
M
Baru
4.6 Proyek dan task (PRJ)
ID
Kebutuhan
Prior.
Status
PRJ-01
Proyek nyata: id, nama, divisi pemilik, path workspace/repo, status, deliverable
M
Sebagian
PRJ-02
Pipeline coding (Arsitek, Backend/API/Frontend, QA, tinjauan Lead, perbaikan hingga MAX_REPAIR_ROUNDS) berjalan setelah persetujuan Owner
M
Ada
PRJ-03
Beberapa proyek berjalan paralel dengan antrean dan batas konkurensi yang dapat dikonfigurasi
S
Baru
PRJ-04
Task memiliki penerima, prioritas, status, dependensi, kriteria penerimaan, dan bukti (file, hasil tes)
M
Sebagian
PRJ-05
Proyek Engineering selesai memicu usulan task untuk divisi lain (misalnya Promosi)
S
Baru
PRJ-06
Eksekusi perintah proyek terbatas pada allowlist executable, direktori proyek, dan timeout
M
Ada
PRJ-07
Proyek selesai di-snapshot ke arsip tak-berubah beserta laporan akhir dan bukti tes
S
Baru
PRJ-08
Status working konsisten antara backend dan game, hanya selama sesi kerja nyata
M
Ada
PRJ-09
Task hanya dapat berstatus selesai bila bukti (file, hasil tes, atau tautan commit) terlampir
M
Baru
PRJ-10
Status task: PENDING, IN_PROGRESS, REVIEW, QA, COMPLETED; alternatif BLOCKED dan FAILED. Transisi yang sah didefinisikan di backend dan status lama dipetakan saat migrasi
M
Baru
PRJ-11
COMPLETED hanya ditetapkan backend setelah bukti tervalidasi. Kode: file ada dan hasil tes dengan exit code 0 atau commit yang dapat diverifikasi. Non-kode: file ada dan peninjauan Manajer atau Owner. Karyawan AI tidak dapat menetapkannya sendiri
M
Baru
PRJ-12
BLOCKED dan FAILED memiliki pemulihan: percobaan ulang hingga MAX_REPAIR_ROUNDS, lalu eskalasi ke Manajer divisi
M
Baru
PRJ-13
Matriks transisi status task (bagian 4.6.1) ditegakkan backend; transisi di luar matriks atau oleh pelaku yang tidak sah ditolak dan dicatat
M
Baru
4.6.1 Matriks transisi status task
Dari
Ke
Pelaku sah
Syarat
PENDING
IN_PROGRESS
Backend, atas penugasan
Penerima ditetapkan dan dependensi selesai
IN_PROGRESS
REVIEW
Karyawan penerima
Bukti awal terlampir
REVIEW
IN_PROGRESS
Manajer divisi
Catatan revisi wajib
REVIEW
QA
Manajer divisi
Tinjauan lulus
QA
COMPLETED
Backend
Bukti tervalidasi sesuai PRJ-11
QA
IN_PROGRESS
Backend
Tes gagal; hitungan percobaan bertambah
IN_PROGRESS, REVIEW, QA
BLOCKED
Karyawan atau backend
Alasan dan penghalang dicatat
BLOCKED
IN_PROGRESS
Manajer atau backend
Penghalang teratasi
IN_PROGRESS, QA
FAILED
Backend
Batas MAX_REPAIR_ROUNDS tercapai atau timeout
FAILED
IN_PROGRESS
Manajer divisi atau Owner
Percobaan ulang dengan catatan; hanya mereka yang dapat mereset hitungan percobaan
Task FAILED yang tidak ditangani Manajer dalam 24 jam dieskalasikan Sekretaris ke Owner sebagai proposal kertas. Karyawan AI tidak dapat melakukan transisi selain yang tercantum untuknya.
4.7 Rapat (MTG)
ID
Kebutuhan
Prior.
Status
MTG-01
Membuat rapat: judul, agenda, peserta, ruang, waktu
M
Sebagian
MTG-02
Peserta AI berkumpul di ruang meeting dan berdiskusi bergiliran sesuai agenda dengan jumlah putaran terbatas
M
Baru
MTG-03
Owner dapat bergabung dan menyela lewat chat; pesannya masuk transkrip
M
Baru
MTG-04
Output rapat: transkrip, notulen, keputusan, dan tindak lanjut sebagai task usulan
M
Baru
MTG-05
Notulen tersimpan sebagai dokumen dan terindeks ke knowledge base
S
Baru
MTG-06
Batas putaran dan token per rapat
M
Baru
4.8 Komunikasi (CHT)
ID
Kebutuhan
Prior.
Status
CHT-01
Chat 1-ke-1 dengan karyawan; riwayat persisten di database
M
Sebagian
CHT-02
Chat grup (tim, divisi, rapat)
S
Sebagian
CHT-03
Percakapan antar-karyawan tercatat (pengirim, penerima, isi, ruang, masa aktif) dan tampil sebagai bubble
M
Ada
CHT-04
Karyawan menjawab sesuai persona dan konteks RAG, dan tidak mengaku telah mengerjakan sesuatu yang tidak ada di log
M
Sebagian
4.9 Email (EML)
ID
Kebutuhan
Prior.
Status
EML-01
Terhubung ke kotak surat perusahaan lewat IMAP (baca) dan SMTP (kirim); kredensial dari .env
M
Baru
EML-02
Inbox: ambil email baru berkala, simpan di database, tandai sebagai sumber tak tepercaya
M
Baru
EML-03
Outbox: draf (penerima, subjek, isi, lampiran) berstatus draft, menunggu persetujuan, terkirim, atau ditolak
M
Baru
EML-04
Kirim hanya setelah Owner menyetujui, dengan pratinjau lengkap
M
Baru
EML-05
Isi email masuk diperlakukan sebagai data, bukan instruksi; aksi turunan butuh persetujuan
M
Baru
EML-06
Kirim otomatis ke daftar penerima tertentu, hanya bila diaktifkan Owner (default mati)
C
Baru
EML-07
Email terkirim tercatat di audit log beserta pembuat draf dan penyetuju
M
Baru
EML-08
Batas laju kirim per jam dan per hari
S
Baru
EML-09
Setiap email keluar memiliki Message-ID unik yang disimpan sebelum pengiriman; rekonsiliasi memeriksa folder Terkirim lewat IMAP sebelum pengiriman ulang apa pun
M
Baru
4.10 Website (WEB)
ID
Kebutuhan
Prior.
Status
WEB-01
Konfigurasi website (URL, metode deploy, token) dari .env
M
Baru
WEB-02
Karyawan Frontend/Promosi menyiapkan perubahan sebagai paket dengan diff atau pratinjau
M
Baru
WEB-03
Publikasi hanya setelah persetujuan Owner; versi, waktu, dan penyetuju dicatat
M
Baru
WEB-04
Rollback ke versi sebelumnya
S
Baru
WEB-05
Pemeriksaan pasca-publikasi (status HTTP, halaman utama termuat)
S
Baru
WEB-06
Backup otomatis sebelum publikasi
S
Baru
WEB-07
Setiap publikasi memiliki ID rilis; rekonsiliasi memeriksa versi yang aktif di server sebelum publikasi diulang
M
Baru
4.11 Knowledge dan arsip (KNW)
ID
Kebutuhan
Prior.
Status
KNW-01
Dokumen dipecah menjadi chunk; pencarian embedding Ollama dengan fallback FTS5/BM25 atau LIKE
M
Ada
KNW-02
Dokumen di docs/, reports/, workspace/projects/ terindeks otomatis
M
Ada
KNW-03
Notulen, keputusan, laporan proyek, dan kebijakan perusahaan masuk indeks otomatis
S
Baru
KNW-04
Dokumen yang mengandung pola rahasia (kunci API, password) ditolak atau disamarkan sebelum diindeks
M
Baru
KNW-05
Arsip bersifat baca-saja; perubahan berarti versi baru
S
Baru
4.12 Laporan dan audit (RPT)
ID
Kebutuhan
Prior.
Status
RPT-01
Tindakan dan keputusan penting (interaksi objek, task, rapat, persetujuan, email, publikasi) menjadi event audit; pergerakan karakter tidak dicatat sebagai audit
M
Sebagian
RPT-02
Laporan mingguan Markdown dari event dan task
M
Ada
RPT-03
Laporan per divisi dan per proyek; ekspor PDF lewat printer
S
Baru
RPT-04
Dasbor pemakaian token dan estimasi biaya per karyawan/model
S
Baru
RPT-05
Audit log hanya-tambah (append-only) dan dapat dicari
M
Baru
4.13 Divisi Promosi (DIV)
ID
Kebutuhan
Prior.
Status
DIV-01
Divisi Promosi memiliki manajer dan minimal dua karyawan dengan ruang kerja sendiri
M
Baru
DIV-02
Keluaran: copywriting, rencana konten, draf pengumuman/rilis, perubahan halaman website
S
Baru
DIV-03
Semua materi keluar (email, website, media sosial) melewati antrean persetujuan
M
Baru
DIV-04
Divisi baru dapat ditambah lewat data dan prompt peran, tanpa mengubah kode
S
Baru
4.14 Company Command Center (CCC)
Komputer Owner membuka satu dasbor perusahaan di dalam game. Urutan bangun: CCC-01 sampai 03, CCC-07, dan CCC-08 pada Fase B; CCC-04 sampai 06 pada Fase D.
ID
Kebutuhan
Prior.
Status
CCC-01
Ringkasan kondisi perusahaan: karyawan bekerja, idle, atau terhambat; proyek aktif; task terlambat
M
Baru
CCC-02
Antrean persetujuan dengan pratinjau payload dan tombol setujui atau tolak
M
Baru
CCC-03
Daftar proyek dan task dengan progres dan bukti pekerjaan
M
Baru
CCC-04
Linimasa aktivitas dan audit yang dapat difilter menurut divisi, karyawan, dan jenis
S
Baru
CCC-05
Laporan kinerja per divisi
S
Baru
CCC-06
Pemakaian token dan biaya AI per karyawan, model, dan proyek
S
Baru
CCC-07
Semua data dibaca dari backend; dasbor tidak menghitung atau menyimpan status sendiri
M
Baru
CCC-08
Monitoring per karyawan di komputer meja Owner: task aktif, file terakhir yang diubah, ringkasan output terminal, dan hasil tes (baca saja)
M
Baru
4.15 Sinkronisasi realtime (SYN)
ID
Kebutuhan
Prior.
Status
SYN-01
Backend mengirim event ke klien lewat WebSocket /ws/events
M
Baru
SYN-02
Setiap event memiliki ID berurutan yang terus naik
M
Baru
SYN-03
Klien menyambung ulang otomatis dengan jeda bertahap (backoff)
M
Baru
SYN-04
Setelah tersambung ulang, klien mengirim ID event terakhir dan menerima event yang terlewat; bila selisih melebihi batas, klien mengambil snapshot penuh
M
Baru
SYN-05
Bila WebSocket tidak tersedia, klien kembali ke polling dan menampilkan indikatornya
S
Sebagian
SYN-06
Pembaruan posisi karakter dikirim sebagai state dengan laju terbatas dan tidak masuk audit
S
Baru
SYN-07
Event disimpan dengan batas retensi (default 24 jam atau 10.000 event); di luar batas, klien memakai snapshot
M
Baru
SYN-08
Klien mengirim acknowledgment untuk ID event terakhir yang diproses
S
Baru
SYN-09
Event duplikat dikenali dari ID dan tidak menghasilkan aksi dua kali (idempoten)
M
Baru
4.16 Meja Owner dan dokumen fisik (PAP)
Owner memiliki ruangan dan meja kerja sendiri. Dari komputer di meja itu Owner memantau pekerjaan semua karyawan (CCC-08). Hasil kerja dan permintaan persetujuan tidak muncul sebagai pop-up: karyawan mencetaknya di printer kantor, berjalan ke ruang Owner, dan menaruh kertasnya di tray meja. Saat Owner pergi, kertas menumpuk dan menunggu diperiksa, seperti di kantor nyata. Setiap kertas adalah record Paper di backend (prinsip P1 dan P2), bukan sekadar objek visual.
ID
Kebutuhan
Prior.
Status
PAP-01
Setiap hasil kerja yang perlu dibaca Owner dan setiap permintaan persetujuan adalah record Paper: id, jenis (laporan task, laporan proyek, proposal persetujuan, notulen, draf email, paket website), pembuat, tujuan, status pengiriman, status keputusan, versi, hash payload, tautan ke task atau persetujuan
M
Baru
PAP-02
Paper memiliki dua status terpisah. Status pengiriman: DRAFT, PRINTED, DELIVERED. Status pemeriksaan: UNREAD, REVIEWED, DEFERRED, lalu keputusan APPROVED, REJECTED, atau REVISION_REQUESTED. Siklus hidup: EXPIRED bila kedaluwarsa, ARCHIVED sesudahnya. Menunda tidak mengubah status pengiriman. Transisi hanya oleh backend
M
Baru
PAP-03
Karyawan mencetak Paper di printer kantor (OBJ-04): karyawan berjalan ke printer, PrintJob tercatat, file PDF dihasilkan, status PRINTED
M
Baru
PAP-04
Karyawan membawa cetakan ke ruang Owner dan menaruhnya di tray; status DELIVERED hanya setelah event pengantaran tercatat. Animasi berjalan dan menaruh kertas dipicu event itu, bukan sebaliknya
M
Baru
PAP-05
Tray menampilkan tumpukan sesuai Paper berstatus DELIVERED; tumpukan persisten di database dan tetap ada ketika Owner pergi atau game ditutup
M
Baru
PAP-06
Perutean: yang wajib sampai ke tray adalah proposal persetujuan, laporan akhir proyek, dan notulen yang memuat keputusan; laporan task rutin dikumpulkan di arsip dan Command Center kecuali Owner mengubah aturan perutean
S
Baru
PAP-07
Owner memeriksa satu per satu: tekan E pada tray untuk mengambil kertas teratas dan membuka pembaca dokumen berisi isi, bukti pekerjaan, lampiran, dan riwayat versi
M
Baru
PAP-08
Keputusan pada kertas: Setujui, Tolak, Minta revisi (dengan catatan), atau Simpan untuk nanti (status DEFERRED; kertas kembali ke tumpukan dan tetap DELIVERED)
M
Baru
PAP-09
Proposal persetujuan memuat ringkasan, alasan, dampak dan risiko, biaya (bila ada), isi lengkap atau diff, hash payload, pengaju, dan batas kedaluwarsa
M
Baru
PAP-10
Minta revisi mengembalikan catatan ke pembuat; pembuat membuat Paper versi baru (payload dan hash baru) dan versi lama diarsipkan
M
Baru
PAP-11
Proposal kedaluwarsa diberi tanda, tidak dapat disetujui, dan dapat diajukan ulang oleh pembuat
M
Baru
PAP-12
Urutan tumpukan menurut prioritas dan waktu; Sekretaris dapat menyaring dan merangkum bila tumpukan melebihi batas (default 15 kertas) dengan lembar ringkasan di paling atas
S
Baru
PAP-13
Semua kertas yang menunggu juga dapat diperiksa dan diputuskan dari Command Center dengan data, keputusan, dan audit identik; ini jalur alternatif yang tidak menggantikan alur kertas
M
Baru
PAP-14
Tidak ada pop-up modal untuk persetujuan; pemberitahuan hanya pasif, berupa lencana jumlah kertas di HUD yang dapat dimatikan
M
Baru
PAP-15
Kertas tidak muncul atau hilang di dunia tanpa event Paper yang tercatat; kertas yang sudah diputuskan pindah ke tray Selesai lalu diarsipkan
M
Baru
PAP-16
Keputusan, pemutus, waktu, versi, dan hash dicatat di audit log
M
Baru
5. Antarmuka Eksternal
5.1 Antarmuka pengguna (Godot)
HUD berisi status koneksi, nama ruangan, dan prompt interaksi. Panel: Command Center (komputer Owner), Agenda (meja Sekretaris), Pembaca Dokumen (kertas di tray Owner), Proyek, Rapat, Chat, Persetujuan, Arsip, Knowledge, Laporan, Organisasi. Semua panel dapat ditutup dengan Esc. Kontrol: WASD/panah, Shift, Space, E, Esc, mouse. Teks UI berbahasa Indonesia. Persetujuan tidak memakai pop-up modal; permintaan persetujuan datang sebagai dokumen di tray meja Owner. Resolusi dasar 1600x900.
5.2 API backend
Endpoint yang sudah ada: GET /api/status, GET /api/office/state, GET|POST /api/office/player, POST /api/office/action, POST /api/command, POST /api/chat, POST /api/employee-chat, POST /api/room-chat, GET /api/chat/history, GET|POST /api/knowledge/documents, GET /api/knowledge/search.
Endpoint baru: /api/departments, /api/employees, /api/projects, /api/tasks, /api/meetings (termasuk transkrip), /api/approvals (daftar, setujui, tolak), /api/inbox, /api/outbox, /api/website/deployments, /api/audit, /api/usage, dan /ws/events (WebSocket).
Aturan: JSON UTF-8; batas ukuran body; kode status HTTP standar; endpoint yang mengubah data wajib token (Authorization); pesan error tidak membocorkan rahasia atau path internal.
5.3 Antarmuka layanan
LLM melalui litellm (Ollama lokal atau cloud). Email melalui IMAP/SMTP dengan TLS. Website melalui metode deploy yang dipilih Owner (git push, SFTP, atau API CMS). Penyimpanan di SQLite.
6. Kebutuhan Non-Fungsional
ID
Kategori
Kebutuhan
NFR-SEC-01
Keamanan
Rahasia hanya di .env atau vault sisi server; tidak masuk prompt, RAG, log, atau respons API
NFR-SEC-02
Keamanan
Subprocess agen berjalan dengan env hasil whitelist, tanpa kredensial email, website, atau API
NFR-SEC-03
Keamanan
Bind 127.0.0.1 secara default; akses jaringan lain butuh token dan TLS
NFR-SEC-04
Keamanan
Semua aksi berdampak keluar butuh persetujuan Owner (lihat bagian 8)
NFR-SEC-05
Keamanan
Konten tak tepercaya (email, web) berlabel dan tidak dapat memicu tool secara langsung; pertahanan utama tetap izin tool yang ditegakkan backend (CMD-07)
NFR-SEC-06
Keamanan
Validasi input dan path (anti path traversal); batas ukuran request
NFR-SEC-07
Keamanan
.env, data/, workspace/ dikecualikan dari VCS dan paket distribusi
NFR-SEC-08
Keamanan
Klien Godot tidak menanam token permanen; backend menerbitkan sesi Owner berumur pendek (default 8 jam), berizin terbatas, dan dapat dicabut, disimpan di memori atau keystore sistem
NFR-SEC-09
Keamanan
Subprocess agen berjalan di sandbox (container atau isolasi sistem operasi): filesystem terbatas pada folder proyek, jaringan mati secara default (lihat NFR-SEC-10), dengan batas CPU, memori, jumlah proses, dan waktu; allowlist executable saja tidak dianggap sandbox
NFR-SEC-10
Keamanan
Kebijakan jaringan sandbox: dependensi memakai cache atau mirror lokal bila ada; akses sementara hanya lewat proxy dengan allowlist host (misalnya registry paket) per proyek yang ditetapkan Owner; subprocess tidak pernah memperoleh internet langsung; setiap akses jaringan dicatat
NFR-PRF-01
Kinerja
Klien minimal 60 FPS pada GPU entry-level dengan 10 NPC
NFR-PRF-02
Kinerja
API non-LLM p95 di bawah 300 ms (lokal); event sampai klien dalam 1 detik
NFR-PRF-03
Kinerja
Panggilan LLM asinkron; UI tidak membeku; ada indikator sedang memproses
NFR-REL-01
Keandalan
Kegagalan LLM, email, atau website tidak merusak data; retry terbatas dan pesan jelas
NFR-REL-02
Keandalan
Transaksi SQLite; backup otomatis harian
NFR-REL-03
Keandalan
Pipeline terputus dapat dilanjutkan atau ditandai gagal dengan jelas
NFR-MNT-01
Pemeliharaan
main.py dipecah menjadi modul; tes otomatis untuk store, tools, approval, dan validator
NFR-MNT-02
Pemeliharaan
Skema database dengan migrasi bernomor
NFR-USA-01
Kegunaan
Fungsi inti dicapai maksimal 3 interaksi dari posisi Owner; prompt interaksi jelas
NFR-COS-01
Biaya
Batas token harian, per proyek, dan per rapat dapat dikonfigurasi; melewati batas butuh persetujuan
NFR-PRV-01
Privasi
Owner dapat melihat model mana yang lokal dan cloud; data ke cloud hanya untuk karyawan yang dikonfigurasi cloud
NFR-POR-01
Portabilitas
Windows dan Linux; Godot 4.3+
NFR-OBS-01
Observabilitas
Log terstruktur bertingkat dan bebas rahasia
7. Model Data
Entitas
Atribut utama
Company
nama, identitas, jam kerja, kebijakan
Department
id, nama, manajer, ruang
Employee
id, nama, jabatan, departemen, atasan, model, skill, izin tool, status, avatar
PlayerState
posisi, ruangan, aktivitas (state berkala), tampilan avatar
Room / Interactable
id, nama, area, jenis objek, tujuan interaksi
Project
id, nama, divisi, path workspace/repo, status, deliverable
Task
id, proyek, penerima, prioritas, status, dependensi, kriteria, bukti
Meeting
id, agenda, peserta, ruang, waktu, transkrip, keputusan, tindak lanjut
Interaction
pengirim, penerima, isi, ruang, kedaluwarsa
EmailMessage
arah, status, dari, ke, subjek, isi, lampiran, tingkat kepercayaan
Approval
jenis, payload, pemohon, status, pemutus, waktu
WebsiteDeployment
versi, paket perubahan, status, penyetuju, hasil pemeriksaan
Artifact / ArchiveRecord
tautan ke file, build, hasil tes, laporan; tak-berubah
AuditLog
waktu, aktor, jenis, detail, referensi, hash; append-only; hanya tindakan dan keputusan penting
UsageRecord
karyawan, model, token, estimasi biaya, waktu
EmployeeState
karyawan, ruangan, posisi, aktivitas, sumber (task atau sesi), waktu (state berkala)
WorldEvent
waktu, jenis, pelaku, objek, ruangan (kejadian visual dan interaksi dunia; masa simpan terbatas)
Paper
id, jenis, pembuat, tujuan, status pengiriman, status keputusan, versi, hash payload, tautan task atau persetujuan, catatan keputusan
PrintJob
id, Paper, pencetak, waktu, file PDF, status
ExecutionRecord
id, persetujuan, aksi, hash payload, idempotency key, status eksekusi, jumlah percobaan, hasil, waktu
8. Matriks Persetujuan
Aksi
Mode
Pindah ruangan, buat task internal, buat rapat, laporan, pencarian knowledge
Otomatis, dicatat
Mulai pipeline coding
Persetujuan Owner
Membaca email masuk
Otomatis; isi diperlakukan sebagai data tak tepercaya
Mengirim email
Persetujuan Owner (default selalu)
Publikasi atau mengubah website
Persetujuan Owner
Melewati batas biaya token
Persetujuan Owner
Mengubah atau menghapus arsip
Dilarang; hanya versi baru
Menjalankan perintah di luar allowlist
Ditolak
8.1 Aturan keterikatan persetujuan (APR)
Persetujuan mengikat isi yang persis disetujui Owner, bukan sekadar jenis aksinya. Persetujuan diberikan lewat dokumen proposal (kertas di tray Owner atau tampilannya di Command Center), tidak lewat pop-up.
ID
Kebutuhan
Prior.
Status
APR-01
Setiap persetujuan terikat pada hash SHA-256 dari payload lengkap (penerima, subjek, isi, lampiran, atau paket perubahan website)
M
Baru
APR-02
Payload yang berubah setelah disetujui membatalkan persetujuan dan mengembalikan item ke antrean
M
Baru
APR-03
Persetujuan sekali pakai dan kedaluwarsa dalam 24 jam secara default
M
Baru
APR-04
Hanya sesi Owner yang terautentikasi dapat menyetujui; agen tidak dapat menyetujui aksinya sendiri
M
Baru
APR-05
Keputusan, pemutus, waktu, dan hash dicatat di audit log
M
Baru
APR-06
Hash diverifikasi ulang tepat sebelum eksekusi; perubahan status persetujuan dan klaim eksekusi dilakukan dalam satu transaksi database
M
Baru
APR-07
Payload yang disetujui disimpan immutable; perubahan berarti payload dan persetujuan baru. Satu persetujuan tidak dapat dieksekusi dua kali (idempotency key)
M
Baru
APR-08
Persetujuan hanya sah bila diberikan lewat dokumen proposal (Paper) yang hash-nya sama dengan payload
M
Baru
APR-09
Aksi yang disetujui memiliki status eksekusi: PENDING, CLAIMED, EXECUTING, SUCCEEDED, FAILED, atau UNKNOWN; hanya satu pekerja yang dapat mengklaim satu eksekusi
M
Baru
APR-10
Aksi eksternal memakai transactional outbox: persetujuan dan entri outbox ditulis dalam satu transaksi, lalu pekerja terpisah mengeksekusinya
M
Baru
APR-11
Bila hasil eksekusi tidak diketahui (misalnya backend mati saat mengirim), status UNKNOWN: tidak ada kirim ulang otomatis; sistem merekonsiliasi dengan sistem tujuan dan, bila tetap tidak pasti, menyerahkan keputusan kirim ulang kepada Owner lewat Paper
M
Baru
9. Konfigurasi Baru di .env
Variabel
Fungsi
MODEL_SECRETARY
Model untuk Sekretaris
API_AUTH_TOKEN
Rahasia backend untuk menerbitkan sesi Owner; tidak pernah ditanam di klien
EMAIL_ADDRESS, EMAIL_PASSWORD
Akun email perusahaan
EMAIL_IMAP_HOST, EMAIL_SMTP_HOST
Server email
EMAIL_SEND_LIMIT_PER_DAY
Batas kirim harian
WEBSITE_URL, WEBSITE_DEPLOY_TOKEN
Alamat dan token deploy website
DAILY_TOKEN_BUDGET
Batas token harian
MAX_CONCURRENT_PROJECTS
Batas proyek paralel
Semua variabel ini hanya dibaca backend dan tidak diteruskan ke subprocess agen.
10. Fase Pengembangan dan Kriteria Penerimaan
Fase
Cakupan
Kriteria penerimaan
A. Fondasi organisasi
ORG, SEC, CHT-01, CMD-06, CMD-07, WLD-08, RPT-05, sesi Owner (NFR-SEC-08), sandbox subprocess (NFR-SEC-09, NFR-SEC-10), PRJ-10 s.d. 13, NFR-SEC-02, NFR-SEC-07, NFR-MNT-01, NFR-MNT-02
Roster dibaca dari database; Sekretaris merutekan 10 skenario perintah ke penerima yang benar; riwayat chat bertahan setelah restart; tes otomatis membuktikan env subprocess bebas kredensial, panggilan tool di luar izin ditolak backend, endpoint mutasi menolak permintaan tanpa token, audit log hanya-tambah, task tidak dapat menjadi COMPLETED tanpa bukti tervalidasi, transisi di luar matriks ditolak, dan subprocess tidak dapat membaca file di luar folder proyek atau mengakses jaringan (semua tes otomatis)
B. Rapat dan persetujuan
MTG, SEC-05, APR, PAP, OBJ-04, OBJ-10, OBJ-11, CMD-04, CCC-01 s.d. 03, CCC-07, CCC-08
Rapat 3 agen menghasilkan notulen dan minimal satu task usulan; proposal persetujuan tercetak, diantar ke tray meja Owner, dan dapat disetujui dari kertas tanpa pop-up; printer menghasilkan file PDF nyata; persetujuan batal otomatis bila payload berubah (tes otomatis)
C. Email dan website
EML, WEB, KNW-04, NFR-SEC-03 s.d. 05
Draf tidak terkirim sebelum disetujui (tes otomatis); email berisi instruksi jahat tidak memicu tool; publikasi dan rollback lolos uji di staging; simulasi backend mati saat mengirim menghasilkan status UNKNOWN tanpa kirim ulang otomatis
D. Proyek paralel dan Promosi
PRJ-03, 05, 07, DIV, RPT-03, RPT-04, CCC-04 s.d. 06
Dua proyek berjalan bersamaan; proyek selesai memicu usulan task Promosi; snapshot arsip tak-berubah
E. Polish Godot
OBJ-08, WLD-03, WLD-07, SYN-01 s.d. 09, polish animasi PAP, model GLB
NPC tidak menembus furnitur; event tampil di klien dalam 1 detik dan klien pulih otomatis setelah koneksi WebSocket putus
10.1 Milestone 1: satu siklus bisnis penuh
Sebelum dunia 3D diperluas, satu siklus bisnis nyata harus berjalan dari awal sampai akhir pada satu proyek kecil sungguhan (misalnya halaman web statis atau skrip utilitas). Fase A dan B harus mencapai milestone ini sebelum Fase C, D, dan E dimulai. Milestone ini tidak membutuhkan email atau website, sehingga siklus internal terbukti sebelum sistem terhubung ke dunia nyata.
1. Owner memberi perintah lewat Sekretaris atau langsung ke manajer.
2. Sekretaris memahami perintah, menyusun rencana, dan meminta persetujuan.
3. Manajer membagi pekerjaan menjadi task.
4. Karyawan AI mengerjakan dan menghasilkan file nyata.
5. QA menjalankan tes dan hasilnya tersimpan.
6. Karyawan mencetak laporan beserta bukti (file, hasil tes, riwayat), mengantarnya ke tray meja Owner, dan Owner memeriksanya.
Kriteria penerimaan: siklus selesai tanpa intervensi manual selain persetujuan; status setiap karakter di game cocok dengan task di database; siklus berhasil tiga kali berturut-turut; tidak ada task selesai tanpa bukti; tidak ada Paper tanpa record backend; tidak ada Paper atau laporan yang hilang setelah restart; tidak ada Paper yang dapat diputuskan dua kali; posisi dan aktivitas NPC sesuai status backend; semua keputusan Owner tercatat di audit log.
11. Risiko
Risiko
Dampak
Mitigasi
Halusinasi LLM mengirim email atau publikasi keliru
Tinggi
Gerbang persetujuan dan pratinjau penuh
Prompt injection lewat email atau web
Tinggi
Label tak tepercaya; konten luar tidak dapat memicu tool
Kebocoran rahasia lewat subprocess atau log
Tinggi
Whitelist env, redaksi log dan indeks
Biaya token membengkak
Sedang
Batas biaya, dasbor pemakaian, batas putaran rapat
Kualitas model lokal kecil rendah
Sedang
Model cloud untuk Sekretaris dan Manajer
Cakupan terlalu luas
Sedang
Kerjakan per fase, prioritas Must lebih dulu
Perubahan versi CrewAI
Sedang
Bungkus lewat antarmuka internal, kunci versi
Dunia 3D diperbesar sebelum sistem kerja nyata solid
Sedang
Milestone 1 (bagian 10.1) wajib lolos sebelum Fase C
12. Asumsi Default dan Keputusan Tertunda
Asumsi berikut berlaku sampai Owner menetapkan lain. Setiap perubahan dicatat di Riwayat Revisi.
1. Divisi: Eksekutif, Front Office, Engineering (sudah ada), dan Promosi dengan tiga karyawan (manajer, content writer, social media). Divisi lain ditambah setelah Milestone 1.
2. Email memakai satu kotak surat perusahaan lewat IMAP/SMTP; website dideploy lewat git push. Metode lain diputuskan Owner sebelum Fase C.
3. Model cloud untuk Sekretaris dan Manajer, lokal (Ollama) untuk karyawan lain. Anggaran bulanan ditetapkan Owner lewat DAILY_TOKEN_BUDGET sebelum Fase A selesai.
4. Kirim email otomatis tetap mati sepanjang versi 1.x (EML-06 hanya opsi masa depan).
5. Karyawan AI bekerja hanya bila ada task; jam kerja dan siang/malam bersifat kosmetik (WLD-07).
6. Bahasa internal Indonesia; email ke pihak luar mengikuti bahasa pengirim yang dibalas.
7. Akses jarak jauh di luar lingkup versi 1.x.
13. Riwayat Revisi
Versi
Tanggal
Perubahan
1.0
31 Oktober 2026
Draf awal
1.1
31 Oktober 2026
Final: persetujuan terikat payload (APR), Company Command Center (CCC), sinkronisasi realtime (SYN), audit dipisah dari state posisi, izin tool ditegakkan backend (CMD-06, CMD-07), Milestone 1, Sekretaris sebagai pintu utama, asumsi default menggantikan pertanyaan terbuka
1.2
31 Oktober 2026
Meja Owner dan dokumen fisik (PAP), monitoring per karyawan (CCC-08), persetujuan atomic (APR-06 s.d. 08), state machine task (PRJ-10 s.d. 12), sesi Owner dan sandbox subprocess (NFR-SEC-08, 09), model data dipecah (PlayerState, EmployeeState, WorldEvent, AuditLog, Paper, PrintJob), retensi dan idempotensi event (SYN-07 s.d. 09), gerbang Milestone 1 dipindah ke setelah Fase B
1.3
31 Oktober 2026
Baseline implementasi: status eksekusi dan rekonsiliasi (APR-09 s.d. 11, EML-09, WEB-07), status pengiriman dan keputusan Paper dipisah (PAP-02, PAP-08), matriks transisi task (PRJ-13, bagian 4.6.1), kebijakan jaringan sandbox (NFR-SEC-10), kriteria Milestone 1 diperluas
Dokumen ini dibekukan sebagai baseline implementasi. Perubahan lingkup setelah ini dilakukan lewat revisi bernomor di tabel di atas; klarifikasi teknis yang tidak mengubah lingkup dicatat sebagai patch dokumentasi.