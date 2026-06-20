"""
Virtual Try-On engine.

What this does (and doesn't do):
  ✅  Perspective-warps clothing to match body proportions from pose data
  ✅  Feathers clothing edges so it blends rather than looking pasted on
  ✅  Brightness-matches clothing to the scene's ambient light
  ✅  Layers multiple items in the right order (outerwear over top, etc.)
  ✅  Runs entirely locally — no GPU, no internet, no cost

  ❌  Does not simulate fabric wrinkles / folds  (needs diffusion model)
  ❌  Does not remove original clothing from photo (needs inpainting model)
  ❌  Does not do photorealistic skin-edge blending (needs DensePose)

To get closer to photorealistic results you would need OOTDiffusion or
IDM-VTON (large NVIDIA GPU required) or a paid API such as Fashn.ai.
"""

import os
import uuid
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Apply clothing in this order so layering looks correct
_CATEGORY_ORDER = {
    'full_outfit': 0,
    'bottom':      1,
    'top':         2,
    'outerwear':   3,
    'shoes':       4,
    'accessory':   5,
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def process_try_on(person_path, clothing_items, pose_data, output_dir):
    """
    Composite one or more clothing items onto a person photo.

    Args:
        person_path:     Absolute path to the person's processed PNG.
        clothing_items:  List of (clothing_abs_path, category_str) tuples.
        pose_data:       Dict returned by detect_pose(), or None.
        output_dir:      Directory where the result PNG will be saved.

    Returns:
        Absolute path to the composited result PNG.

    Raises:
        ValueError if the person image can't be loaded.
    """
    os.makedirs(output_dir, exist_ok=True)

    base = _load_bgra(person_path)
    if base is None:
        raise ValueError(f"Could not load person image: {person_path}")

    ph, pw = base.shape[:2]

    # Sort items so they layer in the natural order
    clothing_items = sorted(clothing_items,
                            key=lambda x: _CATEGORY_ORDER.get(x[1], 99))

    for clothing_path, category in clothing_items:
        clothing = _load_bgra(clothing_path)
        if clothing is None:
            logger.warning(f"Skipping unreadable clothing file: {clothing_path}")
            continue
        try:
            base = _apply_one(base, clothing, category, pose_data, pw, ph)
        except Exception as exc:
            logger.error(f"Failed to apply {category} ({clothing_path}): {exc}")

    out_path = os.path.join(output_dir, f"tryon_{uuid.uuid4().hex[:12]}.png")
    cv2.imwrite(out_path, base)
    logger.info(f"Try-on result → {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline for one clothing item
# ─────────────────────────────────────────────────────────────────────────────

def _apply_one(base_bgra, clothing_bgra, category, pose_data, pw, ph):
    dst  = _target_quad(pose_data, category, pw, ph)
    warp = _perspective_warp(clothing_bgra, dst, pw, ph)
    warp = _feather_edges(warp, blur_px=20)
    warp = _match_brightness(warp, base_bgra, dst)
    return _composite(base_bgra, warp)


# ─────────────────────────────────────────────────────────────────────────────
# Target quad — where the clothing goes in the output image
# ─────────────────────────────────────────────────────────────────────────────

def _target_quad(pose_data, category, pw, ph):
    if not pose_data:
        return _default_quad(category, pw, ph)

    d  = pose_data
    sx = lambda r: r * pw
    sy = lambda r: r * ph

    sc_x  = sx(d['shoulder_center']['x'])
    sc_y  = sy(d['shoulder_center']['y'])
    hc_x  = sx(d['hip_center']['x'])
    hc_y  = sy(d['hip_center']['y'])
    sw    = sx(d['shoulder_width'])
    hw    = sx(d['hip_width'])
    ank_y = sy(d['ankle_y'])
    nos_y = sy(d['nose_y'])

    Ms = 0.22
    Mh = 0.18

    cat = category.lower()

    if cat == 'top':
        tl = (sc_x - sw/2 - sw*Ms,   sc_y - sw*0.10)
        tr = (sc_x + sw/2 + sw*Ms,   sc_y - sw*0.10)
        bl = (hc_x - hw/2 - hw*Mh,   hc_y + sw*0.08)
        br = (hc_x + hw/2 + hw*Mh,   hc_y + sw*0.08)

    elif cat == 'bottom':
        tl = (hc_x - hw/2 - hw*Mh,   hc_y - hw*0.06)
        tr = (hc_x + hw/2 + hw*Mh,   hc_y - hw*0.06)
        bl = (hc_x - hw/2 - hw*0.05, ank_y + hw*0.12)
        br = (hc_x + hw/2 + hw*0.05, ank_y + hw*0.12)

    elif cat == 'outerwear':
        tl = (sc_x - sw/2 - sw*0.38,  sc_y - sw*0.12)
        tr = (sc_x + sw/2 + sw*0.38,  sc_y - sw*0.12)
        bl = (hc_x - hw/2 - hw*0.28,  hc_y + sw*0.30)
        br = (hc_x + hw/2 + hw*0.28,  hc_y + sw*0.30)

    elif cat == 'full_outfit':
        tl = (sc_x - sw/2 - sw*Ms,   sc_y - sw*0.10)
        tr = (sc_x + sw/2 + sw*Ms,   sc_y - sw*0.10)
        bl = (hc_x - hw/2 - hw*0.06, ank_y + hw*0.10)
        br = (hc_x + hw/2 + hw*0.06, ank_y + hw*0.10)

    elif cat == 'shoes':
        fw = sw * 0.55
        tl = (hc_x - fw,      ank_y - fw*0.25)
        tr = (hc_x + fw,      ank_y - fw*0.25)
        bl = (hc_x - fw*0.85, ank_y + fw*0.65)
        br = (hc_x + fw*0.85, ank_y + fw*0.65)

    elif cat == 'accessory':
        aw = sw * 0.42
        tl = (sc_x - aw, nos_y - aw*1.6)
        tr = (sc_x + aw, nos_y - aw*1.6)
        bl = (sc_x - aw, nos_y - aw*0.05)
        br = (sc_x + aw, nos_y - aw*0.05)

    else:
        return _default_quad(category, pw, ph)

    return np.float32([tl, tr, bl, br])


def _default_quad(category, pw, ph):
    presets = {
        'top':         (.12, .18, .88, .18, .12, .56, .88, .56),
        'bottom':      (.14, .50, .86, .50, .14, .97, .86, .97),
        'full_outfit': (.12, .18, .88, .18, .12, .97, .88, .97),
        'outerwear':   (.08, .15, .92, .15, .08, .62, .92, .62),
        'shoes':       (.22, .82, .78, .82, .22, .98, .78, .98),
        'accessory':   (.35, .02, .65, .02, .35, .18, .65, .18),
    }
    v = presets.get(category, (.18, .18, .82, .18, .18, .82, .82, .82))
    return np.float32([
        (v[0]*pw, v[1]*ph), (v[2]*pw, v[3]*ph),
        (v[4]*pw, v[5]*ph), (v[6]*pw, v[7]*ph),
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Perspective warp
# ─────────────────────────────────────────────────────────────────────────────

def _perspective_warp(clothing_bgra, dst_pts, pw, ph):
    ch, cw = clothing_bgra.shape[:2]
    src_pts = np.float32([
        (0,  0),
        (cw, 0),
        (0,  ch),
        (cw, ch),
    ])
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    return cv2.warpPerspective(
        clothing_bgra, M, (pw, ph),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Edge feathering
# ─────────────────────────────────────────────────────────────────────────────

def _feather_edges(img_bgra, blur_px=20):
    if img_bgra.shape[2] < 4:
        return img_bgra

    alpha  = img_bgra[:, :, 3].astype(np.float32)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    alpha  = cv2.erode(alpha, kernel, iterations=1)
    k      = blur_px * 2 + 1
    alpha  = cv2.GaussianBlur(alpha, (k, k), blur_px * 0.45)

    result = img_bgra.copy()
    result[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Brightness matching
# ─────────────────────────────────────────────────────────────────────────────

def _match_brightness(clothing_bgra, base_bgra, dst_pts):
    try:
        ph, pw      = base_bgra.shape[:2]
        poly        = dst_pts.reshape((-1, 1, 2)).astype(np.int32)
        region_mask = np.zeros((ph, pw), dtype=np.uint8)
        cv2.fillConvexPoly(region_mask, poly, 255)

        base_gray   = cv2.cvtColor(base_bgra[:, :, :3], cv2.COLOR_BGR2GRAY)
        base_mean   = cv2.mean(base_gray, mask=region_mask)[0]

        c_alpha     = clothing_bgra[:, :, 3]
        opaque_mask = (c_alpha > 30).astype(np.uint8) * 255
        c_gray      = cv2.cvtColor(clothing_bgra[:, :, :3], cv2.COLOR_BGR2GRAY)
        c_mean      = cv2.mean(c_gray, mask=opaque_mask)[0]

        if c_mean < 1:
            return clothing_bgra

        factor = float(np.clip(float(base_mean) / float(c_mean), 0.75, 1.25))

        result = clothing_bgra.astype(np.float32)
        result[:, :, :3] *= factor
        result = np.clip(result, 0, 255).astype(np.uint8)
        result[:, :, 3]  = clothing_bgra[:, :, 3]
        return result

    except Exception as exc:
        logger.warning(f"Brightness match skipped: {exc}")
        return clothing_bgra


# ─────────────────────────────────────────────────────────────────────────────
# Alpha compositing
# ─────────────────────────────────────────────────────────────────────────────

def _composite(base_bgra, overlay_bgra):
    base    = base_bgra.astype(np.float32)    / 255.0
    overlay = overlay_bgra.astype(np.float32) / 255.0

    a_o   = overlay[:, :, 3:4]
    a_b   = base[:, :, 3:4]
    a_out = a_o + a_b * (1.0 - a_o)

    safe_a  = np.where(a_out > 0, a_out, 1.0)
    rgb_out = (overlay[:, :, :3] * a_o
               + base[:, :, :3] * a_b * (1.0 - a_o)) / safe_a

    out = np.empty_like(base)
    out[:, :, :3] = rgb_out
    out[:, :, 3]  = a_out[:, :, 0]

    return np.clip(out * 255, 0, 255).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# Image loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_bgra(path):
    try:
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif img.shape[2] == 3:
            alpha = np.full(img.shape[:2], 255, dtype=np.uint8)
            img   = np.dstack([img, alpha])
        return img
    except Exception as exc:
        logger.error(f"Image load error ({path}): {exc}")
        return None