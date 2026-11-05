#!/usr/bin/env bash
# Sinkronisasi folder ke Cloudflare R2 (backup file kantor) — unggah idempoten.
#
# Pemakaian:
#   ./sync.sh <folder-lokal> [prefix-r2] [--dry-run]
#
# Contoh:
#   ./sync.sh ../ftp/share kantor        # share/ -> bucket bangkah-files /kantor/...
#
# Setiap file diunggah ulang (menimpa versi lama). File sensitif seperti
# users.json dan folder .venv dikecualikan secara otomatis.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WRANGLER="$ROOT/bangkah-web/node_modules/wrangler/bin/wrangler.js"
BUCKET="${R2_BUCKET:-bangkah-files}"

if [[ $# -lt 1 ]]; then
  echo "Pemakaian: $0 <folder-lokal> [prefix-r2] [--dry-run]"
  exit 1
fi

SRC="$(realpath "$1")"
PREFIX="${2:-}"
DRY_RUN="false"
for arg in "${@:3}"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN="true"
done

if [[ ! -f "$WRANGLER" ]]; then
  echo "wrangler tidak ditemukan di $WRANGLER"
  echo "Jalankan 'npm install' di folder bangkah-web terlebih dahulu."
  exit 1
fi

# wrangler membaca CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID dari env.

UPLOADED=0
FAILED=0

while IFS= read -r -d '' file; do
  rel="${file#"$SRC"/}"
  key="${rel}"
  [[ -n "$PREFIX" ]] && key="${PREFIX}/${rel}"
  size="$(stat -c '%s' "$file" 2>/dev/null || stat -f '%z' "$file")"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] $key ($size bytes)"
    continue
  fi

  if node "$WRANGLER" r2 object put "$BUCKET/$key" \
      --file "$file" --content-type auto --remote - >/dev/null 2>&1; then
    echo "[+] $key ($size bytes)"
    UPLOADED=$((UPLOADED + 1))
  else
    echo "[!] Gagal: $key"
    FAILED=$((FAILED + 1))
  fi
done < <(find "$SRC" -type f \
  -not -path '*/.venv/*' \
  -not -path '*/__pycache__/*' \
  -not -name 'users.json')

echo
echo "Ringkasan: $UPLOADED diunggah, $FAILED gagal."
exit $(( FAILED > 0 ? 1 : 0 ))
