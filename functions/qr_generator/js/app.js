/* QR Generator — front-end logic */
(function () {
  'use strict';
  var input = document.getElementById('qrInput');
  var sizeRange = document.getElementById('qrSize');
  var sizeLabel = document.getElementById('sizeLabel');
  var btnGenerate = document.getElementById('btnGenerate');
  var btnDownload = document.getElementById('btnDownload');
  var btnCopy = document.getElementById('btnCopy');
  var preview = document.getElementById('qrPreview');
  var historyEl = document.getElementById('qrHistory');
  var history = JSON.parse(localStorage.getItem('bardom_qr_history') || '[]');

  function saveHistory() { localStorage.setItem('bardom_qr_history', JSON.stringify(history.slice(0, 20))); }

  function renderHistory() {
    historyEl.innerHTML = history.map(function (h) {
      return '<li data-text="' + encodeURIComponent(h) + '">' + h.slice(0, 80) + '</li>';
    }).join('');
    historyEl.querySelectorAll('li').forEach(function (li) {
      li.addEventListener('click', function () {
        input.value = decodeURIComponent(li.dataset.text);
        generate();
      });
    });
  }

  function generate() {
    var text = input.value.trim() || ' ';
    var size = parseInt(sizeRange.value, 10);
    var enc = encodeURIComponent(text);
    var url = 'https://quickchart.io/qr?text=' + enc + '&size=' + size;
    preview.innerHTML = '<img src="' + url + '" alt="QR code" id="qrImg">';
    if (history[0] !== text) {
      history.unshift(text);
      saveHistory();
      renderHistory();
    }
  }

  btnGenerate.addEventListener('click', generate);
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) generate(); });
  sizeRange.addEventListener('input', function () { sizeLabel.textContent = sizeRange.value + ' px'; });
  btnDownload.addEventListener('click', function () {
    var img = document.getElementById('qrImg');
    if (!img) return;
    fetch(img.src).then(function (r) { return r.blob(); }).then(function (blob) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'qr-' + Date.now() + '.png';
      a.click();
    });
  });
  btnCopy.addEventListener('click', function () {
    var img = document.getElementById('qrImg');
    if (!img) return;
    fetch(img.src).then(function (r) { return r.blob(); }).then(function (blob) {
      if (navigator.clipboard && navigator.clipboard.write) {
        navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
      }
    });
  });
  renderHistory();
})();
