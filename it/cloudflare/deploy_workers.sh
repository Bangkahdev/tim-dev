#!/usr/bin/env bash
# Deploy/undeplok ulang ketiga Worker setelah sisi Cloudflare sudah diprov provisioning.
#
# Pemakaian:
#   export CLOUDFLARE_API_TOKEN=...       # atau sudah wrangler login
#   export CLOUDFLARE_ACCOUNT_ID=...
#   ./deploy_workers.sh [web|mail|files|all] [--skip-build]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WRANGLER="$ROOT/bangkah-web/node_modules/wrangler/bin/wrangler.js"
TARGET="${1:-all}"
SKIP_BUILD="false"
for arg in "${@:2}"; do [[ "$arg" == "--skip-build" ]] && SKIP_BUILD="true"; done

deploy_web() {
  if [[ "$SKIP_BUILD" == "false" ]]; then
    echo "[+] Build website..."
    (cd "$ROOT/bangkah-web" && node node_modules/next/dist/bin/next build)
  fi
  echo "[+] Deploy bangkah-web..."
  node "$WRANGLER" deploy --config "$ROOT/bangkah-web/wrangler.jsonc"
}

deploy_mail() {
  echo "[+] Deploy bangkah-mail..."
  node "$WRANGLER" deploy --config "$ROOT/bangkah-mail/wrangler.jsonc"
}

deploy_files() {
  echo "[+] Deploy bangkah-files..."
  node "$WRANGLER" deploy --config "$ROOT/bangkah-files/wrangler.jsonc"
}

case "$TARGET" in
  web)   deploy_web ;;
  mail)  deploy_mail ;;
  files) deploy_files ;;
  all)   deploy_mail; deploy_files; deploy_web ;;
  *) echo "Target tidak dikenal: $TARGET (pilih web | mail | files | all)"; exit 1 ;;
esac

echo
echo "Selesai. Cek:"
echo "  curl https://bangkah.web.id/api/health"
echo "  curl https://mail.bangkah.web.id/api/health"
echo "  curl https://files.bangkah.web.id/api/health"
