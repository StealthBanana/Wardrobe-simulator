/* wardrobe.js — handles all interactions on the wardrobe page */

'use strict';

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────
let _pendingClothingFile = null;
let _pendingPersonFile   = null;

// ─────────────────────────────────────────────────────────────────────────────
// Bootstrap — runs when the DOM is ready
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  _initClothingDropzone();
  _initPersonDropzone();
  _initCategoryFilter();

  // Modal open buttons
  document.getElementById('btnOpenAddClothing')
    ?.addEventListener('click', () => document.getElementById('clothingFileInput').click());
  document.getElementById('btnOpenAddPerson')
    ?.addEventListener('click', () => document.getElementById('personFileInput').click());

  // Modal submit buttons
  document.getElementById('btnSubmitClothing')
    ?.addEventListener('click', _submitClothingUpload);
  document.getElementById('btnSubmitPerson')
    ?.addEventListener('click', _submitPersonUpload);

  // Allow pressing Enter inside name inputs to submit
  document.getElementById('clothingName')
    ?.addEventListener('keydown', e => { if (e.key === 'Enter') _submitClothingUpload(); });
  document.getElementById('personName')
    ?.addEventListener('keydown', e => { if (e.key === 'Enter') _submitPersonUpload(); });

  // Close modal on backdrop click
  document.querySelectorAll('.dr-modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', e => {
      if (e.target === backdrop) backdrop.hidden = true;
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Clothing drop zone
// ─────────────────────────────────────────────────────────────────────────────
function _initClothingDropzone() {
  const zone  = document.getElementById('clothingDropzone');
  const input = document.getElementById('clothingFileInput');
  if (!zone || !input) return;

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') input.click(); });

  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('dz-active'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dz-active'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dz-active');
    const files = Array.from(e.dataTransfer.files);
    // If multiple files dropped, open modal for first valid one
    const valid = files.filter(_isValidImage);
    if (valid.length) _openClothingModal(valid[0]);
  });

  input.addEventListener('change', e => {
    if (e.target.files.length) _openClothingModal(e.target.files[0]);
    input.value = '';
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Person photo drop zone
// ─────────────────────────────────────────────────────────────────────────────
function _initPersonDropzone() {
  const zone  = document.getElementById('personDropzone');
  const input = document.getElementById('personFileInput');
  if (!zone || !input) return;

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') input.click(); });

  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('dz-active'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dz-active'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dz-active');
    const f = e.dataTransfer.files[0];
    if (f && _isValidImage(f)) _openPersonModal(f);
  });

  input.addEventListener('change', e => {
    if (e.target.files[0]) _openPersonModal(e.target.files[0]);
    input.value = '';
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Open modals
// ─────────────────────────────────────────────────────────────────────────────
function _openClothingModal(file) {
  _pendingClothingFile = file;

  // Show image preview
  const preview = document.getElementById('clothingPreviewImg');
  const reader = new FileReader();
  reader.onload = e => { preview.src = e.target.result; preview.hidden = false; };
  reader.readAsDataURL(file);

  // Pre-fill name from filename (strip extension)
  document.getElementById('clothingName').value =
    file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');

  document.getElementById('clothingProcessing').hidden = true;
  document.getElementById('modalAddClothing').hidden = false;
  setTimeout(() => document.getElementById('clothingName').focus(), 80);
}

function _openPersonModal(file) {
  _pendingPersonFile = file;

  const preview = document.getElementById('personPreviewImg');
  const reader = new FileReader();
  reader.onload = e => { preview.src = e.target.result; preview.hidden = false; };
  reader.readAsDataURL(file);

  document.getElementById('personName').value = '';
  document.getElementById('personProcessing').hidden = true;
  document.getElementById('modalAddPerson').hidden = false;
  setTimeout(() => document.getElementById('personName').focus(), 80);
}

// ─────────────────────────────────────────────────────────────────────────────
// Submit clothing upload
// ─────────────────────────────────────────────────────────────────────────────
async function _submitClothingUpload() {
  if (!_pendingClothingFile) return;

  const name     = document.getElementById('clothingName').value.trim();
  const category = document.getElementById('clothingCategory').value;
  const btn      = document.getElementById('btnSubmitClothing');

  if (!name) {
    document.getElementById('clothingName').focus();
    _flashInput('clothingName');
    return;
  }

  const formData = new FormData();
  formData.append('file', _pendingClothingFile);
  formData.append('name', name);
  formData.append('category', category);

  _setBtn(btn, true, 'Processing…');
  document.getElementById('clothingProcessing').hidden = false;

  try {
    const res  = await fetch('/upload-clothing', { method: 'POST', body: formData });
    const data = await res.json();

    if (data.success) {
      closeModal('modalAddClothing');
      _addClothingCard(data.item);
      showToast(`"${data.item.name}" added to wardrobe!`, 'success');
    } else {
      showToast(data.error || 'Upload failed.', 'error');
    }
  } catch {
    showToast('Network error — please try again.', 'error');
  } finally {
    _setBtn(btn, false, 'Add to Wardrobe');
    document.getElementById('clothingProcessing').hidden = true;
    _pendingClothingFile = null;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Submit person photo upload
// ─────────────────────────────────────────────────────────────────────────────
async function _submitPersonUpload() {
  if (!_pendingPersonFile) return;

  const name = (document.getElementById('personName').value.trim()) || 'My Photo';
  const btn  = document.getElementById('btnSubmitPerson');

  const formData = new FormData();
  formData.append('file', _pendingPersonFile);
  formData.append('name', name);

  _setBtn(btn, true, 'Processing…');
  document.getElementById('personProcessing').hidden = false;

  try {
    const res  = await fetch('/upload-person', { method: 'POST', body: formData });
    const data = await res.json();

    if (data.success) {
      closeModal('modalAddPerson');
      _addPersonCard(data.photo);
      showToast(`Photo "${data.photo.name}" added!`, 'success');
    } else {
      showToast(data.error || 'Upload failed.', 'error');
    }
  } catch {
    showToast('Network error — please try again.', 'error');
  } finally {
    _setBtn(btn, false, 'Process Photo');
    document.getElementById('personProcessing').hidden = true;
    _pendingPersonFile = null;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Delete clothing  (called from inline onclick in template)
// ─────────────────────────────────────────────────────────────────────────────
async function deleteClothing(id) {
  if (!confirm('Remove this item from your wardrobe?')) return;
  try {
    const res = await fetch(`/delete-clothing/${id}`, { method: 'DELETE' });
    if ((await res.json()).success) {
      document.getElementById(`ci-${id}`)?.remove();
      _checkEmpty('clothingGrid', 'clothingEmpty', 'clothing');
      showToast('Item removed.', 'success');
    }
  } catch {
    showToast('Could not delete item.', 'error');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Delete person photo  (called from inline onclick in template)
// ─────────────────────────────────────────────────────────────────────────────
async function deletePerson(id) {
  if (!confirm('Delete this photo?')) return;
  try {
    const res = await fetch(`/delete-person/${id}`, { method: 'DELETE' });
    if ((await res.json()).success) {
      document.getElementById(`pp-${id}`)?.remove();
      _checkEmpty('personGrid', 'personEmpty', 'person');
      showToast('Photo deleted.', 'success');
    }
  } catch {
    showToast('Could not delete photo.', 'error');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Category filter
// ─────────────────────────────────────────────────────────────────────────────
function _initCategoryFilter() {
  document.querySelectorAll('.filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const cat = pill.dataset.cat;
      document.querySelectorAll('.item-col[data-cat]').forEach(col => {
        col.style.display = (cat === 'all' || col.dataset.cat === cat) ? '' : 'none';
      });
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// DOM helpers
// ─────────────────────────────────────────────────────────────────────────────
function _addClothingCard(item) {
  const grid = document.getElementById('clothingGrid');
  document.getElementById('clothingEmpty')?.remove();

  const col = document.createElement('div');
  col.className = 'item-col';
  col.id        = `ci-${item.id}`;
  col.dataset.cat = item.category;

  const catLabel = item.category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const imgTag   = item.thumbnail_url
    ? `<img src="${item.thumbnail_url}" alt="${_esc(item.name)}" loading="lazy">`
    : `<div class="item-placeholder"><i class="bi bi-image"></i></div>`;

  col.innerHTML = `
    <div class="item-card">
      <div class="item-card-img">
        ${imgTag}
        <div class="item-card-overlay">
          <button class="btn-icon-red" onclick="deleteClothing(${item.id})" title="Delete">
            <i class="bi bi-trash"></i>
          </button>
        </div>
      </div>
      <div class="item-card-foot">
        <p class="item-name" title="${_esc(item.name)}">${_esc(item.name)}</p>
        <span class="item-cat">${catLabel}</span>
      </div>
    </div>`;

  grid.prepend(col);
  _updateCount('clothingGrid', '.section-count');
}

function _addPersonCard(photo) {
  const grid = document.getElementById('personGrid');
  document.getElementById('personEmpty')?.remove();

  const col = document.createElement('div');
  col.className = 'item-col';
  col.id        = `pp-${photo.id}`;

  const imgTag = photo.processed_url
    ? `<img src="${photo.processed_url}" alt="${_esc(photo.name)}" loading="lazy">`
    : `<div class="item-placeholder"><i class="bi bi-person"></i></div>`;

  const poseTag = photo.has_pose
    ? `<span class="pose-badge"><i class="bi bi-person-check me-1"></i>Pose Ready</span>` : '';
  const catText = photo.has_pose
    ? `<span class="item-cat" style="color:var(--success)">Auto-placement on</span>`
    : `<span class="item-cat">No pose data</span>`;

  col.innerHTML = `
    <div class="item-card person-card">
      <div class="item-card-img person-card-img">
        ${imgTag}
        <div class="item-card-overlay">
          <a class="btn-icon-accent" href="/dressing-room/${photo.id}" title="Open in Dressing Room">
            <i class="bi bi-scissors"></i>
          </a>
          <button class="btn-icon-red" onclick="deletePerson(${photo.id})" title="Delete">
            <i class="bi bi-trash"></i>
          </button>
        </div>
        ${poseTag}
      </div>
      <div class="item-card-foot">
        <p class="item-name" title="${_esc(photo.name)}">${_esc(photo.name)}</p>
        ${catText}
      </div>
    </div>`;

  grid.prepend(col);
}

function _checkEmpty(gridId, emptyId, type) {
  const grid = document.getElementById(gridId);
  if (!grid) return;
  const hasItems = grid.querySelector('.item-col');
  if (!hasItems && !document.getElementById(emptyId)) {
    const icon  = type === 'clothing' ? 'bi-bag-x' : 'bi-person-slash';
    const title = type === 'clothing' ? 'No clothes yet' : 'No photos yet';
    const sub   = type === 'clothing'
      ? 'Upload an item above to get started.'
      : 'Add a photo so you can try clothes on.';
    const div = document.createElement('div');
    div.className = 'empty-state'; div.id = emptyId;
    div.innerHTML = `<i class="bi ${icon} empty-icon"></i>
      <p class="empty-title">${title}</p>
      <p class="empty-sub">${sub}</p>`;
    grid.appendChild(div);
  }
}

function _updateCount(gridId, selector) {
  const count = document.getElementById(gridId)?.querySelectorAll('.item-col').length ?? 0;
  const el = document.querySelector(selector);
  if (el) el.textContent = count;
}

function _setBtn(btn, disabled, label) {
  btn.disabled = disabled;
  btn.textContent = label;
}

function _flashInput(id) {
  const el = document.getElementById(id);
  el?.classList.add('dr-input-error');
  setTimeout(() => el?.classList.remove('dr-input-error'), 1200);
}

function _isValidImage(file) {
  const ok = ['image/jpeg','image/png','image/webp'];
  if (!ok.includes(file.type)) { showToast('Only JPG, PNG, or WebP files allowed.', 'error'); return false; }
  if (file.size > 16 * 1024 * 1024) { showToast('File must be under 16 MB.', 'error'); return false; }
  return true;
}

function _esc(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
