"""Penulis PDF minimal tanpa dependensi (OBJ-04, PAP-03).

Hanya teks monospasi, cukup untuk laporan, notulen, dan proposal nyata yang
dapat dibuka di pembaca PDF.
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path


def _escape(text: str) -> str:
    value = text.encode("latin-1", errors="replace").decode("latin-1")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(title: str, lines: list[str], *, page_lines: int = 62) -> bytes:
    wrapped: list[str] = []
    wrapped.append(title)
    wrapped.append("=" * min(78, len(title)))
    wrapped.append("")
    for line in lines:
        if line == "":
            wrapped.append("")
            continue
        for part in textwrap.wrap(str(line), width=92, replace_whitespace=False) or [""]:
            wrapped.append(part)
    wrapped.append("")
    wrapped.append(f"Dicetak: {datetime.now().astimezone().isoformat(timespec='seconds')}")

    pages = [wrapped[i:i + page_lines] for i in range(0, len(wrapped), page_lines)] or [[""]]
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_id = 4
    page_ids = []
    content_ids = []
    for page in pages:
        stream_lines = ["BT", "/F1 9 Tf", "50 800 Td", "11 TL"]
        for line in page:
            stream_lines.append(f"({_escape(line)}) Tj T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        content_id = add(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
        content_ids.append(content_id)
        page_id = add(b"PLACEHOLDER_PAGE")
        page_ids.append(page_id)

    pages_id = add(b"PLACEHOLDER_PAGES")
    catalog_id = add(b"PLACEHOLDER_CATALOG")
    # Font harus berada sebelum placeholder diisi; nomor objeknya stabil.
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    for index, page_id in enumerate(page_ids):
        page_body = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_ids[index]} 0 R >>"
        ).encode()
        objects[page_id - 1] = page_body
    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    )
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_start = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    ).encode()
    return bytes(output)


def write_pdf(path: str | Path, title: str, lines: list[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_pdf(title, lines))
    return target
