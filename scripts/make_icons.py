"""Draw the CreditScope app icons (PNG + SVG) with the standard library only.

    python scripts/make_icons.py          # writes assets/icons/*
"""
import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "icons"
AMBER, GREEN = (255, 176, 32), (47, 209, 139)
BG_TOP, BG_BOT = (20, 32, 52), (6, 10, 16)
LINE = [(-0.34, 0.24), (-0.12, 0.0), (0.04, 0.14), (0.30, -0.28)]


def seg_dist(px, py, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def shade(u, v, maskable):
    """Colour and alpha at normalised point (u, v) in [-1, 1]."""
    if maskable:
        alpha = 1.0
    else:
        qx, qy = abs(u) - 0.58, abs(v) - 0.58
        d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - 0.34
        alpha = 1.0 if d < 0 else 0.0
    if alpha == 0.0:
        return (0, 0, 0), 0.0
    t = (v + 1) / 2
    col = tuple(BG_TOP[i] * (1 - t) + BG_BOT[i] * t for i in range(3))
    r = math.hypot(u, v)
    if abs(r - 0.60) < 0.045:
        col = AMBER
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):          # crosshair ticks
        along = u * sx + v * sy
        across = abs(-u * sy + v * sx)
        if 0.47 < along < 0.76 and across < 0.028:
            col = AMBER
    d = min(seg_dist(u, v, LINE[i], LINE[i + 1]) for i in range(len(LINE) - 1))
    if d < 0.05 or math.hypot(u - LINE[-1][0], v - LINE[-1][1]) < 0.085:
        col = GREEN
    return col, alpha


def render(size, maskable, ss=2):
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    u = (x + (sx + 0.5) / ss) / size * 2 - 1
                    v = (y + (sy + 0.5) / ss) / size * 2 - 1
                    col, a = shade(u, v, maskable)
                    for i in range(3):
                        acc[i] += col[i] * a
                    acc[3] += a
            a = acc[3] / (ss * ss)
            rgb = [int(acc[i] / acc[3]) if acc[3] else 0 for i in range(3)]
            row += bytes(rgb + [int(round(a * 255))])
        rows.append(bytes(row))
    return rows


def write_png(path, size, maskable):
    raw = b"".join(render(size, maskable))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 2 2">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#142034"/><stop offset="1" stop-color="#060a10"/></linearGradient></defs>
<rect x="-0.92" y="-0.92" width="1.84" height="1.84" rx="0.34" fill="url(#g)"/>
<circle r="0.6" fill="none" stroke="#ffb020" stroke-width="0.09"/>
<g stroke="#ffb020" stroke-width="0.056" stroke-linecap="round"><path d="M0.47 0H0.76M-0.47 0H-0.76M0 0.47V0.76M0 -0.47V-0.76"/></g>
<polyline points="-0.34,0.24 -0.12,0 0.04,0.14 0.3,-0.28" fill="none" stroke="#2fd18b" stroke-width="0.1" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="0.3" cy="-0.28" r="0.085" fill="#2fd18b"/></svg>
"""

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    write_png(OUT / "icon-192.png", 192, False)
    write_png(OUT / "icon-512.png", 512, False)
    write_png(OUT / "icon-maskable-512.png", 512, True)
    write_png(OUT / "apple-touch-icon.png", 180, True)
    (OUT / "icon.svg").write_text(SVG)
    print("icons written to", OUT)
