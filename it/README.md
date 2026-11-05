# Bangkah — Infrastruktur Perusahaan (IT Runbook)

Folder `it/` berisi seluruh layanan milik perusahaan Bangkah di domain **bangkah.web.id**
(Cloudflare) dan jaringan kantor (LAN).

| Layanan | Alamat | Teknologi | Status |
|---|---|---|---|
| Website perusahaan | https://bangkah.web.id | Next.js (static) + Worker + D1 | dideploy via `it/cloudflare/` |
| Mail perusahaan | https://mail.bangkah.web.id | Email Routing + Email Worker + D1 + R2 | arsip semua `@bangkah.web.id` |
| Portal file (R2) | https://files.bangkah.web.id | Worker + R2 | transfer file via HTTPS |
| FTPS kantor | `ftps://<ip-kantor>:2121` | pyftpdlib (TLS) | `it/ftp/start_ftp.sh` |
| Portal intranet | `http://<ip-kantor>:8080` | Python stdlib | daftar dir + tautan layanan |
| Gateway Office API | `http://<ip-kantor>:8081` | reverse proxy Python | membuka backend loopback ke LAN |
| Backend kantor | `127.0.0.1:8765` | Python API kantor | `start_backend.sh` |

## Struktur

```text
it/
├── README.md              # dokumen ini
├── company.json           # profil + direktori email tim
├── cloudflare/
│   ├── README.md          # cara membuat API token + langkah manual
│   └── setup_cloudflare.py# provisioning sekali jalan (D1, R2, DNS, Email Routing)
├── credentials/
│   └── company-secrets.env# token layanan (otomatis dibuat, chmod 600, jangan disebar)
├── ftp/
│   ├── ftp_server.py      # server FTPS
│   ├── start_ftp.sh
│   ├── users.json         # akun + sandi (jangan dibagikan)
│   ├── share/             # data file kantor
│   └── certs/             # sertifikat TLS self-signed
├── lan/
│   ├── portal_server.py   # portal intranet :8080
│   ├── lan_gateway.py     # proxy LAN -> backend loopback :8081
│   ├── start_office.sh    # jalankan backend+portal+gateway (FTPS opsional separate)
│   └── selftest_lan.py    # tes cepat layanan LAN
└── r2/
    └── sync.sh            # backup folder kantor ke bucket R2
```

## 1. Website perusahaan

Source: `bangkah-web/` (Next.js + Worker `worker/index.ts`).

```bash
cd bangkah-web
node node_modules/next/dist/bin/next build     # hasil -> out/
node node_modules/wrangler/bin/wrangler.js deploy
```

- Formulir kontak → tabel `contacts` di D1 `bangkah-contacts`.
- Baca pesan: `curl -H "Authorization: Bearer $ADMIN_TOKEN" https://bangkah.web.id/api/contacts`
- Health: https://bangkah.web.id/api/health

## 2. Mail perusahaan

Setiap karyawan punya alamat `@bangkah.web.id`: `owner, arman, sinta, raka, bima,
naya, dira, tika, mira` plus alias `team@`, `contact@`.

- Semua email masuk diarsipkan Worker `bangkah-mail` (D1 metadata + R2 raw `.eml`),
  lalu diteruskan ke alamat pribadi owner (`FORWARD_TO`).
- Inbox web: https://mail.bangkah.web.id (login memakai `MAIL_API_TOKEN`).
- API untuk backend Bangkah:
  - `GET /api/messages?mailbox=arman&limit=50`
  - `GET /api/messages/{id}` · `GET /api/messages/{id}/raw` · `DELETE /api/messages/{id}`
- Email keluar: `POST /api/send` memakai Resend (isi secret `RESEND_API_KEY`)
  atau SMTP relay backend lewat outbox approval (`backend/.env`).
- Autentikasi: Bearer atau Basic (`bangkah:<MAIL_API_TOKEN>`).

## 3. FTPS kantor (LAN)

```bash
cd it/ftp
./start_ftp.sh                 # pertama: buat users.json + share + sertifikat
```

- Port **2121**, mode **FTPS explicit (TLS wajib)**, passive ports 30000–30009.
- Akun per karyawan: folder pribadi; `owner` akses penuh; `team` folder bersama.
- Klien: FileZilla/WinSCP — Encryption "Require explicit FTP over TLS".

## 4. Portal file R2 (transfer lintas lokasi)

- https://files.bangkah.web.id — login dengan `FILES_TOKEN`, drag & drop.
- REST API: `GET/PUT/DELETE /api/files`, `GET /api/download?key=...`.
- Batas 100 MB per file (batas body Worker). Untuk backup folder:

```bash
cd it/r2
./sync.sh ../ftp/share kantor/db-office
```

## 5. Jaringan kantor (LAN)

```bash
cd it/lan
./start_office.sh                                       # jalankan semuanya
python3 selftest_lan.py                                  # cek status
```

- Portal intranet di port **8080**, gateway API di **8081**, FTPS di **2121**.
- Backend tetap di loopback; satu-satunya pintu LAN adalah gateway
  `it/lan/lan_gateway.py` yang menolak alamat IP publik dan menyisipkan bearer token.
- Akses dari perangkat lain di LAN: `http://<ip-kantor>:8080`.
- Firewall (sekali jalan, butuh sudo):

```bash
sudo ufw allow from 192.168.0.0/16 to any port 8080,8081 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 2121 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 30000:30009 proto tcp
```

## 6. Kredensial

Semua token layanan online (mail, files, admin-kontak) ada di
`it/credentials/company-secrets.env` — dibuat otomatis oleh
`it/cloudflare/setup_cloudflare.py` dengan `chmod 600`.

- Jangan pernah meng-commit `.env`, `users.json`, `credentials/`, `certs/`.
- Rotasi token: `wrangler secret put MAIL_API_TOKEN` (dan lainnya), lalu ubah
  salinan lokal di `credentials/`.

## 7. Catatan disk

Project ini berada di disk **exFAT** (USB) yang tidak mendukung symlink:
- Script `it/ftp/start_ftp.sh` otomatis memasang dependensi Python ke
  `it/ftp/.pylibs` (tanpa virtualenv).
- `` bangkah-web/node_modules `` tetap dibutuhkan untuk wrangler.
- Saat migrasi ke Windows/server internal, folder ini tetap bekerja karena
  tidak ada path yang menolak Windows kecuali sertifikat OpenSSL (regenerate
  dengan `--setup` di Windows menggunakan Git Bash).
