"""
Image processing utilities.

Key functions:
  process_clothing_upload(file_obj, upload_folder) -> dict
  process_person_upload(file_obj, upload_folder)   -> dict
  delete_file(base, subdir, filename)

Background removal uses rembg (requires onnxruntime).
On first use, rembg downloads its AI model (~170 MB) — this is normal.
If rembg is not installed, uploads are saved as-is (no background removal).
"""

import os
import uuid
import shutil
import logging
import importlib.util

from PIL import Image

logger = logging.getLogger(__name__)

# Cached after the first check so we don't re-probe on every single upload.
_rembg_checked = False
_rembg_usable  = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def allowed_file(filename, allowed_extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def delete_file(base, subdir, filename):
    """Silently delete a file if it exists."""
    if not filename:
        return
    path = os.path.join(base, subdir, filename)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning(f"Could not delete {path}: {e}")


def _save_raw(file_obj, directory):
    """Save an uploaded FileStorage to disk with a UUID filename."""
    ext = os.path.splitext(file_obj.filename)[1].lower() if "." in file_obj.filename else ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(directory, filename)
    file_obj.save(path)
    return path, filename


# ─────────────────────────────────────────────────────────────────────────────
# Background removal
# ─────────────────────────────────────────────────────────────────────────────

def _rembg_is_usable():
    """
    Check once whether rembg can actually run (it needs the onnxruntime
    package installed separately). Cached so we only probe once per process.
    """
    global _rembg_checked, _rembg_usable
    if _rembg_checked:
        return _rembg_usable

    _rembg_checked = True
    has_rembg       = importlib.util.find_spec("rembg") is not None
    has_onnxruntime = importlib.util.find_spec("onnxruntime") is not None

    if not has_rembg:
        logger.warning("rembg not installed — background removal disabled. "
                        "Run: pip install rembg")
        _rembg_usable = False
    elif not has_onnxruntime:
        logger.warning("rembg is installed but onnxruntime is missing — background "
                        "removal disabled. Run: pip install \"rembg[cpu]\"")
        _rembg_usable = False
    else:
        _rembg_usable = True

    return _rembg_usable


def remove_background(image_path):
    """
    Remove the background from image_path and return the path to a new PNG.
    Falls back to the original file if rembg/onnxruntime are unavailable or
    if anything goes wrong — uploads should never fail just because background
    removal isn't working.
    """
    if not _rembg_is_usable():
        return image_path

    try:
        from rembg import remove
        with open(image_path, "rb") as f:
            result = remove(f.read())
        out_path = os.path.splitext(image_path)[0] + "_nobg.png"
        with open(out_path, "wb") as f:
            f.write(result)
        logger.info(f"Background removed → {os.path.basename(out_path)}")
        return out_path
    except Exception as e:
        # Normal Python errors — log and fall back to original image.
        logger.error(f"Background removal failed: {e}")
        return image_path
    except BaseException as e:
        # Some backends (e.g. rembg without onnxruntime) raise SystemExit or
        # other non-Exception errors instead of a normal exception. Catching
        # this prevents the whole request from dying silently — the upload
        # still succeeds, just without background removal.
        logger.error(f"Background removal crashed unexpectedly ({type(e).__name__}): {e}")
        return image_path


# ─────────────────────────────────────────────────────────────────────────────
# Thumbnail
# ─────────────────────────────────────────────────────────────────────────────

def create_thumbnail(image_path, size=(300, 300)):
    """Return path to a thumbnail PNG next to the source file, or None on error."""
    try:
        img = Image.open(image_path).convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)
        thumb_path = os.path.splitext(image_path)[0] + "_thumb.png"
        img.save(thumb_path, "PNG")
        return thumb_path
    except Exception as e:
        logger.error(f"Thumbnail creation failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Full upload pipelines
# ─────────────────────────────────────────────────────────────────────────────

def process_clothing_upload(file_obj, upload_folder):
    """
    Save original → remove background → create thumbnail.
    Returns: { original_filename, processed_filename, thumbnail_filename }
    """
    orig_dir = os.path.join(upload_folder, "clothing")
    proc_dir = os.path.join(upload_folder, "clothing_processed")

    # 1. Save original
    orig_path, orig_fn = _save_raw(file_obj, orig_dir)

    # 2. Remove background
    nobg_path = remove_background(orig_path)
    proc_fn = f"{uuid.uuid4().hex}_proc.png"
    final_proc = os.path.join(proc_dir, proc_fn)
    if nobg_path != orig_path:
        shutil.move(nobg_path, final_proc)
    else:
        shutil.copy(orig_path, final_proc)

    # 3. Thumbnail
    thumb_path = create_thumbnail(final_proc)
    thumb_fn = None
    if thumb_path:
        thumb_fn = f"{uuid.uuid4().hex}_thumb.png"
        shutil.move(thumb_path, os.path.join(proc_dir, thumb_fn))

    return {
        "original_filename":  orig_fn,
        "processed_filename": proc_fn,
        "thumbnail_filename": thumb_fn,
    }


def process_person_upload(file_obj, upload_folder):
    """
    Save original → remove background.
    Returns: { original_filename, processed_filename, processed_path }
    processed_path is the absolute path (needed for pose detection).
    """
    orig_dir = os.path.join(upload_folder, "person")
    proc_dir = os.path.join(upload_folder, "person_processed")

    # 1. Save original
    orig_path, orig_fn = _save_raw(file_obj, orig_dir)

    # 2. Remove background
    nobg_path = remove_background(orig_path)
    proc_fn = f"{uuid.uuid4().hex}_person.png"
    final_proc = os.path.join(proc_dir, proc_fn)
    if nobg_path != orig_path:
        shutil.move(nobg_path, final_proc)
    else:
        shutil.copy(orig_path, final_proc)

    return {
        "original_filename":  orig_fn,
        "processed_filename": proc_fn,
        "processed_path":     final_proc,   # absolute — used by detect_pose()
    }