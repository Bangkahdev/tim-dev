#!/usr/bin/env bash
# Menjalankan server FTPS perusahaan dari folder it/ftp.
#
# Dukungan disk exFAT (USB/Fat32): paket python di salin ke .pylibs
# (tanpa virtualenv/symlink), lalu dimuat via PYTHONPATH.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
PYLIBS="$DIR/.pylibs"

have_module() {
  python3 - "$@" <<'PY'
import importlib.util, sys
missing = [m for m in sys.argv[1:] if importlib.util.find_spec(m) is None]
sys.exit(0 if not missing else 1)
PY
}

if ! have_module pyftpdlib; then
  if [[ ! -d "$PYLIBS/pyftpdlib" ]]; then
    echo "[+] Mengunduh pyftpdlib ke .pylibs ..."
    python3 -m pip install --quiet --target "$PYLIBS" --upgrade pyftpdlib
  fi
fi

if [[ ! -f users.json ]]; then
  echo "[+] Membuat akun dan folder perusahaan ..."
  python3 ftp_server.py --setup
fi

PYTHONPATH="$PYLIBS${PYTHONPATH:+:$PYTHONPATH}" exec python3 ftp_server.py "$@"
