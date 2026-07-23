"""
branding.py  -  Generates ENCHANTR-CAD 2D V1.1 branding assets from the
canonical logo (assets/branding/logo.png).  Uses PIL only (stable in headless
environments; PyQt QPainter crashes here).

Outputs:
  assets/icons/appicon.ico        multi-size app icon
  assets/icons/appicon.png        256px icon
  assets/branding/splash.png       animated splash background (900x540)
  assets/branding/banner.png       installer / About banner (520x120)
  assets/startbg.png               welcome/start screen background (1100x680)
"""
import os
import math

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.abspath(os.path.join(HERE, "..", "assets"))
BRAND = os.path.join(ASSETS, "branding")
ICONS = os.path.join(ASSETS, "icons")
for p in (BRAND, ICONS):
    os.makedirs(p, exist_ok=True)

BG0 = (13, 17, 23)
BG1 = (22, 27, 34)
ACCENT = (58, 155, 255)
ACCENT2 = (0, 229, 192)
GRID = (29, 38, 48)
TXT = (232, 238, 245)
MUTE = (139, 151, 165)


def _font(size, bold=True):
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/segoeuil.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _rounded_tile(size, src_logo):
    """Square icon tile: dark bg + faint grid + logo centered + accent frame."""
    img = Image.new("RGBA", (size, size), BG0 + (255,))
    d = ImageDraw.Draw(img)
    m = max(2, size // 24)
    step = max(6, size // 14)
    d.line([(m, m), (size - m, m), (size - m, size - m), (m, size - m),
            (m, m)], fill=ACCENT + (255,), width=max(1, size // 90))
    # faint grid
    gd = ImageDraw.Draw(img, "RGBA")
    for x in range(m, size - m, step):
        gd.line([(x, m), (x, size - m)], fill=GRID + (120,), width=1)
    for y in range(m, size - m, step):
        gd.line([(m, y), (size - m, y)], fill=GRID + (120,), width=1)
    # logo fitted to ~62% with margin
    lm = int(size * 0.19)
    box = (lm, lm, size - lm, size - lm)
    logo = src_logo.convert("RGBA").resize((size - 2 * lm, size - 2 * lm))
    # ensure logo sits on opaque bg (composite over tile)
    img.paste(logo, box, logo)
    return img


def _make_icon_set(src_logo):
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = []
    for s in sizes:
        tile = _rounded_tile(s, src_logo)
        tile.save(os.path.join(ICONS, "appicon_%d.png" % s))
        frames.append(tile)
    frames[0].save(os.path.join(ICONS, "appicon.ico"),
                   sizes=[(f.width, f.height) for f in frames])
    frames[-1].save(os.path.join(ICONS, "appicon.png"))
    return frames[-1]


def _dotgrid(w, h, col):
    img = Image.new("RGBA", (w, h), col + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(0, w, 24):
        for y in range(0, h, 24):
            d.point((x, y), fill=GRID + (255,))
    return img


def _make_splash(src_logo, w=900, h=540):
    img = _dotgrid(w, h, BG0)
    d = ImageDraw.Draw(img, "RGBA")
    # diagonal accent rules top
    d.line([(0, 0), (w, 0)], fill=ACCENT + (255,), width=3)
    d.line([(0, 4), (w, 4)], fill=ACCENT2 + (200,), width=2)
    # blueprint arc bottom-left
    d.arc([-260, h - 280, 260, h + 240], 0, 360, fill=(20, 32, 44, 255), width=6)
    # logo tile near top center
    tile = _rounded_tile(150, src_logo)
    img.paste(tile, (w // 2 - 75, 56), tile)
    # title
    d.text((w // 2, 244), "ENCHANTR-CAD 2D", font=_font(42), fill=TXT,
           anchor="mm")
    d.text((w // 2, 304), "Parametric 2D CAD  •  CNC Toolpath Ready",
           font=_font(17, False), fill=ACCENT2, anchor="mm")
    d.text((w // 2, 344), "Version 1.1", font=_font(13, False), fill=MUTE,
           anchor="mm")
    return img


def _make_banner(src_logo, w=520, h=120):
    img = Image.new("RGBA", (w, h), BG1 + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    tile = _rounded_tile(92, src_logo)
    img.paste(tile, (14, 14), tile)
    d.text((128, 34), "ENCHANTR-CAD 2D", font=_font(24), fill=TXT, anchor="lm")
    d.text((128, 74), "2D CAD + CNC G-code  •  V1.1", font=_font(13, False),
           fill=ACCENT2, anchor="lm")
    d.line([(0, h - 2), (w, h - 2)], fill=(43, 51, 64, 255), width=2)
    return img


def _make_startbg(src_logo, w=1100, h=680):
    return _make_splash(src_logo, w, h)


def main():
    src = Image.open(os.path.join(BRAND, "logo.png")).convert("RGBA")
    _make_icon_set(src)
    sp = _make_splash(src)
    sp.save(os.path.join(BRAND, "splash.png"))
    os.makedirs(os.path.join(HERE, "..", "resources", "splash"), exist_ok=True)
    sp.save(os.path.join(HERE, "..", "resources", "splash", "splash.png"))
    _make_banner(src).save(os.path.join(BRAND, "banner.png"))
    _make_startbg(src).save(os.path.join(ASSETS, "startbg.png"))
    print("OK branding assets:")
    for f in sorted(os.listdir(BRAND)) + ["../icons/" + f for f in os.listdir(ICONS)] + ["../startbg.png"]:
        print("  ", f)


if __name__ == "__main__":
    main()
