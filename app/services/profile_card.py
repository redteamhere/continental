"""
PIL-based profile card image generator for the Continental escrow bot.

Place your banner image at:  assets/banner.jpg  (or .png / .webp)
The image is displayed at its NATURAL aspect ratio (no cropping).
Two rounded info cards are overlaid on the bottom of the banner.
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

# ─── Layout constants ────────────────────────────────────────────────────────
TARGET_W   = 800    # resize banner to this width; height scales proportionally
CARD_H     = 145    # height of each info card
CARD_PAD   = 20     # margin from edges and bottom
CARD_GAP   = 14     # gap between the two cards
CARD_SPLIT = 0.57   # fraction of usable width given to the LEFT card
RADIUS     = 12     # rounded-corner radius
ACCENT_W   = 4      # width of the green accent bar on the left card

# ─── Colour palette ──────────────────────────────────────────────────────────
C_CARD_BG  = (28, 26, 24, 215)    # RGBA  dark semi-transparent card fill
C_HANDLE   = (165, 165, 165, 255) # @username
C_NAME     = (235, 235, 235, 255) # display name (bold white)
C_LABEL    = (145, 145, 145, 255) # "Deposit" label
C_AMOUNT   = (210, 175, 50,  255) # deposit value (gold)
C_ACCENT   = (68,  190, 90,  255) # green left-card accent bar
C_VIGNETTE = (0,   0,   0,   255) # bottom vignette fill


# ─── Font loader ─────────────────────────────────────────────────────────────
def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load TrueType font; works on Windows (dev) and Linux/Railway (prod)."""
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
        return ImageFont.load_default(size=size)   # Pillow 10+
    except TypeError:
        return ImageFont.load_default()


# ─── Background loader ───────────────────────────────────────────────────────
def _load_background() -> Image.Image:
    """
    Load banner at natural aspect ratio scaled to TARGET_W wide.
    Falls back to a generated dark gradient if no file is found.
    """
    banner_path = next((p for p in _BANNER_CANDIDATES if os.path.exists(p)), None)

    if banner_path:
        img = Image.open(banner_path).convert("RGBA")
        # Scale width to TARGET_W, keep aspect ratio — NO cropping
        new_h = int(TARGET_W * img.height / img.width)
        return img.resize((TARGET_W, new_h), Image.Resampling.LANCZOS)

    # ── Generated fallback: dark Continental-styled background ─────────
    W, H = TARGET_W, 980
    bg = Image.new("RGBA", (W, H), (10, 9, 8, 255))
    d  = ImageDraw.Draw(bg)
    for y in range(H):
        luma = int(10 + 10 * y / H)
        d.line([(0, y), (W, y)], fill=(luma, int(luma * 0.88), int(luma * 0.72), 255))
    try:
        wm_f = _font(96, bold=True)
        d.text((W // 2, H // 2 - 60), "CONTINENTAL",
               fill=(28, 24, 18, 255), font=wm_f, anchor="mm")
    except Exception:
        pass
    return bg


# ─── Overlay helpers ─────────────────────────────────────────────────────────
def _draw_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    """Draw a rounded-rectangle card background."""
    draw.rounded_rectangle(box, radius=RADIUS, fill=C_CARD_BG)


def _bottom_vignette(img: Image.Image, vignette_h: int = 220) -> Image.Image:
    """Add a dark fade at the very bottom so cards are readable on any photo."""
    W, H = img.size
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)
    for y in range(vignette_h):
        alpha = int(170 * (y / vignette_h) ** 1.5)  # smooth curve
        d.line([(0, H - vignette_h + y), (W, H - vignette_h + y)],
               fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img, ov)


# ─── Main generator ──────────────────────────────────────────────────────────
def generate_profile_card(
    username:      Optional[str],
    display_name:  str,
    deposit_str:   str,
    role_label:    str,
    deposit_label: str = "Deposit",
) -> BytesIO:
    """
    Build and return a JPEG BytesIO of the profile card.

    The banner image is displayed at full natural height (no cropping).
    Two rounded cards are overlaid at the bottom of the image.

    Parameters
    ----------
    username      : Telegram @username (no @) or None
    display_name  : Full name shown below the handle
    deposit_str   : Formatted escrow balance, e.g. "$12.50"
    role_label    : Localised role string, e.g. "👤 User"
    deposit_label : Localised label, e.g. "Deposit" / "Депозит"
    """
    img = _load_background()
    img = _bottom_vignette(img)

    IW, IH = img.size   # actual image dimensions after scaling

    # ── Card geometry ─────────────────────────────────────────────────
    usable_w  = IW - 2 * CARD_PAD - CARD_GAP
    left_w    = int(usable_w * CARD_SPLIT)
    right_w   = usable_w - left_w

    card_y    = IH - CARD_H - CARD_PAD   # top of cards

    left_box  = (CARD_PAD,
                 card_y,
                 CARD_PAD + left_w,
                 IH - CARD_PAD)

    right_x   = CARD_PAD + left_w + CARD_GAP
    right_box = (right_x,
                 card_y,
                 right_x + right_w,
                 IH - CARD_PAD)

    # ── Draw card backgrounds ─────────────────────────────────────────
    ov_cards = Image.new("RGBA", (IW, IH), (0, 0, 0, 0))
    cd = ImageDraw.Draw(ov_cards)
    _draw_card(cd, left_box)
    _draw_card(cd, right_box)
    img = Image.alpha_composite(img, ov_cards)

    # ── Draw green accent bar on left card ───────────────────────────
    ov_accent = Image.new("RGBA", (IW, IH), (0, 0, 0, 0))
    ad = ImageDraw.Draw(ov_accent)
    bar_x1 = CARD_PAD
    bar_x2 = CARD_PAD + ACCENT_W
    bar_y1 = card_y + RADIUS
    bar_y2 = IH - CARD_PAD - RADIUS
    ad.rectangle([(bar_x1, bar_y1), (bar_x2, bar_y2)], fill=C_ACCENT)
    img = Image.alpha_composite(img, ov_accent)

    # ── Text on cards ─────────────────────────────────────────────────
    draw = ImageDraw.Draw(img)
    tx = CARD_PAD + ACCENT_W + 14     # left card text x (after accent bar)
    ty = card_y                        # left card top y

    handle = f"@{username}" if username else display_name
    draw.text((tx, ty + 18),  handle,       fill=C_HANDLE, font=_font(19))
    draw.text((tx, ty + 50),  display_name, fill=C_NAME,   font=_font(30, bold=True))

    # Right card text
    rx = right_x + 18
    draw.text((rx, card_y + 18), deposit_label, fill=C_LABEL,  font=_font(17))
    draw.text((rx, card_y + 50), deposit_str,   fill=C_AMOUNT, font=_font(38, bold=True))

    # ── Output ────────────────────────────────────────────────────────
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92, optimize=True)
    buf.seek(0)
    return buf
