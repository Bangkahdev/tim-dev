# Bangkah — Website Perusahaan

Situs resmi Bangkah: [https://bangkah.web.id](https://bangkah.web.id).

Next.js (static export) + Cloudflare Worker untuk API. Kredensial/form kontak
tersimpan di D1 `bangkah-contacts`.

## Perintah

```bash
npm install                        # sekali di awal
node node_modules/next/dist/bin/next build   # build -> out/

# Jalankan site + API lokal:
node node_modules/wrangler/bin/wrangler.js dev   # http://localhost:8787

# Build website + deploy (butuh wrangler login / CLOUDFLARE_API_TOKEN):
node node_modules/wrangler/bin/wrangler.js deploy
```

## Struktur

- `src/app/page.tsx` — halaman utama (tentang, layanan, tim, proses, proyek, kontak).
- `src/components/` — navbar/footer + komponen UI shadcn-style.
- `src/app/robots.ts` + `src/app/sitemap.ts` — SEO.
- `worker/index.ts` — API Worker Cloudflare:
  - `GET /api/health` — status layanan.
  - `POST /api/contact` — formulir kontak: validasi, honeypot, rate-limit per IP (D1).
  - `GET /api/contacts` — daftar pesan (Bearer `ADMIN_TOKEN`).
  - redirect `www` → apex + security headers.
- `worker/migrations/0001_contacts.sql` — skema D1.
- `wrangler.jsonc` — deploy config (custom domain `bangkah.web.id` + `www`).

## Lokal dev

`wrangler dev` memakai nilai di `.dev.vars` (khusus lokal, jangan dipakai produksi)
dan D1 lokal; inisialisasi:

```bash
node node_modules/wrangler/bin/wrangler.js d1 execute bangkah-contacts \
  --local --file worker/migrations/0001_contacts.sql -y
```

## Deployment

Semua provisioning online (D1, R2, DNS, Email Routing, secrets) dijalankan
sekali jalan lewat [../it/cloudflare/README.md](../it/cloudflare/README.md).

## Catatan disk

HDD/USB exFAT tidak mendukung symlink: jalankan Next/wrangler langsung lewat
`node node_modules/...` (yang sudah ditunjukkan di atas), bukan `npx`.
