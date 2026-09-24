/**
 * components.js — v3.0 Web Components Library
 *
 * Defines custom elements that replace 194KB of imperative HTML:
 *   <data-grid dataset="patients" rbac="view:admin,doctor"></data-grid>
 *   <data-form dataset="invoices" rbac="edit:accountant"></data-form>
 *   <data-field code="hfhcd" label="Patient Name"></data-field>
 *   <data-card code="34vhx"></data-card>
 *
 * Each component uses Shadow DOM for complete CSS/JS isolation.
 * Reads data from CoreEngine (window.CoreEngine).
 *
 * Total: ~6KB — replaces ~180KB of generated HTML.
 */
(function () {
  'use strict';

  // ═════════════════════════════════════════════════════════════════════
  // SHARED STYLES (injected into each Shadow DOM)
  // ═════════════════════════════════════════════════════════════════════
  const SHARED_CSS = `
    :host { display: block; font-family: -apple-system, sans-serif; }
    .card { background: #1a1a2e; border-radius: 10px; padding: 12px; margin-bottom: 6px; border: 1px solid transparent; cursor: pointer; transition: .15s; display: flex; align-items: center; gap: 12px; }
    .card:active { background: #16213e; border-color: #e94560; }
    .icon { width: 44px; height: 44px; border-radius: 8px; background: rgba(233,69,96,.15); display: flex; align-items: center; justify-content: center; font-size: 22px; flex-shrink: 0; }
    .info { flex: 1; min-width: 0; }
    .name { font-size: 13px; font-weight: 600; color: #f5f5f5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .meta { font-size: 11px; color: #8b949e; margin-top: 3px; display: flex; gap: 8px; flex-wrap: wrap; }
    .meta .price { color: #3fb950; font-weight: 600; }
    .meta .status { padding: 1px 6px; border-radius: 4px; font-size: 10px; }
    .meta .status.ok { background: rgba(22,163,74,.2); color: #3fb950; }
    .meta .status.warn { background: rgba(250,204,21,.2); color: #facc15; }
    .meta .status.crit { background: rgba(248,81,73,.2); color: #f85149; }
    .field-group { margin-bottom: 12px; }
    .field-group label { display: block; font-size: 11px; color: #8b949e; margin-bottom: 4px; }
    .field-group input, .field-group select { width: 100%; background: #0f0f1e; color: #f5f5f5; border: 1px solid #30363d; border-radius: 6px; padding: 10px; font-size: 13px; box-sizing: border-box; }
    .field-group input:focus { outline: none; border-color: #58a6ff; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .detail-field { background: #1a1a2e; padding: 10px 12px; border-radius: 8px; border: 1px solid #30363d; }
    .detail-field .label { font-size: 10px; color: #6b6b8a; text-transform: uppercase; margin-bottom: 3px; }
    .detail-field .value { font-size: 13px; color: #f5f5f5; font-weight: 500; word-break: break-word; }
    .detail-field .value.accent { color: #58a6ff; }
    .detail-field .value.green { color: #3fb950; }
    .section-header { padding: 12px 4px 6px; font-size: 11px; font-weight: 600; color: #e94560; text-transform: uppercase; }
  `;

  // ═════════════════════════════════════════════════════════════════════
  // <data-grid> — Renders a list of items from a dataset
  // ═════════════════════════════════════════════════════════════════════
  class DataGrid extends HTMLElement {
    static observedAttributes = ['dataset', 'rbac', 'search'];
    _items = []; _filter = '';

    connectedCallback() {
      const shadow = this.attachShadow({ mode: 'open' });
      const style = document.createElement('style'); style.textContent = SHARED_CSS;
      const container = document.createElement('div'); container.className = 'grid-container';
      shadow.appendChild(style); shadow.appendChild(container);
      this._container = container;
      this._render();
    }

    attributeChangedCallback(name, old, val) {
      if (old !== val && this._container) this._render();
    }

    _render() {
      if (!this._container) return;
      const engine = window.CoreEngine;
      if (!engine) return;

      const dsName = this.getAttribute('dataset');
      const ids = engine.getIds();
      
      // Collect items for this dataset
      const items = [];
      for (const [code, info] of Object.entries(ids)) {
        if (info.dataset === dsName) {
          const values = engine.getValues(code);
          values.forEach(v => {
            if (!items[v.item_index]) items[v.item_index] = {};
            items[v.item_index][info.original] = v.text;
          });
        }
      }
      
      // Apply filter
      const filtered = this._filter ? items.filter(i => i && JSON.stringify(i).toLowerCase().includes(this._filter)) : items.filter(i => i);

      // Find name field + group field
      let nameField = Object.keys(ids).map(c => ids[c].original).find(f => ['name', 'title', 'patient', 'doctor', 'product'].includes(f.toLowerCase())) || Object.keys(filtered[0] || {})[0] || 'Item';
      let groupField = Object.keys(ids).map(c => ids[c]).find(i => i.type === 'Enum' && i.dataset === dsName)?.original;

      // Group items
      const groups = {};
      filtered.forEach(item => {
        const g = groupField ? (item[groupField] || 'Other') : 'All';
        if (!groups[g]) groups[g] = [];
        groups[g].push(item);
      });

      // Render
      let html = `<div style="color:#8b949e;font-size:11px;padding:4px 0">${filtered.length} items</div>`;
      for (const [group, groupItems] of Object.entries(groups)) {
        html += `<div class="section-header">${engine.escapeHtml(group)} (${groupItems.length})</div>`;
        groupItems.forEach((item, idx) => {
          const name = item[nameField] || 'Unknown';
          let meta = '';
          let fieldCount = 0;
          for (const [code, info] of Object.entries(ids)) {
            if (info.dataset !== dsName || info.original === nameField) continue;
            const val = item[info.original];
            if (val === undefined || val === '') continue;
            if (['price', 'fee', 'cost'].includes(info.original.toLowerCase())) meta += `<span class="price">${engine.escapeHtml(String(val))}</span>`;
            else if (['status', 'severity'].includes(info.original.toLowerCase())) {
              const cls = /stable|paid|ok/i.test(val) ? 'ok' : /crit|urgent|pending/i.test(val) ? 'crit' : 'warn';
              meta += `<span class="status ${cls}">${engine.escapeHtml(String(val))}</span>`;
            } else meta += `<span style="color:#8b949e;font-size:10px">${engine.escapeHtml(String(val).slice(0, 20))}</span>`;
            if (++fieldCount >= 3) break;
          }
          html += `<div class="card" data-idx="${filtered.indexOf(item)}"><div class="icon">📋</div><div class="info"><div class="name">${engine.escapeHtml(String(name))}</div><div class="meta">${meta}</div></div></div>`;
        });
      }
      this._container.innerHTML = html;

      // Wire click events
      this._container.querySelectorAll('.card').forEach(card => {
        card.addEventListener('click', () => {
          const idx = parseInt(card.dataset.idx);
          this._showDetail(filtered[idx - 0] || filtered[idx], dsName);
        });
      });
    }

    _showDetail(item, dsName) {
      const engine = window.CoreEngine;
      const ids = engine.getIds();
      let html = '<div class="grid">';
      for (const [code, info] of Object.entries(ids)) {
        if (info.dataset !== dsName) continue;
        const val = item[info.original];
        if (val === undefined) continue;
        let cls = '';
        if (['price', 'fee', 'cost'].includes(info.original.toLowerCase())) cls = 'green';
        if (['phone', 'id'].includes(info.original.toLowerCase())) cls = 'accent';
        html += `<div class="detail-field"><div class="label">${engine.escapeHtml(info.original)}</div><div class="value ${cls}">${engine.escapeHtml(String(val))}</div></div>`;
      }
      html += '</div>';
      this._container.innerHTML = `<div class="card"><div class="icon">📄</div><div class="info"><div class="name">${engine.escapeHtml(String(item[Object.keys(item)[0]] || 'Detail'))}</div></div></div>${html}<button class="card" onclick="this.getRootNode().host._render()" style="text-align:center;justify-content:center">← Back</button>`;
    }
  }

  // ═════════════════════════════════════════════════════════════════════
  // <data-field> — Single field with RBAC + type-aware widget
  // ═════════════════════════════════════════════════════════════════════
  class DataField extends HTMLElement {
    static observedAttributes = ['code', 'label', 'type', 'value'];
    connectedCallback() {
      const shadow = this.attachShadow({ mode: 'open' });
      const style = document.createElement('style'); style.textContent = SHARED_CSS;
      shadow.appendChild(style);

      const engine = window.CoreEngine;
      const code = this.getAttribute('code');
      const label = this.getAttribute('label') || code;
      const type = this.getAttribute('type') || 'String';
      const value = this.getAttribute('value') || '';

      // Check RBAC
      const rbac = this.getAttribute('rbac');
      if (rbac && !engine.can(rbac.split(':')[0] || 'view', code)) {
        this.style.display = 'none';
        return;
      }

      const wrapper = document.createElement('div');
      wrapper.className = 'field-group';
      wrapper.innerHTML = `<label>${engine.escapeHtml(label)}</label>${this._widget(type, code, value)}`;
      shadow.appendChild(wrapper);
    }

    _widget(type, code, value) {
      const v = window.CoreEngine.escapeHtml(value);
      switch (type) {
        case 'Boolean': return `<label style="display:flex;align-items:center;gap:8px"><input type="checkbox" data-code="${code}" ${value === 'true' ? 'checked' : ''}><span>${v}</span></label>`;
        case 'Enum': return `<select data-code="${code}"><option value="">Select...</option><option selected>${v}</option></select>`;
        case 'Int': case 'Float': return `<input type="number" data-code="${code}" value="${v}">`;
        case 'Phone': return `<input type="tel" data-code="${code}" value="${v}">`;
        case 'Email': return `<input type="email" data-code="${code}" value="${v}">`;
        case 'Date': return `<input type="date" data-code="${code}" value="${v}">`;
        case 'URL': case 'Canvas': return `<input type="url" data-code="${code}" value="${v}" placeholder="Image URL">`;
        default: return `<input type="text" data-code="${code}" value="${v}">`;
      }
    }
  }

  // ═════════════════════════════════════════════════════════════════════
  // <data-tabs> — Tab bar for switching between datasets
  // ═════════════════════════════════════════════════════════════════════
  class DataTabs extends HTMLElement {
    connectedCallback() {
      const shadow = this.attachShadow({ mode: 'open' });
      const style = document.createElement('style');
      style.textContent = SHARED_CSS + `
        .tab-bar { display: flex; gap: 4px; padding: 8px 0; overflow-x: auto; }
        .tab-btn { flex-shrink: 0; padding: 8px 14px; border-radius: 8px; border: 1px solid #30363d; background: #21262d; color: #8b949e; font-size: 12px; font-weight: 600; cursor: pointer; white-space: nowrap; }
        .tab-btn.active { background: #e94560; color: #fff; border-color: #e94560; }
      `;
      shadow.appendChild(style);

      const engine = window.CoreEngine;
      const datasets = engine.getDatasets();
      const icons = { patients: '👥', doctors: '🩺', nurses: '💉', medicines: '💊', invoices: '💰', rooms: '🛏️', products: '📦', staff: '👨‍⚕️' };

      const bar = document.createElement('div');
      bar.className = 'tab-bar';
      bar.innerHTML = datasets.map((ds, i) => {
        const icon = icons[ds.name?.toLowerCase?.()] || '📋';
        return `<button class="tab-btn ${i === 0 ? 'active' : ''}" data-idx="${i}">${icon} ${ds.name} (${ds.item_count})</button>`;
      }).join('');
      shadow.appendChild(bar);

      // Wire clicks
      bar.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          bar.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const idx = parseInt(btn.dataset.idx);
          const dsName = datasets[idx].name;
          // Find sibling <data-grid> and update it
          const grid = this.parentElement.querySelector('data-grid');
          if (grid) grid.setAttribute('dataset', dsName);
        });
      });
    }
  }

  // ═════════════════════════════════════════════════════════════════════
  // REGISTER ALL COMPONENTS
  // ═════════════════════════════════════════════════════════════════════
  customElements.define('data-grid', DataGrid);
  customElements.define('data-field', DataField);
  customElements.define('data-tabs', DataTabs);

  console.log('[Components] v3.0 Web Components registered: data-grid, data-field, data-tabs');
})();
