"""Featured/inline image handling.

Convention (from site/scripts/gen-article-images.mjs): every article ships a
branded SVG illustration rasterized to PNG at /img/articles/<name>.png
(1200×630). The writer agent produces the motif; this module validates the
SVG, rasterizes it deterministically, and optimizes the PNG. Images are never
kept in the engine repo — they are committed to the site repo only.
"""
from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from . import log

BRAND = "#0e7c5b"
TINT = "#e6f4ef"

MAX_SVG_BYTES = 200_000
FORBIDDEN_SVG = ("<script", "foreignObject", "xlink:href", 'href="http', "url(http", "@import", "<image")


def fallback_svg(section: str = "ARTIFICIAL INTELLIGENCE") -> str:
    """Brand-consistent frame when the writer produced no motif."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <rect width="1200" height="630" fill="{TINT}"/>
  <rect x="40" y="40" width="1120" height="550" fill="none" stroke="{BRAND}" stroke-width="2" opacity="0.25"/>
  <circle cx="600" cy="290" r="90" fill="none" stroke="{BRAND}" stroke-width="10"/>
  <circle cx="600" cy="290" r="22" fill="{BRAND}"/>
  <text x="70" y="560" font-family="Georgia, 'Times New Roman', serif" font-size="26" letter-spacing="6" fill="{BRAND}">DIGITAL TECH ADVISER</text>
  <text x="1130" y="560" font-family="Georgia, 'Times New Roman', serif" font-size="20" letter-spacing="3" fill="{BRAND}" opacity="0.75" text-anchor="end">{section}</text>
</svg>'''


class ImageError(Exception):
    pass


def validate_svg(svg: str) -> list[str]:
    """Structural safety checks — returns a list of problems (empty = ok)."""
    problems = []
    if len(svg.encode()) > MAX_SVG_BYTES:
        problems.append(f"svg too large ({len(svg.encode())} bytes)")
    low = svg.lower()
    for bad in FORBIDDEN_SVG:
        if bad.lower() in low:
            problems.append(f"forbidden SVG construct: {bad}")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        problems.append(f"unparseable SVG: {e}")
        return problems
    if not root.tag.endswith("svg"):
        problems.append("root element is not <svg>")
    vb = root.get("viewBox", "")
    if vb.strip() != "0 0 1200 630":
        problems.append(f"viewBox must be '0 0 1200 630', got '{vb}'")
    return problems


def _try(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except FileNotFoundError:
        return False


def rasterize(svg_path: Path, png_path: Path) -> None:
    """SVG → PNG at 1200×630 using the first available rasterizer."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    s, p = str(svg_path), str(png_path)
    if _try(["rsvg-convert", "-w", "1200", "-h", "630", "-o", p, s]):
        return
    if _try(["inkscape", s, "--export-type=png", f"--export-filename={p}", "-w", "1200", "-h", "630"]):
        return
    try:
        import cairosvg
        cairosvg.svg2png(url=s, write_to=p, output_width=1200, output_height=630)
        return
    except ImportError:
        pass
    except Exception as e:
        raise ImageError(f"cairosvg failed: {e}")
    raise ImageError("no SVG rasterizer available (need rsvg-convert, inkscape, or cairosvg)")


def optimize_png(png_path: Path) -> None:
    """Palette-quantize + optimize. Illustrations compress well to ≤256 colors."""
    try:
        from PIL import Image
    except ImportError:
        return
    try:
        img = Image.open(png_path).convert("RGBA")
        q = img.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
        q.save(png_path, optimize=True)
    except Exception as e:  # optimization is best-effort, never fatal
        log.emit(f"images: png optimize skipped ({e})")


def build_featured(svg_text: str | None, slug: str, workdir: Path, section: str) -> tuple[Path, Path]:
    """Validate (or synthesize) the motif SVG, rasterize, optimize.

    Returns (svg_path, png_path) inside workdir/images/<slug>/.
    """
    out_dir = workdir / "images" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    if not svg_text or validate_svg(svg_text):
        if svg_text:
            log.emit(f"images: writer SVG rejected {validate_svg(svg_text)} — using fallback frame")
        svg_text = fallback_svg(section)
    svg_path = out_dir / "featured.svg"
    svg_path.write_text(svg_text)
    png_path = out_dir / "featured.png"
    rasterize(svg_path, png_path)
    optimize_png(png_path)
    kb = png_path.stat().st_size // 1024
    log.emit(f"images: featured PNG built ({kb} KiB)")
    return svg_path, png_path
