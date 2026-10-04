"""Draws safemove\\app.ico (blue tile, white phone, green arrow) with plain Python, no image library.

    python make_icon.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

S = 256
BLUE, WHITE, SCREEN, GREEN = (30, 136, 229, 255), (255, 255, 255, 255), (21, 64, 120, 255), (46, 204, 113, 255)


def rounded(x, y, x0, y0, x1, y1, r) -> bool:
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def arrow(x, y) -> bool:
    """Downward arrow at the lower right."""
    shaft = 168 <= x <= 200 and 120 <= y <= 186
    head = 150 <= y <= 222 and abs(x - 184) <= (222 - y) * 0.75 and y >= 186
    return shaft or head


def pixel(x: float, y: float):
    if not rounded(x, y, 8, 8, 248, 248, 52):
        return (0, 0, 0, 0)
    if arrow(x, y):
        return GREEN
    if rounded(x, y, 146, 112, 222, 230, 18) and not rounded(x, y, 156, 122, 212, 220, 10):
        return BLUE  # gap ring around the arrow so it stands out
    if rounded(x, y, 52, 28, 156, 228, 22):  # phone body
        if rounded(x, y, 62, 50, 146, 196, 6):
            return SCREEN
        if (x - 104) ** 2 + (y - 212) ** 2 <= 7 ** 2:
            return SCREEN  # home button
        return WHITE
    return BLUE


def render(size: int) -> bytes:
    """RGBA rows, 3x3 supersampled for smooth edges."""
    rows = bytearray()
    k = S / size
    for j in range(size):
        rows.append(0)  # PNG filter type
        for i in range(size):
            acc = [0, 0, 0, 0]
            for sy in (0.17, 0.5, 0.83):
                for sx in (0.17, 0.5, 0.83):
                    p = pixel((i + sx) * k, (j + sy) * k)
                    for c in range(4):
                        acc[c] += p[c]
            rows += bytes(round(v / 9) for v in acc)
    return bytes(rows)


def png(size: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(render(size), 9)) + chunk(b"IEND", b"")


def ico(sizes=(256, 64, 48, 32, 16)) -> bytes:
    images = [png(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return header + entries + b"".join(images)


if __name__ == "__main__":
    out = Path(__file__).parent / "safemove" / "app.ico"
    out.write_bytes(ico())
    (Path(__file__).parent / "build").mkdir(exist_ok=True)
    (Path(__file__).parent / "build" / "icon-preview.png").write_bytes(png(256))
    print(out, out.stat().st_size, "bytes")
