/* Notes function — front-end logic with localStorage persistence */
(function () {
  'use strict';
  var STORAGE_KEY = 'bardom_notes';
  var notes = load();
  var currentId = null;
  var editor = document.getElementById('editor');
  var titleInput = document.getElementById('noteTitle');
  var bodyInput = document.getElementById('noteBody');
  var listEl = document.getElementById('notesList');
  var searchInput = document.getElementById('searchInput');

  function load() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
    catch (e) { return []; }
  }
  function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(notes)); }
  function uuid() { return 'n-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8); }

  function render() {
    var q = searchInput.value.toLowerCase();
    var filtered = notes.filter(function (n) {
      return !q || n.title.toLowerCase().indexOf(q) >= 0 || n.body.toLowerCase().indexOf(q) >= 0;
    });
    if (!filtered.length) {
      listEl.innerHTML = '<div class="empty">No notes yet. Tap "+ New Note" to begin.</div>';
      return;
    }
    listEl.innerHTML = filtered.map(function (n) {
      return '<div class="note-card" data-id="' + n.id + '">' +
             '<div class="title">' + escapeHtml(n.title) + '</div>' +
             '<div class="body">' + escapeHtml(n.body.slice(0, 120)) + '</div>' +
             '<div class="date">' + n.updated_at + '</div>' +
             '</div>';
    }).join('');
    listEl.querySelectorAll('.note-card').forEach(function (card) {
      card.addEventListener('click', function () { openEditor(card.dataset.id); });
    });
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function openEditor(id) {
    currentId = id || null;
    var note = id ? notes.find(function (n) { return n.id === id; }) : null;
    titleInput.value = note ? note.title : '';
    bodyInput.value = note ? note.body : '';
    editor.hidden = false;
  }
  function closeEditor() { editor.hidden = true; currentId = null; }

  function saveCurrent() {
    var title = titleInput.value.trim() || 'Untitled';
    var body = bodyInput.value;
    var now = new Date().toISOString();
    if (currentId) {
      var n = notes.find(function (x) { return x.id === currentId; });
      if (n) { n.title = title; n.body = body; n.updated_at = now; }
    } else {
      notes.unshift({ id: uuid(), title: title, body: body, created_at: now, updated_at: now });
      currentId = notes[0].id;
    }
    save(); render();
  }
  function deleteCurrent() {
    if (!currentId) return closeEditor();
    notes = notes.filter(function (n) { return n.id !== currentId; });
    save(); render(); closeEditor();
  }

  document.getElementById('btnNew').addEventListener('click', function () { openEditor(null); });
  document.getElementById('btnSave').addEventListener('click', saveCurrent);
  document.getElementById('btnDelete').addEventListener('click', deleteCurrent);
  document.getElementById('btnClose').addEventListener('click', closeEditor);
  searchInput.addEventListener('input', render);
  render();
})();
