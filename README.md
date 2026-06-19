# DressRoom 👗

A local virtual dressing room. Upload photos of clothes, upload a photo of
yourself, then drag clothes onto your photo to see how outfits look — all
without leaving your computer.

---

## What it does

- **Wardrobe** — upload clothing photos; the app automatically removes the
  background so each item floats cleanly.
- **My Photos** — upload a full-body photo of yourself; background is removed
  and the app optionally detects your body pose for smarter clothing placement.
- **Dressing Room** — drag clothes from your wardrobe onto your photo, resize
  and reposition them, layer items, then save outfits to come back to later.
- **Starter wardrobe** — 10 default items (black & white basics) are added
  automatically on first launch.

---

## Setup

### 1. Requirements
- Python 3.9 or newer  
  Download: https://www.python.org/downloads/

### 2. Install dependencies

Open a terminal in this folder and run:

```bash
pip install -r requirements.txt
```

> ⚠️ **First-time note:** `rembg` (the background-removal library) will
> automatically download an AI model (~170 MB) the first time you upload an
> image. This is a one-time download.

### 3. Run

```bash
python run.py
```

Then open your browser and go to:

```
http://localhost:5000
```

The app is running entirely on your computer. Nothing is sent to the internet.

---

## Notes

### Background removal
Powered by [rembg](https://github.com/danielgatis/rembg). Works best on images
with a plain or simple background. Processing takes ~5–20 seconds depending on
your hardware (faster on subsequent uploads once the model is cached).

### Pose detection (optional)
If [MediaPipe](https://google.github.io/mediapipe/) and OpenCV are installed,
the app detects your body's key points (shoulders, hips, ankles) when you
upload a photo and uses them to auto-position clothing in the right zone.
If pose detection fails for any reason, clothing is still placed at a sensible
default position and you can move it manually.

### Where is my data?
Everything stays on your computer:
- `dressroom.db` — SQLite database (created automatically)
- `static/uploads/` — all uploaded and processed images

To fully reset the app, delete `dressroom.db` and the `static/uploads/`
folder, then restart.

### Accessing from another device on your WiFi
`run.py` binds to `0.0.0.0`, so other devices on the same local network can
reach the app. Find your computer's local IP address:
- **Windows:** `ipconfig` in Command Prompt → look for IPv4 Address
- **Mac/Linux:** `ifconfig` or `ip addr` → look for `192.168.x.x`

Then open `http://<your-ip>:5000` on the other device.

---

## Project structure

```
dressroom/
├── run.py                  ← Start the app with: python run.py
├── app.py                  ← All Flask routes and configuration
├── models.py               ← Database models (ClothingItem, PersonPhoto, SavedOutfit)
├── requirements.txt
├── utils/
│   ├── image_processing.py ← Background removal, thumbnails, file handling
│   ├── pose_detection.py   ← MediaPipe body landmark detection
│   └── default_wardrobe.py ← Generates starter clothing images on first launch
├── templates/
│   ├── base.html           ← Shared layout (navbar, toasts, modals)
│   ├── wardrobe.html       ← Wardrobe page
│   ├── dressing_room_select.html
│   └── dressing_room.html  ← Interactive dressing room canvas
└── static/
    ├── css/
    │   ├── main.css            ← Global dark theme and shared components
    │   └── dressing_room.css   ← Dressing room layout
    ├── js/
    │   ├── wardrobe.js         ← Upload, delete, filter logic
    │   └── dressing_room.js    ← Fabric.js canvas, drag-drop, outfit save/load
    └── uploads/                ← All user images (created automatically)
```

---

## Adding features

The code is structured to make changes straightforward:

| What you want to add | Where to look |
|---|---|
| New page | Add a `@app.route` in `app.py`, create a template in `templates/` |
| New clothing category | Add to `CATEGORIES` list in `models.py` |
| New default starter item | Add a row to `DEFAULTS` in `utils/default_wardrobe.py` |
| New database field | Add a column to the relevant model in `models.py` |
| Style changes | Edit CSS variables at the top of `static/css/main.css` |

---

## Acknowledgements

- Flask — web framework
- Flask-SQLAlchemy / SQLAlchemy — database ORM
- rembg — AI-powered background removal
- MediaPipe — body pose detection
- OpenCV — image processing utilities
- Pillow — image manipulation
- Fabric.js — interactive HTML5 canvas
- Bootstrap 5 — UI components and styling
- Bootstrap Icons — icon set