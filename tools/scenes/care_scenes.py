"""Isometric scenes for the showcase site (site/assets/iso/*.svg), drawn with isoscene.

    python tools/scenes/care_scenes.py site/assets/iso

Labels live in the page's HTML next to each picture, not in the SVG. Glyphs are Lucide 0.468 (ISC licence),
vendored in tools/scenes/lucide.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\code\isoscene")
from isoscene import *  # noqa: E402,F403

ICONS = Path(__file__).parent / "lucide"
BRONZE = ("F6CBA8", "D99364", "E3A57A", "B8703F", "AA6436", "7A4425", "E8975F")


def icon(name, colour="0B5CC9"):
    svg = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    return lucide(re.sub(r"\s+", " ", inner).strip(), colour)


def backdrop(s, cx=0.0, cy=0.0, r1=3.4, r2=6.0, colour="5B7CFA"):
    s.ring(cx, cy, r1, op=0.08)
    s.ring(cx, cy, r2, color=colour, op=0.28, dash="0.12 0.12")


def hero():
    """Sources -> ADLS raw -> Fabric compute -> ADLS lake -> dashboard, SQL endpoint, other engines."""
    s = Scene()
    backdrop(s, -1.5, -1.5, 3.6, 6.4)
    sources = [(-8.8, -1.9, "file-spreadsheet"), (-8.8, -0.2, "calendar-clock"),
               (-7.2, -1.35, "smartphone"), (-7.2, 0.35, "receipt")]
    for x, y, _ in sources:
        s.path([(x + 1.0, y + 0.5, 0), (-5.6, 0.0, 0)])
    for x, y, g in sources:
        s.box(x, y, 0, 1.0, 1.0, 0.7, ICE, glyph=icon(g), lw=0.6, r=0.13, glow=0.2)
    # ADLS raw landing zone
    s.box(-5.6, -0.6, 0, 1.2, 1.2, 0.85, BLUE2, glyph=icon("hard-drive", "FFFFFF"), lw=0.7, r=0.14, glow=0.3)
    s.path([(-4.4, 0.0, 0), (-1.8, 0.0, 0)])
    # Fabric: compute on a platform
    s.box(-1.8, -1.8, 0, 3.6, 3.6, 0.45, NAVY2, order=(0, 0), r=0.16, glow=0.25)
    s.box(-0.85, -0.85, 0.45, 1.7, 1.7, 0.42, ICE, glyph=icon("cpu"), lw=1.0, order=(0, 10), r=0.14,
          glow=0.55, ground=False)
    # ADLS lake (Delta), the system of record
    s.path([(0.0, -1.8, 0), (0.0, -3.8, 0)])
    s.box(-0.6, -5.0, 0, 1.2, 1.2, 0.85, BLUE2, glyph=icon("database", "FFFFFF"), lw=0.7, r=0.14, glow=0.4)
    outs = [(-2.1, -8.0, "layout-dashboard"), (-0.5, -8.0, "terminal"), (1.1, -8.0, "layers")]
    s.path([(0.0, -5.0, 0), (0.0, -6.5, 0)])
    for x, y, _ in outs:
        s.path([(0.0, -6.5, 0), (x + 0.5, -6.5, 0), (x + 0.5, y + 1.0, 0)], order=-89)
    for x, y, g in outs:
        s.box(x, y, 0, 1.0, 1.0, 0.62, ICE, glyph=icon(g), lw=0.6, r=0.13, glow=0.2)
    return s.render()


def medallion():
    """Raw files -> bronze (7 tables) -> silver (9) -> gold (4) -> four answers."""
    s = Scene()
    backdrop(s, -4.5, -1.0, 3.8, 7.2)
    s.box(-12.4, -0.5, 0, 1.0, 1.0, 0.7, GREY2, glyph=icon("hard-drive", "FFFFFF"), lw=0.6, r=0.13, glow=0.15)
    s.path([(-11.4, 0.0, 0), (-2.2, 0.0, 0)], order=-91)
    s.path([(-1.0, -1.2, 0), (-1.0, -3.6, 0)])

    def layer(x0, pal, n, cols, tile, glow):
        s.box(x0, -1.2, 0, 2.4, 2.4, 0.3, pal, order=(x0, 0), r=0.12, glow=glow)
        gap = (2.4 - cols * tile) / (cols + 1)
        for i in range(n):
            cx, cy = i % cols, i // cols
            tx, ty = x0 + gap + cx * (tile + gap), -1.2 + gap + cy * (tile + gap)
            s.box(tx, ty, 0.3, tile, tile, 0.22, pal, order=(x0, 10 + tx + ty), r=0.06, glow=0, ground=False)

    layer(-9.6, BRONZE, 7, 3, 0.5, 0.2)
    layer(-5.9, ICE, 9, 3, 0.5, 0.2)
    layer(-2.2, GOLD2, 4, 2, 0.8, 0.45)
    outs = [(-4.1, -5.0, "wallet"), (-2.6, -5.0, "calendar-clock"), (-1.1, -5.0, "user-round-check"),
            (0.4, -5.0, "receipt")]
    for x, y, _ in outs:
        s.path([(-1.0, -3.6, 0), (x + 0.5, -3.6, 0), (x + 0.5, y + 1.0, 0)], order=-89)
    for x, y, g in outs:
        s.box(x, y, 0, 1.0, 1.0, 0.62, ICE, glyph=icon(g), lw=0.6, r=0.13, glow=0.2)
    return s.render()


def two_engines():
    """One folder of Spark SQL runs on a laptop (DuckDB) and on Fabric (Spark), landing the same tables."""
    s = Scene()
    backdrop(s, -1.0, 0.0, 3.4, 6.0)
    s.box(-6.6, -0.6, 0, 1.2, 1.2, 0.8, TAG2, glyph=icon("file-code"), lw=0.72, r=0.14, glow=0.5)
    # local lane (back) and cloud lane (front)
    s.path([(-5.4, 0.0, 0), (-4.4, 0.0, 0), (-4.4, -2.2, 0), (2.4, -2.2, 0)], order=-91)
    s.path([(-4.4, 0.0, 0), (-4.4, 2.2, 0), (2.4, 2.2, 0)], order=-91)
    s.box(-2.2, -2.8, 0, 1.2, 1.2, 0.62, ICE, glyph=icon("laptop"), lw=0.72, r=0.14, glow=0.25)
    s.box(2.4, -2.75, 0, 1.1, 1.1, 0.7, ICE, glyph=icon("database"), lw=0.62, r=0.14, glow=0.2)
    s.box(-2.8, 1.0, 0, 2.4, 2.4, 0.35, NAVY2, order=(-0.4, 0), r=0.14, glow=0.25)
    s.box(-2.15, 1.65, 0.35, 1.1, 1.1, 0.36, ICE, glyph=icon("cpu"), lw=0.72, order=(-0.4, 10), r=0.12,
          glow=0.35, ground=False)
    s.box(2.4, 1.6, 0, 1.2, 1.2, 0.85, BLUE2, glyph=icon("database", "FFFFFF"), lw=0.7, r=0.14, glow=0.35)
    return s.render()


def identity():
    """Entra ID in the middle: your login reaches storage and the dashboard; Fabric's token is refused."""
    s = Scene()
    backdrop(s, -1.0, 0.0, 3.2, 5.8)
    s.path([(-5.0, 0.0, 0), (-2.4, 0.0, 0)])
    s.box(-6.2, -0.6, 0, 1.2, 1.2, 0.7, TAG2, glyph=PERSON_T, lw=0.7, r=0.14, glow=0.3)
    s.box(-2.4, -0.8, 0, 1.6, 1.6, 0.8, BLUE2, glyph=icon("shield-check", "FFFFFF"), lw=0.9, r=0.15, glow=0.55)
    s.path([(-1.6, -0.8, 0), (-1.6, -2.6, 0), (2.0, -2.6, 0)], order=-91)
    s.path([(-0.8, 0.0, 0), (2.0, 0.0, 0)], order=-91)
    s.path([(-1.6, 0.8, 0), (-1.6, 2.6, 0), (2.0, 2.6, 0)], order=-91,
           color="8A929C", flow=False, halo=False, dash="0.12 0.12")
    s.box(2.0, -3.2, 0, 1.2, 1.2, 0.85, BLUE2, glyph=icon("database", "FFFFFF"), lw=0.7, r=0.14, glow=0.3)
    s.box(2.0, -0.6, 0, 1.2, 1.2, 0.7, ICE, glyph=icon("layout-dashboard"), lw=0.7, r=0.14, glow=0.25)
    s.box(2.0, 2.0, 0, 1.2, 1.2, 0.7, GREY2, glyph=icon("cpu", "FFFFFF"), lw=0.7, r=0.14, glow=0.1)
    s.side_glyph(2.32, 3.2, 0.62, 0.56, icon("triangle-alert", "FF6B70"), order=(5.2, 1))
    return s.render()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "site/assets/iso")
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in [("hero", hero), ("medallion", medallion), ("two-engines", two_engines), ("identity", identity)]:
        (out / f"{name}.svg").write_text(fn(), encoding="utf-8")
        print("wrote", out / f"{name}.svg")
