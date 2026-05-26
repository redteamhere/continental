"""
PIL-based profile card image generator for the Continental escrow bot.

Place your banner image at:  assets/banner.jpg  (or .png / .webp)
If no banner is found, a styled dark background is generated automatically.
"""
from __future__ import annotations

import os
from decimal import Decimal
from io import BytesIO
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ─── Paths ────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "assets"))
_BANNER_CANDIDATES = [
    os.path.join(ASSETS_DIR, "banner.jpg"),
    os.path.join(ASSETS_DIR, "banner.png"),
    os.path.join(ASSETS_DIR, "banner.webp"),
]

# ─── Card dimensions ─────────────────────────────────────────────────────────
W, H      = 800, 440          # total image size
CARD_H    = 110               # height of the bottom user-info strip
BANNER_H  = H - CARD_H       # 330 px for the banner area

# ─── Colour palette ──────────────────────────────────────────────────────────
C_GOLD    = (195, 155, 60)
C_WHITE   = (235, 235, 235)
C_GRAY    = (148, 148, 148)
C_GREEN   = (85, 210, 105)
C_BG      = (10, 9, 8)
C_CARD    = (16, 14, 12, 218)   # RGBA — card strip background
C_DIVIDER = (190, 150, 55, 255) # gold divider line


# ─── Font loader ─────────────────────────────────────────────────────────────
def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """
    Try to load a TrueType font (bold or regular), fall back to PIL built-in.
    Works on both Windows (dev) and Linux/Railway (prod).
    """
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/verdanab.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/verdana.ttf",
        ]
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    # Pillow 10+ built-in with size support
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ─── Background loader ───────────────────────────────────────────────────────
def _load_background() -> Image.Image:
    """
    Load the banner image from assets/ or generate a dark Continental-themed
    background if no banner file exists.
    """
    banner_path = next((p for p in _BANNER_CANDIDATES if os.path.exists(p)), None)

    if banner_path:
        img = Image.open(banner_path).convert("RGBA")
        # Crop-fill to (W, H) while preserving aspect ratio
        img_ratio  = img.width / img.height
        tgt_ratio  = W / H
        if img_ratio > tgt_ratio:
            nw, nh = int(H * img_ratio), H
        else:
            nw, nh = W, int(W / img_ratio)
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - W) // 2
        top  = (nh - H) // 2
        return img.crop((left, top, left + W, top + H))

    # ── Generated dark background ──────────────────────────────────────
    bg = Image.new("RGBA", (W, H), C_BG + (255,))
    d  = ImageDraw.Draw(bg)

    # Subtle warm gradient
    for y in range(H):
        luma = int(10 + 10 * y / H)
        d.line([(0, y), (W, y)], fill=(luma, int(luma * 0.88), int(luma * 0.72), 255))

    # Faint "CONTINENTAL" watermark
    try:
        wm_f = _font(96, bold=True)
        d.text(
            (W // 2, BANNER_H // 2),
            "CONTINENTAL",
            fill=(28, 24, 18, 255),
            font=wm_f,
            anchor="mm",
        )
    except Exception:
        pass

    # Decorative thin gold lines
    for y_off in (60, BANNER_H - 60):
        d.line([(40, y_off), (W - 40, y_off)], fill=(70, 55, 20, 120), width=1)

    return bg


# ─── Main generator ──────────────────────────────────────────────────────────
def generate_profile_card(
    username:     Optional[str],
    display_name: str,
    deposit_str:  str,
    role_label:   str,
) -> BytesIO:
    """
    Build and return a JPEG BytesIO of the profile card.

    Parameters
    ----------
    username     : Telegram @username (without @), or None
    display_name : User's full name shown below the @handle
    deposit_str  : Formatted escrow balance string, e.g. "$12.50"
    role_label   : Localised role string, e.g. "User" / "Пользователь"
    """
    img = _load_background()

    # ── Dark gradient fade at bottom of banner → card ─────────────────
    fade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd   = ImageDraw.Draw(fade)
    fade_top = BANNER_H - 70
    for y in range(fade_top, BANNER_H):
        alpha = int(200 * (y - fade_top) / (BANNER_H - fade_top))
        fd.line([(0, y), (W, y)], fill=(8, 7, 6, alpha))
    # Solid card strip
    fd.rectangle([(0, BANNER_H), (W, H)], fill=C_CARD)
    img = Image.alpha_composite(img, fade)

    # ── Gold divider ──────────────────────────────────────────────────
    div_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(div_layer).line(
        [(0, BANNER_H), (W, BANNER_H)], fill=C_DIVIDER, width=2
    )
    img = Image.alpha_composite(img, div_layer)

    draw = ImageDraw.Draw(img)
    PAD  = 28
    cy   = BANNER_H   # top of the card strip

    # ── Left side: @username, display name, role ──────────────────────
    handle = f"@{username}" if username else display_name
    draw.text((PAD, cy + 12), handle,       fill=C_GOLD,  font=_font(22, bold=True))
    draw.text((PAD, cy + 46), display_name, fill=C_WHITE, font=_font(17))
    draw.text((PAD, cy + 78), role_label,   fill=C_GRAY,  font=_font(13))

    # ── Right side: "Deposit" label + value ───────────────────────────
    dep_x = W - 215
    draw.text((dep_x, cy + 12), "Deposit",   fill=C_GRAY,  font=_font(13))
    draw.text((dep_x, cy + 32), deposit_str, fill=C_GREEN, font=_font(26, bold=True))

    # ── Finalise ──────────────────────────────────────────────────────
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
    buf.seek(0)
    return buf
