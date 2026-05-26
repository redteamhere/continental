"""
PIL-based profile card image generator for the Continental escrow bot.

The banner (assets/banner.jpg) already contains the pre-designed dark card
areas at the bottom.  This module:
  1. Loads the banner at natural aspect ratio (scaled to 800 px wide)
  2. Covers the placeholder text in the existing cards with matching fills
  3. Draws the real user data (@username, name, deposit) on top
"""
from __future__ import annotations

import os
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

# ─── Output width ─────────────────────────────────────────────────────────────
TARGET_W = 800   # image is resized to this width; height scales proportionally

# ─── Card position constants (fractions of final image size) ──────────────────
# These are calibrated to the Continental banner image.
# Tweak these if the banner image changes.
CARD_TOP_FRAC    = 0.845   # card strip starts here (fraction from top)
CARD_BOT_FRAC    = 0.978   # card strip ends here
CARD_SPLIT_FRAC  = 0.584   # left/right card boundary (fraction of width)
CARD_GAP_PX      = 13      # horizontal gap between the two card areas (px, at 800 w)

# Card fill colour — must match the dark card background already in the image
CARD_FILL        = (34, 31, 28, 245)   # RGBA  (opaque enough to cover old text)

# ─── Text colours ────────────────────────────────────────────────────────────
C_HANDLE  = (155, 155, 155, 255)  # @username — matches card's muted style
C_NAME    = (235, 235, 235, 255)  # bold display name — white
C_LABEL   = (140, 140, 140, 255)  # "Deposit" / "Депозит" label
C_AMOUNT  = (210, 175, 50,  255)  # deposit value — gold


# ─── Font loader ─────────────────────────────────────────────────────────────
def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
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
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ─── Background loader ───────────────────────────────────────────────────────
def _load_background() -> Image.Image:
    """
    Load the banner at its natural aspect ratio, scaled to TARGET_W wide.
    Falls back to a generated dark background if no file is present.
    """
    banner_path = next((p for p in _BANNER_CANDIDATES if os.path.exists(p)), None)

    if banner_path:
        img = Image.open(banner_path).convert("RGBA")
        new_h = int(TARGET_W * img.height / img.width)
        return img.resize((TARGET_W, new_h), Image.Resampling.LANCZOS)

    # ── Fallback: generated dark background with full card design ──────
    W, H = TARGET_W, 978
    bg = Image.new("RGBA", (W, H), (10, 9, 8, 255))
    d  = ImageDraw.Draw(bg)
    for y in range(H):
        luma = int(10 + 10 * y / H)
        d.line([(0, y), (W, y)], fill=(luma, int(luma * 0.88), int(luma * 0.72), 255))
    try:
        wm_f = _font(92, bold=True)
        d.text((W // 2, H // 2 - 60), "CONTINENTAL",
               fill=(28, 24, 18, 255), font=wm_f, anchor="mm")
    except Exception:
        pass
    # Draw the two card outlines for the fallback
    card_y = int(H * CARD_TOP_FRAC)
    card_b = int(H * CARD_BOT_FRAC)
    split  = int(W * CARD_SPLIT_FRAC)
    d.rounded_rectangle([(0, card_y), (split, card_b)],          radius=10, fill=(34, 31, 28, 240))
    d.rounded_rectangle([(split + CARD_GAP_PX, card_y), (W, card_b)], radius=10, fill=(34, 31, 28, 240))
    return bg


# ─── Main generator ──────────────────────────────────────────────────────────
def generate_profile_card(
    username:      Optional[str],
    display_name:  str,
    deposit_str:   str,
    role_label:    str,
    deposit_label: str = "Deposit",
) -> BytesIO:
    """
    Overlay real user data on the pre-designed banner card areas.

    Parameters
    ----------
    username      : Telegram @username (no @), or None
    display_name  : Full name
    deposit_str   : Formatted escrow balance, e.g. "$0.00"
    role_label    : Localised role string, e.g. "👤 User"
    deposit_label : Localised label, e.g. "Deposit" / "Депозит"
    """
    img    = _load_background()
    IW, IH = img.size

    # ── Compute card geometry from image fractions ────────────────────
    card_y  = int(IH * CARD_TOP_FRAC)
    card_b  = int(IH * CARD_BOT_FRAC)
    card_h  = card_b - card_y
    split_x = int(IW * CARD_SPLIT_FRAC)
    right_x = split_x + CARD_GAP_PX

    # ── Step 1: cover existing placeholder text ────────────────────────
    # Draw the same dark fill as the card background, but slightly inside
    # the card boundaries so we don't touch the rounded-corner edges.
    cover = Image.new("RGBA", (IW, IH), (0, 0, 0, 0))
    cd    = ImageDraw.Draw(cover)
    inset = 8   # px inset from card edge to avoid edge artefacts
    # Left card cover
    cd.rectangle(
        [(inset, card_y + inset), (split_x - inset, card_b - inset)],
        fill=CARD_FILL,
    )
    # Right card cover
    cd.rectangle(
        [(right_x + inset, card_y + inset), (IW - inset, card_b - inset)],
        fill=CARD_FILL,
    )
    img = Image.alpha_composite(img, cover)

    # ── Step 2: draw real user text ────────────────────────────────────
    draw   = ImageDraw.Draw(img)
    pad_x  = 26              # text left-padding inside each card
    line1_y = card_y + int(card_h * 0.18)   # @username / label row
    line2_y = card_y + int(card_h * 0.50)   # name / amount row

    handle = f"@{username}" if username else display_name

    # — Left card —
    tx = pad_x
    draw.text((tx, line1_y), handle,       fill=C_HANDLE, font=_font(20))
    draw.text((tx, line2_y), display_name, fill=C_NAME,   font=_font(30, bold=True))

    # — Right card —
    rx = right_x + pad_x
    draw.text((rx, line1_y), deposit_label, fill=C_LABEL,  font=_font(18))
    draw.text((rx, line2_y), deposit_str,   fill=C_AMOUNT, font=_font(38, bold=True))

    # ── Step 3: export ────────────────────────────────────────────────
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92, optimize=True)
    buf.seek(0)
    return buf
