"""
Database models.

To add a new table: create a new class here inheriting db.Model,
then restart the app — db.create_all() will pick it up automatically.
"""

import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class ClothingItem(db.Model):
    __tablename__ = "clothing_items"

    # ── Extend this list to add new clothing categories ───────────────────────
    CATEGORIES = ["top", "bottom", "full_outfit", "outerwear", "shoes", "accessory"]

    id                = db.Column(db.Integer, primary_key=True)
    name              = db.Column(db.String(100), nullable=False)
    category          = db.Column(db.String(50),  nullable=False)
    original_filename = db.Column(db.String(255),  nullable=False)
    processed_filename= db.Column(db.String(255))   # PNG after background removal
    thumbnail_filename= db.Column(db.String(255))   # Smaller version for the grid
    is_default        = db.Column(db.Boolean, default=False)  # True = starter item
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        from flask import url_for
        base = "uploads/clothing_processed/"
        return {
            "id":            self.id,
            "name":          self.name,
            "category":      self.category,
            "is_default":    self.is_default,
            "thumbnail_url": url_for("static", filename=base + self.thumbnail_filename)
                             if self.thumbnail_filename else None,
            "processed_url": url_for("static", filename=base + self.processed_filename)
                             if self.processed_filename else None,
            "created_at":    self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<ClothingItem {self.name}>"


class PersonPhoto(db.Model):
    __tablename__ = "person_photos"

    id                 = db.Column(db.Integer, primary_key=True)
    name               = db.Column(db.String(100), nullable=False, default="My Photo")
    original_filename  = db.Column(db.String(255), nullable=False)
    processed_filename = db.Column(db.String(255))
    pose_data          = db.Column(db.Text)   # JSON blob from MediaPipe
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)

    outfits = db.relationship("SavedOutfit", backref="person_photo", lazy="dynamic",
                              cascade="all, delete-orphan")

    def get_pose_data(self):
        return json.loads(self.pose_data) if self.pose_data else None

    def set_pose_data(self, data):
        self.pose_data = json.dumps(data)

    def to_dict(self):
        from flask import url_for
        return {
            "id":           self.id,
            "name":         self.name,
            "processed_url": url_for("static",
                                     filename="uploads/person_processed/" + self.processed_filename)
                             if self.processed_filename else None,
            "has_pose":     bool(self.pose_data),
            "created_at":   self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<PersonPhoto {self.name}>"


class SavedOutfit(db.Model):
    __tablename__ = "saved_outfits"

    id              = db.Column(db.Integer, primary_key=True)
    person_photo_id = db.Column(db.Integer, db.ForeignKey("person_photos.id"), nullable=True)
    name            = db.Column(db.String(100), nullable=False)
    outfit_data     = db.Column(db.Text)   # Fabric.js canvas JSON snapshot
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow,
                                onupdate=datetime.utcnow)

    def get_outfit_data(self):
        return json.loads(self.outfit_data) if self.outfit_data else None

    def set_outfit_data(self, data):
        self.outfit_data = json.dumps(data)

    def to_dict(self):
        return {
            "id":              self.id,
            "name":            self.name,
            "person_photo_id": self.person_photo_id,
            "outfit_data":     self.get_outfit_data(),
            "created_at":      self.created_at.isoformat(),
            "updated_at":      self.updated_at.isoformat(),
        }

    def __repr__(self):
        return f"<SavedOutfit {self.name}>"
