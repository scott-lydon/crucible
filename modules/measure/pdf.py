"""A tiny dependency-free PDF writer for the SR 11-7 report (US-12).

A real PDF library (weasyprint, reportlab) is a heavy or system-dependent add for
a single feature; the report only needs a portable document carrying the same
text as the Markdown. This emits a valid multi-page PDF of monospaced text lines
with a correct cross-reference table, so any reader opens it. It is deliberately
plain: the Markdown view is the rich one, the PDF is the submittable artifact.
"""

from __future__ import annotations

_LINES_PER_PAGE = 52
_FONT_SIZE = 10
_LEADING = 14
_LEFT = 54
_TOP = 760


def _escape(text: str) -> str:
    """Escape the three characters that are special inside a PDF text string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(line: str, width: int = 95) -> list[str]:
    """Hard-wrap a long line so it does not run off the page."""
    if len(line) <= width:
        return [line]
    out: list[str] = []
    while len(line) > width:
        out.append(line[:width])
        line = line[width:]
    out.append(line)
    return out


def _content_stream(lines: list[str]) -> bytes:
    parts = [f"BT /F1 {_FONT_SIZE} Tf {_LEADING} TL {_LEFT} {_TOP} Td"]
    for i, line in enumerate(lines):
        if i:
            parts.append("T*")
        parts.append(f"({_escape(line)}) Tj")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", errors="replace")


def text_to_pdf(text: str) -> bytes:
    """Render plain text into a valid multi-page PDF (Helvetica, monospaced layout)."""
    raw_lines: list[str] = []
    for line in text.splitlines() or [""]:
        raw_lines.extend(_wrap(line))
    pages = [
        raw_lines[i : i + _LINES_PER_PAGE]
        for i in range(0, max(len(raw_lines), 1), _LINES_PER_PAGE)
    ] or [[""]]

    objects: list[bytes] = []  # objects[i] is object number i+1

    # Reserve: 1 catalog, 2 pages-tree, 3 font, then per page a page obj + stream.
    n_pages = len(pages)
    page_obj_nums = [4 + 2 * i for i in range(n_pages)]
    stream_obj_nums = [5 + 2 * i for i in range(n_pages)]

    kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode("latin-1"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page_lines, _page_num, stream_num in zip(
        pages, page_obj_nums, stream_obj_nums, strict=True
    ):
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_num} 0 R >>"
            ).encode("latin-1")
        )
        body = _content_stream(page_lines)
        stream = b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream"
        objects.append(stream)

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    count = len(objects) + 1
    out += f"xref\n0 {count}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    )
    return bytes(out)
