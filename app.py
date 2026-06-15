"""
DressRoom — local single-user virtual try-on app.
No login required. All data stays on your computer.

To add new features:
  - New page route  → add a @app.route below the "Page routes" section
  - New API endpoint → add a @app.route below the "API routes" section
  - New DB table    → add a model in models.py and re-run (db.create_all handles it)
"""

import os
import logging

from flask import Flask, render_template, request, jsonify, redirect, url_for

from models import db, ClothingItem, PersonPhoto, SavedOutfit
from utils.image_processing import (
    allowed_file,
    process_clothing_upload,
    process_person_upload,
    delete_file,
)
from utils.pose_detection import detect_pose, calculate_clothing_position

# ─────────────────────────────────────────────────────────────────────────────
# App configuration
# ─────────────────────────────────────────────────────────────────────────────

BASEDIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config.update(
    SECRET_KEY="dressroom-local-key",          # Only used for flash messages
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(BASEDIR, 'dressroom.db')}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=os.path.join(BASEDIR, "static", "uploads"),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,       # 16 MB file limit
    ALLOWED_EXTENSIONS={"png", "jpg", "jpeg", "webp"},
)

db.init_app(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# First-run setup  (runs once when the app starts)
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_upload_dirs():
    """Make sure every upload subdirectory exists."""
    for sub in ["clothing", "clothing_processed", "person", "person_processed"]:
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], sub), exist_ok=True)


def _seed_defaults_if_empty():
    """Add the starter wardrobe on very first launch."""
    if ClothingItem.query.count() == 0:
        from utils.default_wardrobe import seed_default_wardrobe
        seed_default_wardrobe(app.config["UPLOAD_FOLDER"])
        logger.info("Starter wardrobe seeded.")


with app.app_context():
    _ensure_upload_dirs()
    db.create_all()
    _seed_defaults_if_empty()


# ─────────────────────────────────────────────────────────────────────────────
# Page routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("wardrobe"))


@app.route("/wardrobe")
def wardrobe():
    clothing_items = (
        ClothingItem.query
        .order_by(ClothingItem.category, ClothingItem.name)
        .all()
    )
    person_photos = (
        PersonPhoto.query
        .order_by(PersonPhoto.created_at.desc())
        .all()
    )
    return render_template(
        "wardrobe.html",
        clothing_items=clothing_items,
        person_photos=person_photos,
        categories=ClothingItem.CATEGORIES,
    )


@app.route("/dressing-room")
def dressing_room_select():
    person_photos = PersonPhoto.query.order_by(PersonPhoto.created_at.desc()).all()
    if not person_photos:
        # No photos yet — send to wardrobe with a helpful hint
        return redirect(url_for("wardrobe") + "?hint=photo")
    return render_template("dressing_room_select.html", person_photos=person_photos)


