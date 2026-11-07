#!/usr/bin/env bash
# Menjalankan seluruh layanan jaringan kantor Bangkah:
#   1. Backend kantor      -> 127.0.0.1:8765 (loopback, dari folder backend/)
#   2. Portal intranet     -> http://<ip-kantor>:8080
#   3. Gateway Office API  -> http://<ip-kantor>:8081 (menembus ke backend loopback)
#   4. FTPS perusahaan     -> ftps://<ip-kantor>:2121
#
# Semua berjalan di depan terminal; Ctrl+C menghentikan semuanya.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LAN_DIR="$ROOT/it/lan"
FTP_DIR="$ROOT/it/ftp"
BACKEND_DIR="$ROOT/backend"
BACKEND_PORT="${BANGKAH_PORT:-8765}"
GATEWAY_PORT="${GATEWAY_PORT:-8081}"

# Gateway is pass-through: it forwards Authorization as-is and never injects tokens.

PIDS=()

start() {
  echo "[+] $1"
  "$@" &
  PIDS+=($!)
}

cleanup() {
  echo
  echo "[+] Menghentikan layanan kantor..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---------- 1. Backend kantor ----------
if curl -fsS -m 2 "http://127.0.0.1:${BACKEND_PORT}/api/status" >/dev/null 2>&1; then
  echo "[=] Backend sudah berjalan di 127.0.0.1:${BACKEND_PORT}"
else
  echo "[+] Memulai backend Bangkah (loopback ${BACKEND_PORT})..."
  (
    cd "$BACKEND_DIR"
    if [[ ! -d .venv ]]; then
      python3 -m venv .venv
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install --quiet -r requirements.txt 2>/dev/null
    exec python office_server.py
  ) &
  PIDS+=($!)
  for _ in $(seq 1 30); do
    if curl -fsS -m 2 "http://127.0.0.1:${BACKEND_PORT}/api/status" >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi

# ---------- 2. Portal intranet ----------
start "Portal intranet  ->  http://0.0.0.0:8080"
python3 "$LAN_DIR/portal_server.py" --listen "0.0.0.0:8080"

# ---------- 3. Gateway LAN ----------
start "Gateway LAN  ->  http://0.0.0.0:${GATEWAY_PORT}"
python3 "$LAN_DIR/lan_gateway.py" \
  --listen "0.0.0.0:${GATEWAY_PORT}" \
  --upstream "127.0.0.1:${BACKEND_PORT}"

# ---------- 4. FTPS ----------
if curl -fsS -m 2 "ftps://" >/dev/null 2>&1 || true; then
  if [[ -f "$FTP_DIR/start_ftp.sh" ]]; then
    start "FTPS kantor  ->  ftps://0.0.0.0:2121"
    bash "$FTP_DIR/start_ftp.sh"
  fi
fi

wait
