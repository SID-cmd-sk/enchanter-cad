"""
fonts.py
Stroke-font engine for PyCAD.

Turns a string into *real, machineable geometry* (Line / Arc) so the G-code
toolpath actually cuts or engraves text as single-line / engraving geometry.

Two text commands use this engine:

  * TEXT   (general)  - the original QCAD .cxf stroke font (normal.cxf), drawn
                          as a single pass of Line + Arc centerlines.  This is
                          the "normal" CAD font look.
  * TEXTS  (single)   - single-line / engraving font: Line + Arc centerlines
                          (identical output to TEXT, kept as an explicit
                          single-line command).

Glyph shapes come from a public-domain QCAD .cxf stroke font in fonts/
(normal.cxf, Andrew Mustun / QCAD).  Drop in another .cxf and call
set_cxf_font(...) to change faces.  Because the output is LINE / ARC, the
G-code engine machines text automatically.

API:
    list_fonts()                       -> ["single", "general"]
    list_cxf_fonts()                   -> font file names available
    set_cxf_font(name)                 -> switch the .cxf used
    render_text(text, pos, height, font="single", rotation=0.0, stroke=0.18)
         -> returns (entities, info)
"""

import math
import os
import re

from entities import Line, Arc


# --------------------------------------------------------------------------
# .cxf loading
# --------------------------------------------------------------------------
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# char key -> list of primitive dicts:
#   {"type":"L", "x1":..,"y1":..,"x2":..,"y2":..}
#   {"type":"A", "cx":..,"cy":..,"r":..,"a0":..(deg),"a1":..(deg)}
_GLYPHS = {}
_CXF_NAME = "normal.cxf"
_CAP_HEIGHT = 9.0
_WORD_SPACE = 6.75
_LETTER_SPACE = 3.0


def _parse_cxf(path):
    glyphs = {}
    key = None
    strokes = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^\[(.+?)\]\s*\d*$", line)
            if m:
                if key is not None:
                    glyphs[key] = strokes
                key = m.group(1)
                strokes = []
                continue
            if key is None:
                continue
            if line.startswith("L "):
                parts = [float(v) for v in line[2:].split(",")]
                if len(parts) == 4:
                    x1, y1, x2, y2 = parts
                    strokes.append({"type": "L", "x1": x1, "y1": y1,
                                    "x2": x2, "y2": y2})
            elif line.startswith("A "):
                parts = [float(v) for v in line[2:].split(",")]
                if len(parts) == 5:
                    cx, cy, r, a0, a1 = parts
                    strokes.append({"type": "A", "cx": cx, "cy": cy,
                                    "r": r, "a0": a0, "a1": a1})
    if key is not None:
        glyphs[key] = strokes
    return glyphs


_load_default_done = False


def _load_default():
    global _GLYPHS, _load_default_done
    path = os.path.join(_FONT_DIR, _CXF_NAME)
    if os.path.exists(path):
        _GLYPHS = _parse_cxf(path)
    else:
        _GLYPHS = {}
    _load_default_done = True


_load_default()


def list_fonts():
    return ["general", "single"]


def list_cxf_fonts():
    if not os.path.isdir(_FONT_DIR):
        return []
    return sorted(f for f in os.listdir(_FONT_DIR) if f.lower().endswith(".cxf"))


def set_cxf_font(name):
    """Switch the .cxf file used for the stroke fonts."""
    global _CXF_NAME, _GLYPHS
    if os.path.isabs(name) and os.path.exists(name):
        _CXF_NAME = os.path.basename(name)
        path = name
    else:
        cand = name if name.lower().endswith(".cxf") else name + ".cxf"
        path = os.path.join(_FONT_DIR, cand)
    if not os.path.exists(path):
        return False
    _CXF_NAME = os.path.basename(path)
    _GLYPHS = _parse_cxf(path)
    return True


def current_cxf_font():
    return _CXF_NAME


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def _deg2rad(d):
    return d * math.pi / 180.0


def _glyph_strokes(ch):
    return _GLYPHS.get(ch, [])


def _char_advance(ch):
    strokes = _glyph_strokes(ch)
    if not strokes:
        return _WORD_SPACE if ch == " " else 4.0
    xs = []
    for s in strokes:
        if s["type"] == "L":
            xs.extend([s["x1"], s["x2"]])
        else:
            xs.extend([s["cx"] - s["r"], s["cx"] + s["r"]])
    if not xs:
        return 4.0
    return (max(xs) - min(xs)) + _LETTER_SPACE


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def render_text(text, pos, height, font="single", stroke=0.18, rotation=0.0):
    """Render `text` into machineable entities. Returns (entities, info).

    Both `general` and `single` draw the glyph centerlines as Line + Arc
    entities (single-line / engraving geometry).  The `double` style has been
    removed.
    """
    text = text or ""
    if font not in ("general", "single"):
        font = "single"
    px, py = pos
    scale = height / _CAP_HEIGHT
    entities = []
    x_cursor = 0.0

    def _place(fx, fy):
        wx = px + x_cursor * scale + fx * scale
        wy = py + fy * scale
        if rotation:
            dx, dy = wx - px, wy - py
            c, s = math.cos(rotation), math.sin(rotation)
            wx = px + dx * c - dy * s
            wy = py + dx * s + dy * c
        return (wx, wy)

    for ch in text:
        if ch == " ":
            x_cursor += _WORD_SPACE
            continue
        strokes = _glyph_strokes(ch)
        if not strokes:
            x_cursor += _char_advance(ch)
            continue

        for s in strokes:
            if s["type"] == "L":
                p1 = _place(s["x1"], s["y1"])
                p2 = _place(s["x2"], s["y2"])
                entities.append(Line(p1, p2))
            else:
                a0 = _deg2rad(s["a0"])
                a1 = _deg2rad(s["a1"])
                cx, cy = _place(s["cx"], s["cy"])
                entities.append(Arc((cx, cy), s["r"] * scale, a0, a1))
        x_cursor += _char_advance(ch)

    total_w = x_cursor
    bbox = (px, py, px + total_w * scale, py + height)
    info = {"bbox": bbox, "width": total_w * scale, "font": font,
            "cxf": _CXF_NAME}
    return entities, info


def text_bbox(text, pos, height, font="single"):
    ents, info = render_text(text, pos, height, font=font)
    return info["bbox"]
