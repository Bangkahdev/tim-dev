# Cloudflare — Deploy Situs + Mail + Files Bangkah

Semua layanan online perusahaan Bangkah (website `bangkah.web.id`, mail, portal
file R2) dilakukan provisioning sekali jalan oleh satu script:

```bash
export CLOUDFLARE_API_TOKEN="token-anda"
export CLOUDFLARE_ACCOUNT_ID="155d49116414c2ec2461da423cc17ba2"
export OWNER_EMAIL="email-pribadi-anda@example.com"   # tujuan penerusan email
python3 it/cloudflare/setup_cloudflare.py
```

Script akan:

1. Verifikasi token dan akun
2. Mencari zone **bangkah.web.id**
3. Membuat D1 **bangkah-contacts** dan **bangkah-mail**
4. Membuat bucket R2 **bangkah-files** dan **bangkah-mail**
5. Menulis database ID ke `wrangler.jsonc` (bangkah-web, bangkah-mail)
6. Deploy Workers: **bangkah-web** (situs), **bangkah-mail**, **bangkah-files**
7. Menjalankan migrasi D1 (tabel `contacts`, `messages`)
8. Mengaktifkan **Email Routing**, membuat DNS MX/SPF/DKIM dan record DMARC
9. Menambahkan alamat tujuan (`OWNER_EMAIL`) — periksa email verifikasi Cloudflare
10. Menyambungkan **catch-all → Worker bangkah-mail** (semua alamat @bangkah.web.id)
11. Membuat token layanan dan menyimpannya ke `it/credentials/company-secrets.env`

Alternatif tanpa API token: jalankan `npx wrangler login` di terminal Anda sendiri
lalu approve di browser. Namun scope OAuth wrangler tidak mencakup R2 dan D1
management melalui REST — mengikuti langkah 3–4 tetap membutuhkan token atau
langkah manual di dasbor (bekerja lebih aman dengan API Token di atas).

## Membuat API Token

Dasbor Cloudflare → *My Profile → API Tokens → Create Token → Custom* dengan izin:

**Account — seluruh akun:**

| Izin | Scope |
|---|---|
| Workers Scripts | Edit |
| Workers Routes | Edit |
| D1 | Edit |
| Workers R2 Storage | Edit |
| Account Settings | Read |

**Zone — bangkah.web.id:**

| Izin | Scope |
|---|---|
| Zone | Read |
| DNS | Edit (baik semua record pun) |
| Email Routing Rules | Edit |
| Email Routing Addresses | Edit |

Alternatif tanpa API token: jalankan `wrangler login` di terminal Anda sendiri
lalu approve di browser. Namun scope OAuth wrangler tidak mencakup management
R2 melalui REST, sehingga langkah 3–4 lebih terjamin menggunakan API Token di atas.

## Setelah deploy

```bash
curl https://bangkah.web.id/api/health      # {"status":"ok",...}
```

- Satu script cukup dijalankan saat token sudah dibuat.
- Buka https://mail.bangkah.web.id → masukkan `MAIL_API_TOKEN` dari
  `it/credentials/company-secrets.env`.
- Kirim tes email ke `arman@bangkah.web.id` — pastikan muncul di inbox web dan
  masuk ke Gmail owner (setelah di verifikasi).
- Buka https://files.bangkah.web.id → masukkan `FILES_TOKEN`, unggah file percobaan.
- Kata sandi kantor permasalahan sandbox (meja FTPS) dilihat di `it/ftp/users.json`.

## Catatan

- Login wrangler OAuth (wrapper) meng-scope `email_routing` juga — sehingga
  `wrangler login` cukup untuk deploy, tetapi membaca aturan email masih
  lebih mudah lewat API token di atas.
- Domain baru butuh beberapa menit agar record MX/DKIM/SPF aktif di
  jaringan provider email tujuan.
