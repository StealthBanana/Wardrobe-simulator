"""
Pose detection using Google MediaPipe.

detect_pose(image_path) → dict or None
    Returns body landmark data. Returns None if MediaPipe is not installed
    or if no person is detected — clothing placement falls back to sensible
    defaults in that case.

calculate_clothing_position(pose_data, category, canvas_w, canvas_h) → dict
    Returns {x, y, width, height} in canvas pixels for initial placement.
"""

import logging

logger = logging.getLogger(__name__)

# MediaPipe landmark indices we use
_LANDMARKS = {
    "nose":           0,
    "left_shoulder":  11,
    "right_shoulder": 12,
    "left_hip":       23,
    "right_hip":      24,
    "left_ankle":     27,
    "right_ankle":    28,
}


# ─────────────────────────────────────────────────────────────────────────────
# Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_pose(image_path):
    """
    Run MediaPipe Pose on an image file.
    Returns a dict of derived body measurements (all in 0-1 relative coords),
    or None if detection fails for any reason.
    """
    try:
        import cv2
        import mediapipe as mp

        image = cv2.imread(image_path)
        if image is None:
            logger.warning(f"detect_pose: cannot read {image_path}")
            return None

        h, w = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        with mp.solutions.pose.Pose(
            static_image_mode=True,
            model_complexity=1,
            min_detection_confidence=0.5,
        ) as pose:
            results = pose.process(rgb)

        if not results.pose_landmarks:
            logger.info("detect_pose: no landmarks found in image.")
            return None

        lm = results.pose_landmarks.landmark

        def pt(idx):
            l = lm[idx]
            return {"x": l.x, "y": l.y, "vis": l.visibility}

        pts = {name: pt(idx) for name, idx in _LANDMARKS.items()}

        ls, rs = pts["left_shoulder"],  pts["right_shoulder"]
        lh, rh = pts["left_hip"],       pts["right_hip"]
        la, ra = pts["left_ankle"],     pts["right_ankle"]
        nose   = pts["nose"]

        sc_x = (ls["x"] + rs["x"]) / 2
        sc_y = (ls["y"] + rs["y"]) / 2
        hc_x = (lh["x"] + rh["x"]) / 2
        hc_y = (lh["y"] + rh["y"]) / 2
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
        }

    except ImportError:
        logger.warning("MediaPipe / OpenCV not installed — pose detection skipped.")
        return None
    except Exception as e:
        logger.error(f"Pose detection error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Placement calculator
# ─────────────────────────────────────────────────────────────────────────────

def calculate_clothing_position(pose_data, clothing_category, canvas_width, canvas_height):
    """
    Return a suggested {x, y, width, height} for placing a clothing item on
    the Fabric.js canvas.  x/y are the top-left corner in canvas pixels.
    Falls back to a centred default when pose_data is None.
    """
    if not pose_data:
        return _default_position(clothing_category, canvas_width, canvas_height)

    W, H = canvas_width, canvas_height

    def sx(r): return r * W
    def sy(r): return r * H

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
        w = max(sw * 1.8, 100);  h = max(tor_h * 1.4, 80)
        x = sc_x - w / 2;        y = sc_y - h * 0.1

    elif cat == "shoes":
        w = max(sw * 0.7, 50);   h = max(bdy_h * 0.1, 30)
        x = hc_x - w / 2;        y = ank_y - h / 2

    elif cat == "accessory":
        w = max(sw * 0.5, 40);   h = w
        x = sc_x - w / 2;        y = max(nos_y - h * 2, 0)

    else:
        return _default_position(clothing_category, canvas_width, canvas_height)

    # Keep the item inside the canvas
    x = max(0, min(x, W - w))
    y = max(0, min(y, H - h))

    return {"x": round(x), "y": round(y), "width": round(w), "height": round(h)}


def _default_position(category, W, H):
    """Fallback positions when no pose data is available."""
    presets = {
        "top":         (0.25, 0.20, 0.50, 0.35),
        "bottom":      (0.25, 0.52, 0.50, 0.40),
        "full_outfit": (0.25, 0.18, 0.50, 0.72),
        "outerwear":   (0.22, 0.18, 0.56, 0.45),
        "shoes":       (0.28, 0.82, 0.44, 0.12),
        "accessory":   (0.35, 0.02, 0.30, 0.15),
    }
    rx, ry, rw, rh = presets.get(category, (0.25, 0.25, 0.50, 0.50))
    return {"x": round(rx * W), "y": round(ry * H),
            "width": round(rw * W), "height": round(rh * H)}
