"""
DressRoom — local single-user virtual try-on app.
No login required. All data stays on your computer.
"""

import os
import logging

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file

from models import db, ClothingItem, PersonPhoto, SavedOutfit
from utils.image_processing import (
    allowed_file,
    process_clothing_upload,
    process_person_upload,
    delete_file,
)
from utils.pose_detection import detect_pose, calculate_clothing_position

BASEDIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config.update(
    SECRET_KEY="dressroom-local-key",
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(BASEDIR, 'dressroom.db')}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=os.path.join(BASEDIR, "static", "uploads"),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    ALLOWED_EXTENSIONS={"png", "jpg", "jpeg", "webp"},
)

db.init_app(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# First-run setup
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_upload_dirs():
    for sub in ["clothing", "clothing_processed", "person",
                "person_processed", "tryon_results"]:
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], sub), exist_ok=True)


with app.app_context():
    _ensure_upload_dirs()
    db.create_all()


# ─────────────────────────────────────────────────────────────────────────────
# Page routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("wardrobe"))


@app.route("/wardrobe")
def wardrobe():
    clothing_items = ClothingItem.query.order_by(
        ClothingItem.category, ClothingItem.name).all()
    person_photos  = PersonPhoto.query.order_by(
        PersonPhoto.created_at.desc()).all()
    return render_template("wardrobe.html",
                           clothing_items=clothing_items,
                           person_photos=person_photos,
                           categories=ClothingItem.CATEGORIES)


@app.route("/dressing-room")
def dressing_room_select():
    person_photos = PersonPhoto.query.order_by(PersonPhoto.created_at.desc()).all()
    if not person_photos:
        return redirect(url_for("wardrobe") + "?hint=photo")
    return render_template("dressing_room_select.html", person_photos=person_photos)


@app.route("/dressing-room/<int:person_id>")
def dressing_room(person_id):
    person_photo   = db.get_or_404(PersonPhoto, person_id)
    clothing_items = ClothingItem.query.order_by(
        ClothingItem.category, ClothingItem.name).all()
    saved_outfits  = (SavedOutfit.query
                      .filter_by(person_photo_id=person_id)
                      .order_by(SavedOutfit.updated_at.desc())
                      .all())
    return render_template("dressing_room.html",
                           person_photo=person_photo,
                           clothing_items=clothing_items,
                           saved_outfits=saved_outfits)


