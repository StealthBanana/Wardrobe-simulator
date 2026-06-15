"""
Generates starter clothing PNGs using only Pillow — no internet or AI needed.
Called once on first launch when the wardrobe is empty.

To add a new default item: add a row to DEFAULTS and, if it needs a new
shape, add a draw function and wire it in to _draw_item().
"""

import os
import uuid
import logging

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# ── Starter items ─────────────────────────────────────────────────────────────
# (display name, category, fill hex colour)
DEFAULTS = [
    ("Black T-Shirt",   "top",      "#1c1c1c"),
    ("Black Pants",     "bottom",   "#1c1c1c"),
    ("Black Overcoat",  "outerwear","#1c1c1c"),
    ("Black Shoes",     "shoes",    "#1c1c1c"),
    ("Black Button-Up", "top",      "#1c1c1c"),
    ("White T-Shirt",   "top",      "#f0f0f0"),
    ("White Pants",     "bottom",   "#f0f0f0"),
    ("White Overcoat",  "outerwear","#f0f0f0"),
    ("White Shoes",     "shoes",    "#f0f0f0"),
    ("White Button-Up", "top",      "#f0f0f0"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def seed_default_wardrobe(upload_folder):
    """
    Create ClothingItem rows + PNG files for all DEFAULTS.
    Called automatically on first launch when the wardrobe is empty.
    """
    from models import db, ClothingItem

    proc_dir = os.path.join(upload_folder, "clothing_processed")
    os.makedirs(proc_dir, exist_ok=True)

    new_items = []
    for name, category, color in DEFAULTS:
        # Unique filenames so re-seeding never collides
        p_fn  = f"default_{uuid.uuid4().hex}.png"
        th_fn = f"thumb_{p_fn}"
        p_path  = os.path.join(proc_dir, p_fn)
        th_path = os.path.join(proc_dir, th_fn)

        _draw_item(p_path, category, color, name)
        _make_thumb(p_path, th_path)

        new_items.append(ClothingItem(
            name=name,
            category=category,
            original_filename=p_fn,
            processed_filename=p_fn,
            thumbnail_filename=th_fn,
            is_default=True,
        ))

    db.session.add_all(new_items)
    db.session.commit()
    logger.info(f"Created {len(new_items)} default wardrobe items.")
    return new_items


# ─────────────────────────────────────────────────────────────────────────────
# Drawing router
# ─────────────────────────────────────────────────────────────────────────────

def _draw_item(filepath, category, color, name):
    is_button_up = "button" in name.lower()
    fn_map = {
        "top":        _draw_button_up if is_button_up else _draw_tshirt,
        "bottom":     _draw_pants,
        "outerwear":  _draw_overcoat,
        "shoes":      _draw_shoes,
        "full_outfit":_draw_tshirt,
        "accessory":  _draw_tshirt,
    }
    fn_map.get(category, _draw_tshirt)(filepath, color)


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers
# All shapes drawn at 4× scale then downsampled for smooth edges.
# Output canvas = 300 × 300 px.
# ─────────────────────────────────────────────────────────────────────────────

_SZ    = 300   # output size
_SC    = 4     # super-sampling scale


def _canvas():
    W = H = _SZ * _SC
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def _save(img, filepath):
    img = img.resize((_SZ, _SZ), Image.LANCZOS)
    img.save(filepath, "PNG")


def _make_thumb(src, dst, size=(150, 150)):
    try:
        img = Image.open(src).convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)
        img.save(dst, "PNG")
    except Exception as e:
        logger.warning(f"Thumb failed for {src}: {e}")


def _is_light(hex_color):
    r, g, b, _ = _rgb(hex_color)
    return (r * 299 + g * 587 + b * 114) / 1000 > 180


def _outline(hex_color):
    """Light fabrics get a subtle grey outline so they're visible on dark backgrounds."""
    return (180, 180, 180, 200) if _is_light(hex_color) else None


def _button_color(hex_color):
    return (100, 100, 100, 255) if _is_light(hex_color) else (70, 70, 70, 255)


# ── T-Shirt ────────────────────────────────────────────────────────────────

def _draw_tshirt(filepath, color):
    img, draw = _canvas()
    s = _SC
    c = _rgb(color)

    # Shoulder band + body
    draw.rectangle([80*s, 90*s, 220*s, 120*s], fill=c)
    draw.rectangle([80*s, 108*s, 220*s, 268*s], fill=c)
    # Sleeves
    draw.polygon([(80*s,108*s),(22*s,134*s),(40*s,168*s),(80*s,148*s)], fill=c)
    draw.polygon([(220*s,108*s),(278*s,134*s),(260*s,168*s),(220*s,148*s)], fill=c)
    # Crew-neck cutout
    draw.ellipse([115*s, 80*s, 185*s, 118*s], fill=(0,0,0,0))

    oc = _outline(color)
    if oc:
        draw.ellipse([115*s, 80*s, 185*s, 118*s], outline=oc, width=2*s)

    _save(img, filepath)


# ── Button-up shirt ────────────────────────────────────────────────────────

def _draw_button_up(filepath, color):
    img, draw = _canvas()
    s = _SC
    c = _rgb(color)

    # Body
    draw.rectangle([78*s, 85*s, 222*s, 270*s], fill=c)
    # Long sleeves
    draw.polygon([(78*s,85*s),(16*s,114*s),(26*s,216*s),(78*s,182*s)], fill=c)
    draw.polygon([(222*s,85*s),(284*s,114*s),(274*s,216*s),(222*s,182*s)], fill=c)
    # Collar points
    draw.polygon([(110*s,85*s),(150*s,115*s),(132*s,44*s),(110*s,50*s)], fill=c)
    draw.polygon([(190*s,85*s),(150*s,115*s),(168*s,44*s),(190*s,50*s)], fill=c)
    # Buttons
    bc = _button_color(color)
    for y in range(128, 262, 28):
        draw.ellipse([146*s,y*s,154*s,(y+8)*s], fill=bc)

    _save(img, filepath)


# ── Pants ──────────────────────────────────────────────────────────────────

def _draw_pants(filepath, color):
    img, draw = _canvas()
    s = _SC
    c = _rgb(color)

    # Waistband
    draw.rectangle([68*s, 42*s, 232*s, 80*s], fill=c)
    # Left leg (slightly tapered)
    draw.polygon([(68*s,76*s),(62*s,278*s),(148*s,278*s),(152*s,76*s)], fill=c)
    # Right leg
    draw.polygon([(148*s,76*s),(152*s,278*s),(238*s,278*s),(232*s,76*s)], fill=c)
    # Tiny crotch gap
    draw.rectangle([149*s,80*s,151*s,168*s], fill=(0,0,0,0))

    _save(img, filepath)


# ── Overcoat ───────────────────────────────────────────────────────────────

def _draw_overcoat(filepath, color):
    img, draw = _canvas()
    s = _SC
    c = _rgb(color)

    # Long body
    draw.rectangle([72*s, 72*s, 228*s, 280*s], fill=c)
    # Long sleeves
    draw.polygon([(72*s,72*s),(12*s,108*s),(20*s,226*s),(72*s,192*s)], fill=c)
    draw.polygon([(228*s,72*s),(288*s,108*s),(280*s,226*s),(228*s,192*s)], fill=c)
    # Lapels
    draw.polygon([(108*s,72*s),(150*s,122*s),(128*s,38*s),(108*s,42*s)], fill=c)
    draw.polygon([(192*s,72*s),(150*s,122*s),(172*s,38*s),(192*s,42*s)], fill=c)
    # Buttons
    bc = _button_color(color)
    for y in range(138, 272, 36):
        draw.ellipse([146*s,y*s,154*s,(y+8)*s], fill=bc)

    _save(img, filepath)


# ── Shoes ──────────────────────────────────────────────────────────────────

def _draw_shoes(filepath, color):
    img, draw = _canvas()
    s = _SC
    c = _rgb(color)

    # Sole accent colour (slightly darker than fill)
    r, g, b, _ = _rgb(color)
    sole = (max(0,r-45), max(0,g-45), max(0,b-45), 255)

    def _shoe(ox):
        """Draw a single shoe offset by ox pixels."""
        draw.ellipse([(ox+8)*s,  195*s, (ox+128)*s, 230*s], fill=c)   # sole
        draw.ellipse([(ox+2)*s,  178*s, (ox+80)*s,  228*s], fill=c)   # toe
        draw.polygon([
            ((ox+8)*s,  210*s), ((ox+4)*s,  155*s), ((ox+52)*s, 118*s),
            ((ox+108)*s,128*s), ((ox+132)*s,158*s), ((ox+132)*s,210*s)
        ], fill=c)
        draw.ellipse([(ox+40)*s, 108*s, (ox+122)*s, 158*s], fill=c)   # ankle
        draw.arc([(ox+8)*s, 196*s, (ox+128)*s, 232*s], 0, 180, fill=sole, width=3*s)

    _shoe(0)    # left shoe
    _shoe(148)  # right shoe (shifted right)

    _save(img, filepath)
