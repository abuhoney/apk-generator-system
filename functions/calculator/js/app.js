/* Calculator function — front-end logic */
(function () {
  'use strict';
  var exprEl = document.getElementById('expr');
  var resultEl = document.getElementById('result');
  var historyList = document.getElementById('historyList');
  var current = '';

  function updateDisplay() { exprEl.textContent = current || '0'; }

  function safeEval(expression) {
    if (!/^[0-9+\-*/.() ]+$/.test(expression)) return { error: 'Invalid characters' };
    try {
      var result = Function('"use strict"; return (' + expression + ')')();
      if (typeof result !== 'number' || !isFinite(result)) return { error: 'Invalid result' };
      return { result: result };
    } catch (e) { return { error: e.message }; }
  }

  function appendValue(val) { current += val; updateDisplay(); }
  function clearAll() {
    current = ''; updateDisplay();
    resultEl.textContent = '= 0'; resultEl.style.color = '#58a6ff';
  }
  function evaluate() {
    var res = safeEval(current);
    if (res.error) {
      resultEl.textContent = 'Error: ' + res.error; resultEl.style.color = '#f85149'; return;
    }
    resultEl.textContent = '= ' + res.result; resultEl.style.color = '#3fb950';
    addHistory(current, res.result);
    current = String(res.result); updateDisplay();
  }
  function addHistory(expression, result) {
    var li = document.createElement('li');
    li.textContent = expression + ' = ' + result; li.style.cursor = 'pointer';
    li.onclick = function () {
      current = expression; updateDisplay();
      resultEl.textContent = '= ' + result; resultEl.style.color = '#3fb950';
    };
    historyList.insertBefore(li, historyList.firstChild);
  }

  document.querySelectorAll('.key').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var action = btn.dataset.action; var val = btn.dataset.val;
      if (action === 'clear') return clearAll();
      if (action === 'equals') return evaluate();
      if (val) return appendValue(val);
    });
  });

  document.addEventListener('keydown', function (e) {
    var key = e.key;
    if (/[0-9+\-*/.() ]/.test(key)) appendValue(key);
    else if (key === 'Enter' || key === '=') { e.preventDefault(); evaluate(); }
    else if (key === 'Escape' || key === 'c' || key === 'C') clearAll();
    else if (key === 'Backspace') { current = current.slice(0, -1); updateDisplay(); }
  });
  updateDisplay();
})();
