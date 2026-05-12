// Injected via context.add_init_script() on every page. Walks the DOM
// (including open shadow roots) to extract form-field metadata. Debounces
// on DOM mutations so we get one snapshot per stable step. Pushes back to
// the Python driver via window.__claudePush exposed there.
//
// Privacy contract (#351):
//   - This script NEVER emits user-typed input contents (`.value`,
//     `.innerText`) for inputs/textareas/contenteditable/comboboxes.
//     Capture files would otherwise persist passwords, SSNs, OTPs, etc.
//     in cleartext on disk.
//   - For radio/select options, only `value` + `label` (form-author-
//     supplied option metadata, visible on the page) are emitted. The
//     user's current selection (`checked` / `selected`) is intentionally
//     omitted — it reveals user choices on sensitive forms (EEO,
//     veteran status, disability disclosure, etc.).
//   - The matcher consumes only `label` + `type`; nothing in
//     `job_apply_kit` reads user-typed contents, so this stripping is
//     a zero-behavior-change privacy fix.

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
        // Privacy: `value` and `label` are form-author-supplied (visible
        // on the page); `r.checked` would reveal which option the user
        // picked, so we omit it. See header.
        const opts = group.map((r) => ({
          value: r.value,
          label: labelOf(r),
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
        // Privacy: same posture as radio above — emit form-author option
        // metadata (`value`, `label`) but omit `o.selected` so we don't
        // record the user's current selection.
        opts = [...el.options].map((o) => ({
          value: o.value,
          label: o.text,
        }));
      }

      const fieldType =
        el.tagName === 'SELECT' ? 'select'
        : el.tagName === 'TEXTAREA' ? 'textarea'
        : el.contentEditable === 'true' ? 'contenteditable'
        : type || el.getAttribute('role') || el.tagName.toLowerCase();

      // Privacy: NO `value` / `innerText` capture for inputs / textareas /
      // contenteditable / comboboxes — see header. The matcher operates on
      // labels and structural metadata only.
      fields.push({
        label: labelOf(el),
        type: fieldType,
        name: el.name || '',
        id: el.id || '',
        autocomplete: el.autocomplete || '',
        placeholder: el.placeholder || '',
        required: !!el.required || el.getAttribute('aria-required') === 'true',
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
