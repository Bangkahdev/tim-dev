# Bangkah Company FTPS

Server file perusahaan untuk jaringan kantor (LAN), berjalan langsung dari
folder `it/ftp`. Tidak perlu akses root: port default **2121**, bukan 21.

## Mulai

```bash
./start_ftp.sh
```

Pertama kali, script membuat:

- `users.json` — akun + kata sandi acak (chmod 600, jangan di-commit)
- `share/` — folder data:
  - `share/` → akun `owner` (akses penuh)
  - `share/<nama>/` → folder pribadi tiap karyawan
  - `share/team/` → folder bersama (akun `team`)
- `certs/ftp.crt` + `certs/ftp.key` — sertifikat self-signed untuk **FTPS**

Login memakai **FTPS (explicit TLS)**:

| Klien | Pengaturan |
|---|---|
| FileZilla | Host `192.168.x.x`, Port `2121`, Encryption: **Require explicit FTP over TLS** |
| WinSCP | Protocol **FTP**, Encryption **TLS/SSL Explicit**, Port `2121` |
| curl | `curl --ftp-ssl -k ftp://192.168.x.x:2121/ --user arman:PASSWORD` |

> Sertifikat self-signed: terima/trust sekali di klien. Untuk produksi,
> gunakan sertifikat internal CA atau Cloudflare Tunnel + HTTPS (lihat `it/README.md`).

## Akun

Akun dibuat untuk `owner`, `team`, dan seluruh karyawan inti:
`arman`, `sinta`, `raka`, `bima`, `naya`, `dira`, `tika`, `mira`.
Kata sandi ditampilkan sekali saat `--setup` dan tersimpan di `users.json`.

Ganti kata sandi: edit `users.json`, lalu restart server.

## Firewall LAN

Buka port berikut hanya untuk subnet kantor:

```bash
sudo ufw allow from 192.168.0.0/16 to any port 2121 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 30000:30009 proto tcp
```

## Catatan keamanan

- FTP polos mengirim kata sandi tanpa enkripsi. Script ini memaksa TLS.
- Jangan port-forward 2121 ke internet. Untuk akses luar, gunakan
  Cloudflare Tunnel + portal file R2 (`files.bangkah.web.id`).
- Backup folder `share/` secara berkala (`it/r2/sync.sh` bisa dipakai).