@app.route("/dressing-room/<int:person_id>")
def dressing_room(person_id):
    person_photo = db.get_or_404(PersonPhoto, person_id)
    clothing_items = (
        ClothingItem.query
        .order_by(ClothingItem.category, ClothingItem.name)
        .all()
    )
    saved_outfits = (
        SavedOutfit.query
        .filter_by(person_photo_id=person_id)
        .order_by(SavedOutfit.updated_at.desc())
        .all()
    )
    return render_template(
        "dressing_room.html",
        person_photo=person_photo,
        clothing_items=clothing_items,
        saved_outfits=saved_outfits,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Clothing — upload & delete
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/upload-clothing", methods=["POST"])
def upload_clothing():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided."}), 400

    file = request.files["file"]
    name = (request.form.get("name") or file.filename or "Unnamed").strip()
    category = request.form.get("category", "top")

    if not file.filename or not allowed_file(file.filename, app.config["ALLOWED_EXTENSIONS"]):
        return jsonify({"success": False, "error": "Only JPG, PNG, or WebP files are allowed."}), 400

    if category not in ClothingItem.CATEGORIES:
        return jsonify({"success": False, "error": "Invalid category."}), 400

    try:
        result = process_clothing_upload(file, app.config["UPLOAD_FOLDER"])
        item = ClothingItem(
            name=name,
            category=category,
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
        return jsonify({"success": False, "error": "Upload failed. Please try again."}), 500


@app.route("/delete-clothing/<int:item_id>", methods=["DELETE"])
def delete_clothing(item_id):
    item = db.get_or_404(ClothingItem, item_id)

    base = app.config["UPLOAD_FOLDER"]
    delete_file(base, "clothing", item.original_filename)
    delete_file(base, "clothing_processed", item.processed_filename)
    delete_file(base, "clothing_processed", item.thumbnail_filename)

    db.session.delete(item)
    db.session.commit()
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
# Person photos — upload & delete
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/upload-person", methods=["POST"])
def upload_person():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided."}), 400

    file = request.files["file"]
    name = (request.form.get("name") or "My Photo").strip()

    if not file.filename or not allowed_file(file.filename, app.config["ALLOWED_EXTENSIONS"]):
        return jsonify({"success": False, "error": "Only JPG, PNG, or WebP files are allowed."}), 400

    try:
        result = process_person_upload(file, app.config["UPLOAD_FOLDER"])

        photo = PersonPhoto(
            name=name,
            original_filename=result["original_filename"],
            processed_filename=result["processed_filename"],
        )

        # Pose detection is optional — clothing placement still works without it
        pose_data = detect_pose(result["processed_path"])
        if pose_data:
            photo.set_pose_data(pose_data)

        db.session.add(photo)
        db.session.commit()
        return jsonify({"success": True, "photo": photo.to_dict()})

    except Exception as e:
        logger.error(f"Person upload error: {e}")
        db.session.rollback()
        return jsonify({"success": False, "error": "Upload failed. Please try again."}), 500


@app.route("/delete-person/<int:photo_id>", methods=["DELETE"])
def delete_person(photo_id):
    photo = db.get_or_404(PersonPhoto, photo_id)

    base = app.config["UPLOAD_FOLDER"]
    delete_file(base, "person", photo.original_filename)
    delete_file(base, "person_processed", photo.processed_filename)

    db.session.delete(photo)
    db.session.commit()
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
# API routes  (consumed by the dressing room JavaScript)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/clothing")
def api_list_clothing():
    category = request.args.get("category")
    q = ClothingItem.query
    if category:
        q = q.filter_by(category=category)
    return jsonify([i.to_dict() for i in q.order_by(ClothingItem.category, ClothingItem.name).all()])


@app.route("/api/clothing-position", methods=["POST"])
def api_clothing_position():
    """
    Given a person photo + clothing item, return the suggested canvas position.
    Body JSON: { person_photo_id, clothing_id, canvas_width, canvas_height }
    """
    data = request.get_json(silent=True) or {}

    person_photo = db.get_or_404(PersonPhoto, data.get("person_photo_id"))
    clothing_item = db.get_or_404(ClothingItem, data.get("clothing_id"))

    canvas_w = int(data.get("canvas_width", 500))
    canvas_h = int(data.get("canvas_height", 700))

    position = calculate_clothing_position(
        pose_data=person_photo.get_pose_data(),
        clothing_category=clothing_item.category,
        canvas_width=canvas_w,
        canvas_height=canvas_h,
    )
    return jsonify(position)


@app.route("/api/outfits", methods=["GET"])
def api_list_outfits():
    person_id = request.args.get("person_photo_id", type=int)
    q = SavedOutfit.query
    if person_id:
        q = q.filter_by(person_photo_id=person_id)
    return jsonify([o.to_dict() for o in q.order_by(SavedOutfit.updated_at.desc()).all()])


@app.route("/api/outfits/<int:outfit_id>", methods=["GET"])
def api_get_outfit(outfit_id):
    outfit = db.get_or_404(SavedOutfit, outfit_id)
    return jsonify(outfit.to_dict())


@app.route("/api/outfits", methods=["POST"])
def api_save_outfit():
    data = request.get_json(silent=True) or {}
    outfit_id = data.get("id")
    name = (data.get("name") or "My Outfit").strip()
    person_photo_id = data.get("person_photo_id")
    outfit_data = data.get("outfit_data", {})

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