# ─────────────────────────────────────────────────────────────────────────────
# Clothing upload & delete
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/upload-clothing", methods=["POST"])
def upload_clothing():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided."}), 400

    file     = request.files["file"]
    name     = (request.form.get("name") or file.filename or "Unnamed").strip()
    category = request.form.get("category", "top")

    if not file.filename or not allowed_file(file.filename,
                                              app.config["ALLOWED_EXTENSIONS"]):
        return jsonify({"success": False,
                        "error": "Only JPG, PNG, or WebP files are allowed."}), 400
    if category not in ClothingItem.CATEGORIES:
        return jsonify({"success": False, "error": "Invalid category."}), 400

    try:
        result = process_clothing_upload(file, app.config["UPLOAD_FOLDER"])
        item   = ClothingItem(
            name=name, category=category,
            original_filename=result["original_filename"],
            processed_filename=result["processed_filename"],
            thumbnail_filename=result["thumbnail_filename"],
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({"success": True, "item": item.to_dict()})
    except Exception as e:
        logger.error(f"Clothing upload error: {e}")
        db.session.rollback()
        return jsonify({"success": False,
                        "error": "Upload failed. Please try again."}), 500


@app.route("/delete-clothing/<int:item_id>", methods=["DELETE"])
def delete_clothing(item_id):
    item = db.get_or_404(ClothingItem, item_id)
    base = app.config["UPLOAD_FOLDER"]
    delete_file(base, "clothing",           item.original_filename)
    delete_file(base, "clothing_processed", item.processed_filename)
    delete_file(base, "clothing_processed", item.thumbnail_filename)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
# Person photo upload & delete
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/upload-person", methods=["POST"])
def upload_person():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided."}), 400

    file = request.files["file"]
    name = (request.form.get("name") or "My Photo").strip()

    if not file.filename or not allowed_file(file.filename,
                                              app.config["ALLOWED_EXTENSIONS"]):
        return jsonify({"success": False,
                        "error": "Only JPG, PNG, or WebP files are allowed."}), 400

    try:
        result = process_person_upload(file, app.config["UPLOAD_FOLDER"])
        photo  = PersonPhoto(
            name=name,
            original_filename=result["original_filename"],
            processed_filename=result["processed_filename"],
        )

        # detect_pose() now always returns something useful:
        # MediaPipe → silhouette analysis → None (only if image unreadable)
        pose_data = detect_pose(result["processed_path"])
        if pose_data:
            photo.set_pose_data(pose_data)
            logger.info(f"Pose detected via: {pose_data.get('source', 'unknown')}")
        else:
            logger.warning("No pose data could be computed for this photo.")

        db.session.add(photo)
        db.session.commit()
        return jsonify({"success": True, "photo": photo.to_dict()})

    except Exception as e:
        logger.error(f"Person upload error: {e}")
        db.session.rollback()
        return jsonify({"success": False,
                        "error": "Upload failed. Please try again."}), 500


@app.route("/delete-person/<int:photo_id>", methods=["DELETE"])
def delete_person(photo_id):
    photo = db.get_or_404(PersonPhoto, photo_id)
    base  = app.config["UPLOAD_FOLDER"]
    delete_file(base, "person",           photo.original_filename)
    delete_file(base, "person_processed", photo.processed_filename)
    db.session.delete(photo)
    db.session.commit()
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
# Try-on layout  (positions for the Fabric.js canvas — no image compositing)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/try-on-layout", methods=["POST"])
def api_try_on_layout():
    """
    Calculate initial clothing positions and return them as JSON.
    The client places each item as a moveable Fabric.js object.

    If no pose data is stored for the person photo, we detect it on the fly
    (using silhouette analysis) and save it so future requests are instant.
    """
    data            = request.get_json(silent=True) or {}
    person_photo_id = data.get("person_photo_id")
    clothing_ids    = data.get("clothing_ids", [])

    if not person_photo_id or not clothing_ids:
        return jsonify({"success": False,
                        "error": "Missing person_photo_id or clothing_ids."}), 400

    person_photo = db.get_or_404(PersonPhoto, person_photo_id)
    if not person_photo.processed_filename:
        return jsonify({"success": False,
                        "error": "Person photo not yet processed."}), 400

    upload_folder = app.config["UPLOAD_FOLDER"]
    person_path   = os.path.join(upload_folder, "person_processed",
                                 person_photo.processed_filename)

    # ── Ensure we have pose data ──────────────────────────────────────────────
    pose_data = person_photo.get_pose_data()

    if not pose_data:
        logger.info(
            f"No stored pose data for photo {person_photo_id} — "
            "detecting now from silhouette."
        )
        pose_data = detect_pose(person_path)
        if pose_data:
            person_photo.set_pose_data(pose_data)
            db.session.commit()
            logger.info(
                f"Pose computed and saved for photo {person_photo_id} "
                f"(source: {pose_data.get('source', '?')})"
            )
        else:
            logger.warning(
                f"Could not compute pose for photo {person_photo_id} — "
                "using default positions."
            )

    # ── Read person image dimensions ──────────────────────────────────────────
    try:
        import cv2
        _img = cv2.imread(person_path)
        if _img is None:
            raise ValueError("cv2.imread returned None")
        ph, pw = _img.shape[:2]
    except Exception as e:
        logger.error(f"Could not read person image dimensions: {e}")
        return jsonify({"success": False,
                        "error": "Could not read person image."}), 500

    # ── Calculate position for each clothing item ─────────────────────────────
    from utils.vton import _target_region, _crop_to_content, _load_bgra, _CATEGORY_ORDER

    items_raw = []
    for cid in clothing_ids:
        item = db.session.get(ClothingItem, cid)
        if item and item.processed_filename:
            items_raw.append(item)
    items_raw.sort(key=lambda x: _CATEGORY_ORDER.get(x.category, 99))

    result_items = []
    for item in items_raw:
        c_path = os.path.join(upload_folder, "clothing_processed",
                              item.processed_filename)
        c_img  = _load_bgra(c_path)
        if c_img is None:
            logger.warning(f"Could not load clothing image: {c_path}")
            continue

        # Crop to actual garment pixels — removes empty transparent padding
        # so scaling is based on the real garment shape, not the whole canvas
        cropped = _crop_to_content(c_img)
        if cropped is None:
            logger.warning(f"Clothing appears fully transparent: {c_path}")
            continue

        ch_img, cw_img = cropped.shape[:2]

        # Get the region in person-image pixel coordinates
        region = _target_region(pose_data, item.category, pw, ph)
        tw, th = region["w"], region["h"]

        # Scale clothing to fill the target region, preserving aspect ratio
        scale = th / ch_img
        nw    = int(cw_img * scale)
        nh    = int(ch_img * scale)
        if nw > tw:
            scale = tw / cw_img
            nw    = int(cw_img * scale)
            nh    = int(ch_img * scale)

        nw = max(nw, 10)
        nh = max(nh, 10)

        # top-left corner of the clothing in person-image coordinates
        x = int(region["cx"] - nw / 2)
        y = int(region["cy"] - nh / 2)

        result_items.append({
            "id":       item.id,
            "name":     item.name,
            "category": item.category,
            "url":      url_for("static",
                                filename=f"uploads/clothing_processed/"
                                         f"{item.processed_filename}"),
            "x":      x,
            "y":      y,
            "width":  nw,
            "height": nh,
        })

    person_url = url_for(
        "static",
        filename=f"uploads/person_processed/{person_photo.processed_filename}"
    )

    return jsonify({
        "success":       True,
        "person_url":    person_url,
        "person_width":  pw,
        "person_height": ph,
        "pose_source":   pose_data.get("source", "none") if pose_data else "none",
        "items":         result_items,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/download-result")
def api_download_result():
    rel       = request.args.get("path", "")
    safe_base = os.path.join(BASEDIR, "static", "uploads", "tryon_results")
    abs_path  = os.path.normpath(os.path.join(BASEDIR, "static", rel.lstrip("/")))
    if not abs_path.startswith(safe_base):
        return "Forbidden", 403
    if not os.path.isfile(abs_path):
        return "Not found", 404
    return send_file(abs_path, as_attachment=True,
                     download_name="dressroom_result.png")


# ─────────────────────────────────────────────────────────────────────────────
# Outfits
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/outfits", methods=["GET"])
def api_list_outfits():
    person_id = request.args.get("person_photo_id", type=int)
    q         = SavedOutfit.query
    if person_id:
        q = q.filter_by(person_photo_id=person_id)
    return jsonify([o.to_dict()
                    for o in q.order_by(SavedOutfit.updated_at.desc()).all()])


@app.route("/api/outfits/<int:outfit_id>", methods=["GET"])
def api_get_outfit(outfit_id):
    return jsonify(db.get_or_404(SavedOutfit, outfit_id).to_dict())


@app.route("/api/outfits", methods=["POST"])
def api_save_outfit():
    data            = request.get_json(silent=True) or {}
    outfit_id       = data.get("id")
    name            = (data.get("name") or "My Outfit").strip()
    person_photo_id = data.get("person_photo_id")
    outfit_data     = data.get("outfit_data", {})

    if outfit_id:
        outfit = db.get_or_404(SavedOutfit, outfit_id)
        outfit.name = name
        outfit.set_outfit_data(outfit_data)
    else:
        outfit = SavedOutfit(person_photo_id=person_photo_id, name=name)
        outfit.set_outfit_data(outfit_data)
        db.session.add(outfit)

    db.session.commit()
    return jsonify(outfit.to_dict())


@app.route("/api/outfits/<int:outfit_id>", methods=["DELETE"])
def api_delete_outfit(outfit_id):
    outfit = db.get_or_404(SavedOutfit, outfit_id)
    db.session.delete(outfit)
    db.session.commit()
    return jsonify({"success": True})