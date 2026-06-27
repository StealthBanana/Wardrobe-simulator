"""
Pose / body-landmark detection.

Two strategies, tried in order:
  1. MediaPipe  — precise ML-based landmark detection (requires mediapipe + opencv)
  2. Mask analysis — scans the person's alpha-channel silhouette row-by-row to
     locate the shoulder line, waist, hip line, and ankles from the actual
     shape of the body outline.  Works with zero extra dependencies and gives
     accurate placement even when MediaPipe is unavailable or fails.

Both strategies return a dict in the same format so the rest of the app
doesn't need to care which one ran.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def detect_pose(image_path):
    """
    Try MediaPipe first, fall back to silhouette analysis.
    Always returns a usable dict if the image is readable.
    Returns None only if the image cannot be loaded at all.
    """
    result = _detect_mediapipe(image_path)
    if result:
        logger.info("Pose detected via MediaPipe.")
        return result

    logger.info("MediaPipe unavailable or found no landmarks — using silhouette analysis.")
    result = estimate_from_mask(image_path)
    if result:
        return result

    logger.warning(f"All pose detection methods failed for {image_path}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1 — MediaPipe
# ─────────────────────────────────────────────────────────────────────────────

def _detect_mediapipe(image_path):
    """Return pose dict from MediaPipe, or None if unavailable / no landmarks."""
    try:
        import cv2
        import mediapipe as mp

        image = cv2.imread(image_path)
        if image is None:
            return None

        h, w = image.shape[:2]
        rgb  = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        with mp.solutions.pose.Pose(
            static_image_mode        = True,
            model_complexity         = 2,     # highest accuracy
            min_detection_confidence = 0.3,   # low threshold — catch more poses
        ) as pose:
            results = pose.process(rgb)

        if not results.pose_landmarks:
            return None

        lm = results.pose_landmarks.landmark

        def pt(idx):
            l = lm[idx]
            return {"x": l.x, "y": l.y, "vis": l.visibility}

        ls   = pt(11)   # left shoulder
        rs   = pt(12)   # right shoulder
        lh   = pt(23)   # left hip
        rh   = pt(24)   # right hip
        la   = pt(27)   # left ankle
        ra   = pt(28)   # right ankle
        nose = pt(0)

        # Discard if both shoulders are invisible — unreliable data
        if ls["vis"] < 0.3 and rs["vis"] < 0.3:
            logger.warning("MediaPipe: shoulder visibility too low, discarding.")
            return None

        sc_x  = (ls["x"] + rs["x"]) / 2
        sc_y  = (ls["y"] + rs["y"]) / 2
        hc_x  = (lh["x"] + rh["x"]) / 2
        hc_y  = (lh["y"] + rh["y"]) / 2
        ank_y = (la["y"] + ra["y"]) / 2

        return {
            "shoulder_center": {"x": sc_x,              "y": sc_y},
            "hip_center":      {"x": hc_x,              "y": hc_y},
            "shoulder_width":  abs(rs["x"] - ls["x"]),
            "hip_width":       abs(rh["x"] - lh["x"]),
            "torso_height":    hc_y - sc_y,
            "body_height":     ank_y - nose["y"],
            "nose_y":          nose["y"],
            "ankle_y":         ank_y,
            "source":          "mediapipe",
        }

    except ImportError:
        logger.warning("MediaPipe not installed.")
        return None
    except Exception as e:
        logger.error(f"MediaPipe error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 2 — Silhouette / mask analysis
# ─────────────────────────────────────────────────────────────────────────────

def estimate_from_mask(image_path):
    """
    Estimate body key points by analysing the person's silhouette.

    How it works
    ─────────────
    Since rembg has already removed the background, the alpha channel is a
    clean outline of the person.  We scan every row of pixels and record the
    horizontal width and centre-x of the occupied region.  Human bodies follow
    predictable width patterns from top to bottom:

      0–10 %  head       (medium, roughly circular)
     10–32 %  shoulders  (widest in upper body)
     32–50 %  torso      (narrows toward waist)
     45–65 %  hips       (widest in mid body)
     65–100%  legs       (narrowing to ankles)

    Finding the local-maximum width in each zone gives us the key landmarks
    we need for clothing placement.
    """
    try:
        import cv2

        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None

        h, w = img.shape[:2]

        # ── Build a binary content mask ───────────────────────────────────────
        THRESH = 30

        if img.ndim == 3 and img.shape[2] == 4:
            # RGBA — use the alpha channel directly
            mask = img[:, :, 3]
        elif img.ndim == 3:
            # RGB with no alpha — background may not be removed; threshold on grey
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, 15, 255, cv2.THRESH_BINARY)
        else:
            return None

        # ── Find the person's bounding box ────────────────────────────────────
        # A row counts as "occupied" if ≥2 % of its pixels are above threshold
        row_occupied = np.sum(mask > THRESH, axis=1) > w * 0.02
        col_occupied = np.sum(mask > THRESH, axis=0) > h * 0.02

        valid_rows = np.where(row_occupied)[0]
        valid_cols = np.where(col_occupied)[0]

        if len(valid_rows) < 20 or len(valid_cols) < 10:
            logger.warning("Mask analysis: not enough content in image.")
            return None

        body_top    = int(valid_rows[0])
        body_bottom = int(valid_rows[-1])
        body_height = body_bottom - body_top

        if body_height < 40:
            return None

        # ── Scan each row for width + centre ─────────────────────────────────
        profiles = []
        for row_y in range(body_top, body_bottom + 1):
            filled = np.where(mask[row_y, :] > THRESH)[0]
            if len(filled) >= 3:
                profiles.append({
                    "y":     row_y,
                    "width": int(filled[-1]) - int(filled[0]),
                    "cx":    (int(filled[0]) + int(filled[-1])) / 2.0,
                })

        if len(profiles) < 10:
            return None

        def zone(pct_start, pct_end):
            """Return profiles within a vertical zone (pct of body height)."""
            y0 = body_top + int(body_height * pct_start)
            y1 = body_top + int(body_height * pct_end)
            return [p for p in profiles if y0 <= p["y"] <= y1]

        def widest(zone_profiles):
            return max(zone_profiles, key=lambda p: p["width"]) if zone_profiles else None

        def narrowest(zone_profiles):
            return min(zone_profiles, key=lambda p: p["width"]) if zone_profiles else None

        # ── Shoulders (10–32 % of body height) ───────────────────────────────
        shoulder_row = widest(zone(0.10, 0.32))
        if shoulder_row:
            sc_x = shoulder_row["cx"] / w
            sc_y = shoulder_row["y"]  / h
            sw   = shoulder_row["width"] / w
        else:
            sc_x = 0.5
            sc_y = body_top / h + 0.18
            sw   = (valid_cols[-1] - valid_cols[0]) * 0.65 / w

        # ── Hips (45–65 % of body height) ────────────────────────────────────
        hip_row = widest(zone(0.45, 0.65))
        if hip_row:
            hc_x = hip_row["cx"] / w
            hc_y = hip_row["y"]  / h
            hw   = hip_row["width"] / w
        else:
            hc_x = sc_x
            hc_y = body_top / h + 0.55
            hw   = sw * 0.90

        # ── Waist (narrowest point between shoulder and hip, 30–50 %) ─────────
        waist_row = narrowest(zone(0.30, 0.50))
        # (Not stored in return dict currently but useful for future refinement)

        # ── Head / nose (upper 10 %) ──────────────────────────────────────────
        head_zone = zone(0.00, 0.10)
        if head_zone:
            mid_head = head_zone[len(head_zone) // 2]
            nose_y   = mid_head["y"] / h
        else:
            nose_y = body_top / h + 0.04

        # ── Ankles (bottom 5 % of silhouette, last substantial row) ──────────
        ankle_zone = [p for p in profiles
                      if p["y"] >= body_top + int(body_height * 0.85)
                      and p["width"] > 4]
        if ankle_zone:
            ankle_y = ankle_zone[-1]["y"] / h
        else:
            ankle_y = body_bottom / h

        result = {
            "shoulder_center": {"x": sc_x, "y": sc_y},
            "hip_center":      {"x": hc_x, "y": hc_y},
            "shoulder_width":  sw,
            "hip_width":       hw,
            "torso_height":    hc_y - sc_y,
            "body_height":     ankle_y - nose_y,
            "nose_y":          nose_y,
            "ankle_y":         ankle_y,
            "source":          "mask_analysis",
        }

        logger.info(
            f"Silhouette analysis: shoulders at y={sc_y:.2f}, "
            f"hips at y={hc_y:.2f}, sw={sw:.2f}, hw={hw:.2f}"
        )
        return result

    except Exception as e:
        logger.error(f"Silhouette analysis failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Placement calculator  (used by the old /api/clothing-position route)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_clothing_position(pose_data, clothing_category, canvas_width, canvas_height):
    """
    Return {x, y, width, height} in canvas pixels for initial placement.
    Falls back to centred defaults when pose_data is None.
    """
    if not pose_data:
        return _default_position(clothing_category, canvas_width, canvas_height)

    W, H = canvas_width, canvas_height
    sx   = lambda r: r * W
    sy   = lambda r: r * H

    sc_x  = sx(pose_data["shoulder_center"]["x"])
    sc_y  = sy(pose_data["shoulder_center"]["y"])
    hc_x  = sx(pose_data["hip_center"]["x"])
    hc_y  = sy(pose_data["hip_center"]["y"])
    sw    = sx(pose_data["shoulder_width"])
    hw    = sx(pose_data["hip_width"])
    tor_h = sy(pose_data["torso_height"])
    bdy_h = sy(pose_data["body_height"])
    ank_y = sy(pose_data["ankle_y"])
    nos_y = sy(pose_data["nose_y"])

    cat = clothing_category.lower()

    if cat == "top":
        w = max(sw * 1.55, 80);  h = max(tor_h * 1.2, 60)
        x = sc_x - w / 2;        y = sc_y - h * 0.12
    elif cat == "bottom":
        w = max(hw * 1.8, 80);   h = max((ank_y - hc_y) * 1.05, 80)
        x = hc_x - w / 2;        y = hc_y
    elif cat == "full_outfit":
        w = max(sw * 1.55, 100); h = max(bdy_h * 0.95, 120)
        x = sc_x - w / 2;        y = sc_y - h * 0.05
    elif cat == "outerwear":
        w = max(sw * 1.80, 100); h = max(tor_h * 1.4, 80)
        x = sc_x - w / 2;        y = sc_y - h * 0.10
    elif cat == "shoes":
        w = max(sw * 0.70, 50);  h = max(bdy_h * 0.10, 30)
        x = hc_x - w / 2;        y = ank_y - h / 2
    elif cat == "accessory":
        w = max(sw * 0.50, 40);  h = w
        x = sc_x - w / 2;        y = max(nos_y - h * 2.0, 0)
    else:
        return _default_position(clothing_category, canvas_width, canvas_height)

    x = max(0, min(x, W - w))
    y = max(0, min(y, H - h))
    return {"x": round(x), "y": round(y), "width": round(w), "height": round(h)}


def _default_position(category, W, H):
    presets = {
        "top":         (0.25, 0.20, 0.50, 0.35),
        "bottom":      (0.25, 0.52, 0.50, 0.40),
        "full_outfit": (0.25, 0.18, 0.50, 0.72),
        "outerwear":   (0.22, 0.18, 0.56, 0.45),
        "shoes":       (0.28, 0.82, 0.44, 0.12),
        "accessory":   (0.35, 0.02, 0.30, 0.15),
    }
    rx, ry, rw, rh = presets.get(category, (0.25, 0.25, 0.50, 0.50))
    return {
        "x": round(rx * W), "y": round(ry * H),
        "width": round(rw * W), "height": round(rh * H),
    }