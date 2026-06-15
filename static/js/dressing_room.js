/* dressing_room.js — interactive canvas for the dressing room page */

'use strict';

// ─────────────────────────────────────────────────────────────────────────────
// Read data injected by the template
// ─────────────────────────────────────────────────────────────────────────────
const _data        = document.getElementById('dr-data');
const PERSON_ID    = parseInt(_data.dataset.personId);
const PERSON_URL   = _data.dataset.personUrl;

// ─────────────────────────────────────────────────────────────────────────────
// Canvas state
// ─────────────────────────────────────────────────────────────────────────────
let canvas          = null;   // Fabric.js canvas instance
let currentOutfitId = null;   // ID of the currently loaded saved outfit

// ─────────────────────────────────────────────────────────────────────────────
// Init on DOM ready
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  _initCanvas();
  _setupSidebarFilter();
  _setupDragDrop();
  _setupToolbar();
  _setupSaveModal();
  _setupKeyboard();

  // Close modals on backdrop click
  document.querySelectorAll('.dr-modal-backdrop').forEach(b => {
    b.addEventListener('click', e => { if (e.target === b) b.hidden = true; });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Canvas initialisation
// ─────────────────────────────────────────────────────────────────────────────
function _initCanvas() {
  const outer = document.getElementById('canvasContainer');

  // Calculate canvas dimensions to fill available space with a 3:4 portrait ratio
  const parentEl   = outer.parentElement;
  const availW     = parentEl.clientWidth  - 32;
  const availH     = parentEl.clientHeight - 32;
  const ratio      = 3 / 4;
  let   cW         = availW;
  let   cH         = Math.round(cW / ratio);
  if (cH > availH) { cH = availH; cW = Math.round(cH * ratio); }
  cW = Math.max(cW, 240); cH = Math.max(cH, 320);

  canvas = new fabric.Canvas('dressingCanvas', {
    width:                 cW,
    height:                cH,
    backgroundColor:       '#16213e',
    preserveObjectStacking:true,
    selection:             true,
  });

  _loadPersonPhoto();

  // Recalculate on window resize
  window.addEventListener('resize', _debounce(_resizeCanvas, 300));
}

function _loadPersonPhoto() {
  fabric.Image.fromURL(PERSON_URL, img => {
    const scale = Math.min(canvas.width / img.width, canvas.height / img.height) * 0.95;
    img.set({
      left:        canvas.width  / 2,
      top:         canvas.height / 2,
      originX:     'center',
      originY:     'center',
      scaleX:      scale,
      scaleY:      scale,
      selectable:  false,
      evented:     false,
      hoverCursor: 'default',
      data:        { type: 'person' },
    });
    canvas.add(img);
    canvas.renderAll();
  });
}

function _resizeCanvas() {
  const parentEl = document.getElementById('canvasContainer').parentElement;
  const availW   = parentEl.clientWidth  - 32;
  const availH   = parentEl.clientHeight - 32;
  const ratio    = 3 / 4;
  let   cW       = availW;
  let   cH       = Math.round(cW / ratio);
  if (cH > availH) { cH = availH; cW = Math.round(cH * ratio); }
  cW = Math.max(cW, 240); cH = Math.max(cH, 320);

  // Scale existing objects proportionally
  const scaleX = cW / canvas.width;
  const scaleY = cH / canvas.height;
  canvas.setWidth(cW);
  canvas.setHeight(cH);
  canvas.getObjects().forEach(obj => {
    obj.set({
      left:   obj.left   * scaleX,
      top:    obj.top    * scaleY,
      scaleX: obj.scaleX * scaleX,
      scaleY: obj.scaleY * scaleY,
    });
    obj.setCoords();
  });
  canvas.renderAll();
}

// ─────────────────────────────────────────────────────────────────────────────
// Add a clothing item to the canvas (shared by drag-drop and mobile tap)
// ─────────────────────────────────────────────────────────────────────────────
async function sidebarAddItem(clothingId, clothingUrl, category, name) {
  document.getElementById('canvasLoading').hidden = false;
  try {
    // Ask the server for the best position based on body pose
    const posRes = await fetch('/api/clothing-position', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        person_photo_id: PERSON_ID,
        clothing_id:     clothingId,
        canvas_width:    canvas.width,
        canvas_height:   canvas.height,
      }),
    });
    const pos = await posRes.json();

    fabric.Image.fromURL(clothingUrl, img => {
      img.set({
        left:   pos.x,
        top:    pos.y,
        scaleX: pos.width  / img.width,
        scaleY: pos.height / img.height,
        // Style the selection handles with the app accent colour
        borderColor:         '#e91e8c',
        cornerColor:         '#e91e8c',
        cornerStyle:         'circle',
        cornerSize:          10,
        transparentCorners:  false,
        data: { type: 'clothing', id: clothingId, name },
      });
      canvas.add(img);
      canvas.setActiveObject(img);
      canvas.renderAll();
      document.getElementById('canvasLoading').hidden = true;
    });
  } catch (err) {
    console.error('addClothingItem failed:', err);
    document.getElementById('canvasLoading').hidden = true;
    showToast('Could not place item — try again.', 'error');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Desktop drag and drop  (from sidebar to canvas)
// ─────────────────────────────────────────────────────────────────────────────
function _setupDragDrop() {
  const canvasEl  = document.getElementById('dressingCanvas');
  const dropHint  = document.getElementById('dropHint');

  // Make sidebar items draggable and attach their data
  document.querySelectorAll('.sidebar-item').forEach(item => {
    item.addEventListener('dragstart', e => {
      e.dataTransfer.setData('clothing-id',  item.dataset.id);
      e.dataTransfer.setData('clothing-url', item.dataset.url);
      e.dataTransfer.setData('clothing-cat', item.dataset.cat);
      e.dataTransfer.setData('clothing-name',item.dataset.name);
      e.dataTransfer.effectAllowed = 'copy';
      dropHint.hidden = false;
    });
    item.addEventListener('dragend', () => { dropHint.hidden = true; });
  });

  canvasEl.addEventListener('dragover', e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });

  canvasEl.addEventListener('dragleave', () => { dropHint.hidden = true; });

  canvasEl.addEventListener('drop', e => {
    e.preventDefault();
    dropHint.hidden = true;
    const id   = parseInt(e.dataTransfer.getData('clothing-id'));
    const url  = e.dataTransfer.getData('clothing-url');
    const cat  = e.dataTransfer.getData('clothing-cat');
    const name = e.dataTransfer.getData('clothing-name');
    if (id && url) sidebarAddItem(id, url, cat, name);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar category filter
// ─────────────────────────────────────────────────────────────────────────────
function _setupSidebarFilter() {
  document.querySelectorAll('.sf-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.sf-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const cat = pill.dataset.cat;
      document.querySelectorAll('.sidebar-item').forEach(item => {
        item.classList.toggle(
          'hidden-by-filter',
          cat !== 'all' && item.dataset.cat !== cat
        );
      });
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Toolbar buttons
// ─────────────────────────────────────────────────────────────────────────────
function _setupToolbar() {
  document.getElementById('btnDeleteSelected')?.addEventListener('click', _deleteSelected);
  document.getElementById('btnBringFwd')?.addEventListener('click', _bringForward);
  document.getElementById('btnSendBack')?.addEventListener('click', _sendBackward);
  document.getElementById('btnClearAll')?.addEventListener('click', () => {
    if (!confirm('Remove all clothing from the canvas?')) return;
    canvas.getObjects()
      .filter(o => o.data?.type === 'clothing')
      .forEach(o => canvas.remove(o));
    canvas.renderAll();
    currentOutfitId = null;
  });
  document.getElementById('btnSaveOutfit')?.addEventListener('click', () => {
    document.getElementById('outfitNameInput').value = '';
    document.getElementById('modalSaveOutfit').hidden = false;
    setTimeout(() => document.getElementById('outfitNameInput').focus(), 80);
  });
}

function _deleteSelected() {
  const obj = canvas.getActiveObject();
  if (obj && obj.data?.type === 'clothing') {
    canvas.remove(obj);
    canvas.renderAll();
  }
}

function _bringForward() {
  const obj = canvas.getActiveObject();
  if (obj) { canvas.bringForward(obj); canvas.renderAll(); }
}

function _sendBackward() {
  const obj = canvas.getActiveObject();
  if (obj && obj.data?.type === 'clothing') {
    canvas.sendBackwards(obj);
    // Keep person photo at the very bottom no matter what
    const person = canvas.getObjects().find(o => o.data?.type === 'person');
    if (person) canvas.sendToBack(person);
    canvas.renderAll();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Keyboard shortcuts
// ─────────────────────────────────────────────────────────────────────────────
function _setupKeyboard() {
  document.addEventListener('keydown', e => {
    // Ignore when typing in an input
    if (['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    if (e.key === 'Delete' || e.key === 'Backspace') _deleteSelected();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Save outfit modal
// ─────────────────────────────────────────────────────────────────────────────
function _setupSaveModal() {
  document.getElementById('btnConfirmSave')?.addEventListener('click', async () => {
    const name = document.getElementById('outfitNameInput').value.trim();
    if (!name) {
      document.getElementById('outfitNameInput').focus();
      return;
    }
    closeModal('modalSaveOutfit');
    await _saveOutfit(name);
  });

  document.getElementById('outfitNameInput')?.addEventListener('keydown', async e => {
    if (e.key === 'Enter') {
      const name = e.target.value.trim();
      if (!name) return;
      closeModal('modalSaveOutfit');
      await _saveOutfit(name);
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Save / Load / Delete outfits
// ─────────────────────────────────────────────────────────────────────────────
async function _saveOutfit(name) {
  try {
    const outfitData = canvas.toJSON(['data']);
    const res = await fetch('/api/outfits', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        id:              currentOutfitId,
        name,
        person_photo_id: PERSON_ID,
        outfit_data:     outfitData,
      }),
    });
    const saved = await res.json();
    currentOutfitId = saved.id;
    showToast(`Outfit "${saved.name}" saved!`, 'success');
    await _refreshOutfitList();
  } catch {
    showToast('Could not save outfit.', 'error');
  }
}

// Called from inline onclick in template
async function loadOutfit(outfitId) {
  try {
    const res    = await fetch(`/api/outfits/${outfitId}`);
    const outfit = await res.json();
    if (!outfit.outfit_data) { showToast('Outfit has no saved data.', 'error'); return; }

    canvas.loadFromJSON(outfit.outfit_data, () => {
      // Re-lock person photo layer after loading
      canvas.getObjects().forEach(obj => {
        if (obj.data?.type === 'person') {
          obj.selectable  = false;
          obj.evented     = false;
          obj.hoverCursor = 'default';
        }
      });
      canvas.renderAll();
    });

    currentOutfitId = outfit.id;
    showToast(`Loaded: ${outfit.name}`, 'success');
  } catch {
    showToast('Could not load outfit.', 'error');
  }
}

// Called from inline onclick in template and re-rendered list
async function deleteOutfit(outfitId) {
  if (!confirm('Delete this saved outfit?')) return;
  try {
    await fetch(`/api/outfits/${outfitId}`, { method: 'DELETE' });
    if (currentOutfitId === outfitId) currentOutfitId = null;
    showToast('Outfit deleted.', 'success');
    await _refreshOutfitList();
  } catch {
    showToast('Could not delete outfit.', 'error');
  }
}

async function _refreshOutfitList() {
  try {
    const res     = await fetch(`/api/outfits?person_photo_id=${PERSON_ID}`);
    const outfits = await res.json();
    _renderOutfitList(outfits);
  } catch { /* silently ignore */ }
}

function _renderOutfitList(outfits) {
  const container = document.getElementById('outfitList');
  if (!container) return;

  if (!outfits.length) {
    container.innerHTML =
      '<p class="outfit-empty">No saved outfits yet. Style something and hit Save!</p>';
    return;
  }

  container.innerHTML = outfits.map(o => `
    <div class="outfit-row" id="outfit-${o.id}">
      <button class="outfit-load-btn" onclick="loadOutfit(${o.id})">${_esc(o.name)}</button>
      <button class="outfit-del-btn"  onclick="deleteOutfit(${o.id})" title="Delete">
        <i class="bi bi-trash"></i>
      </button>
    </div>
  `).join('');
}

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────
function _debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function _esc(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
