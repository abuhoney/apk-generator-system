/* Todo List function — front-end logic with localStorage */
(function () {
  'use strict';
  var STORAGE_KEY = 'bardom_todos';
  var todos = load();
  var form = document.getElementById('addForm');
  var input = document.getElementById('todoInput');
  var list = document.getElementById('todoList');
  var stats = document.getElementById('stats');

  function load() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
    catch (e) { return []; }
  }
  function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(todos)); }
  function uuid() { return 't-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8); }
  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function render() {
    var done = todos.filter(function (t) { return t.done; }).length;
    var total = todos.length;
    stats.textContent = total ? (done + ' of ' + total + ' done') : 'No tasks yet';
    if (!todos.length) {
      list.innerHTML = '<div class="empty">No tasks. Add one above.</div>';
      return;
    }
    list.innerHTML = todos.map(function (t) {
      return '<li class="' + (t.done ? 'done' : '') + '">' +
             '<input type="checkbox" data-id="' + t.id + '" ' + (t.done ? 'checked' : '') + '>' +
             '<span class="text">' + escapeHtml(t.text) + '</span>' +
             '<span class="date">' + (t.completed_at || t.created_at) + '</span>' +
             '<button class="del" data-id="' + t.id + '">×</button>' +
             '</li>';
    }).join('');
    list.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
      cb.addEventListener('change', function () { toggle(cb.dataset.id); });
    });
    list.querySelectorAll('.del').forEach(function (b) {
      b.addEventListener('click', function () { remove(b.dataset.id); });
    });
  }

  function add(text) {
    var now = new Date().toISOString();
    todos.unshift({ id: uuid(), text: text, done: false, created_at: now, completed_at: null });
    save(); render();
  }
  function toggle(id) {
    var t = todos.find(function (x) { return x.id === id; });
    if (t) {
      t.done = !t.done;
      t.completed_at = t.done ? new Date().toISOString() : null;
      save(); render();
    }
  }
  function remove(id) {
    todos = todos.filter(function (x) { return x.id !== id; });
    save(); render();
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (text) { add(text); input.value = ''; }
  });
  document.getElementById('btnClearDone').addEventListener('click', function () {
    todos = todos.filter(function (t) { return !t.done; }); save(); render();
  });
  document.getElementById('btnClearAll').addEventListener('click', function () {
    if (confirm('Delete all tasks?')) { todos = []; save(); render(); }
  });
  render();
})();
