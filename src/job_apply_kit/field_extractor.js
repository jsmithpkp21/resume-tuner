// Injected via context.add_init_script() on every page. Walks the DOM
// (including open shadow roots) to extract form-field metadata. Debounces
// on DOM mutations so we get one snapshot per stable step. Pushes back to
// the Python driver via window.__claudePush exposed there.

(() => {
  if (window.__claudeExtractorInstalled) return;
  window.__claudeExtractorInstalled = true;

  const labelOf = (el) => {
    if (el.id) {
      try {
        const lbl = el.getRootNode().querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lbl) return lbl.innerText.trim();
      } catch (_) { /* ignore */ }
    }
    const labelledby = el.getAttribute && el.getAttribute('aria-labelledby');
    if (labelledby) {
      const id = labelledby.split(/\s+/)[0];
      const e = document.getElementById(id);
      if (e) return e.innerText.trim();
    }
    const al = el.getAttribute && el.getAttribute('aria-label');
    if (al) return al.trim();
    const lp = el.closest && el.closest('label');
    if (lp) return lp.innerText.trim();
    let cur = el;
    for (let i = 0; i < 6 && cur; i++) {
      cur = cur.parentElement;
      if (!cur) break;
      const lg = cur.querySelector && cur.querySelector('legend');
      if (lg) return lg.innerText.trim();
    }
    return (el.placeholder || '').trim();
  };

  function* walk(root) {
    const sel =
      'input,select,textarea,[contenteditable="true"],[role="combobox"],[role="textbox"]';
    if (root.querySelectorAll) {
      for (const n of root.querySelectorAll(sel)) yield n;
      for (const n of root.querySelectorAll('*')) {
        if (n.shadowRoot) yield* walk(n.shadowRoot);
      }
    }
  }

  const extract = () => {
    const fields = [];
    const seenRadios = new Set();
    for (const el of walk(document)) {
      const type = (el.type || '').toLowerCase();
      if (type === 'hidden' || el.disabled) continue;

      if (type === 'radio') {
        const key = el.name || el.id;
        if (seenRadios.has(key)) continue;
        seenRadios.add(key);
        let group = [];
        try {
          group = [...document.querySelectorAll(`input[type="radio"][name="${CSS.escape(el.name)}"]`)];
        } catch (_) { group = [el]; }
        const opts = group.map((r) => ({
          value: r.value,
          label: labelOf(r),
          checked: !!r.checked,
        }));
        fields.push({
          label: labelOf(el),
          type: 'radio-group',
          name: el.name || '',
          required: !!el.required,
          options: opts,
        });
        continue;
      }

      let opts;
      if (el.tagName === 'SELECT') {
        opts = [...el.options].map((o) => ({
          value: o.value,
          label: o.text,
          selected: o.selected,
        }));
      }

      const fieldType =
        el.tagName === 'SELECT' ? 'select'
        : el.tagName === 'TEXTAREA' ? 'textarea'
        : el.contentEditable === 'true' ? 'contenteditable'
        : type || el.getAttribute('role') || el.tagName.toLowerCase();

      fields.push({
        label: labelOf(el),
        type: fieldType,
        name: el.name || '',
        id: el.id || '',
        autocomplete: el.autocomplete || '',
        placeholder: el.placeholder || '',
        required: !!el.required || el.getAttribute('aria-required') === 'true',
        value: el.value !== undefined ? el.value : (el.innerText || '').slice(0, 500),
        options: opts,
      });
    }
    return fields;
  };

  let lastSig = '';
  let timer = null;

  const sigOf = (fields) =>
    JSON.stringify(
      fields.map((f) => [f.label, f.type, (f.options || []).length, !!f.required])
    );

  const emit = () => {
    const fields = extract();
    if (fields.length === 0) return;
    const sig = sigOf(fields);
    if (sig === lastSig) return;
    lastSig = sig;
    if (typeof window.__claudePush === 'function') {
      try {
        window.__claudePush({ url: location.href, ts: Date.now(), fields });
      } catch (_) { /* ignore */ }
    }
  };

  const debounce = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(emit, 1500);
  };

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    debounce();
  } else {
    window.addEventListener('DOMContentLoaded', debounce, { once: true });
  }
  try {
    new MutationObserver(debounce).observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
    });
  } catch (_) { /* ignore */ }
  document.addEventListener('click', () => setTimeout(debounce, 50), true);
})();
