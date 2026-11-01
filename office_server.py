"""Launcher kantor Bangkah.

Semua endpoint dan aturan domain ada di `backend.app`. Jalankan dari root
proyek: `python office_server.py`. Server hanya bind ke 127.0.0.1 secara
default (NFR-SEC-03).
"""

from __future__ import annotations

import uvicorn

from backend import settings


def main() -> None:
    print(f"Bangkah office siap di http://{settings.HOST}:{settings.PORT}")
    uvicorn.run(
        "backend.app:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
