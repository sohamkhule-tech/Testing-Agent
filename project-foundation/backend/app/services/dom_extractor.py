"""
DOM Element Extractor

Reusable extraction helpers that extract structured metadata from DOM elements
on a Playwright page. Each function runs in-browser via page.evaluate() and
returns clean, serializable dicts that map directly to the CrawlPackage schemas.

Visibility filtering, label association, and bounding rect capture are built in.
"""

from uuid import UUID

from playwright.async_api import Page

_EXTRACT_ALL_JS = """
() => {
  const extractLabel = (el) => {
    const id = el.id || el.getAttribute('name');
    if (id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (lbl) return lbl.textContent.replace(/\\s+/g, ' ').trim();
    }
    const parent = el.closest('label');
    if (parent) return parent.textContent.replace(/\\s+/g, ' ').trim();
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const placeholder = el.getAttribute('placeholder');
    if (placeholder) return placeholder.trim();
    return null;
  };

  const isVisible = (el) => {
    if (el.offsetParent === null && el !== document.body) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none') return false;
    if (style.visibility === 'hidden') return false;
    const opacity = parseFloat(style.opacity);
    if (opacity === 0) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return false;
    return true;
  };

  const getRect = (el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) };
  };

  const getFormMethod = (el) => {
    const m = (el.method || 'get').toUpperCase();
    if (m === 'POST' || m === 'GET' || m === 'DIALOG') return m;
    return 'GET';
  };

  /* ---- inputs (all except hidden/submit/button/file) ---- */
  const inputs = [];
  const inputEls = document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=file]), select, textarea');
  inputEls.forEach((el) => {
    const label = extractLabel(el);
    const visible = isVisible(el);
    const tag = el.tagName.toLowerCase();
    const inputType = tag === 'select' ? 'select' : tag === 'textarea' ? 'textarea' : (el.type || 'text');
    const rect = visible ? getRect(el) : null;
    inputs.push({
      inputType,
      name: el.name || null,
      label,
      placeholder: el.placeholder || null,
      required: el.required || false,
      disabled: el.disabled || false,
      readonly: el.readOnly || false,
      maxLength: el.maxLength > 0 ? el.maxLength : null,
      minLength: el.minLength > 0 ? el.minLength : null,
      autocomplete: el.autocomplete || null,
      id: el.id || null,
      visible,
      boundingBox: rect,
    });
  });

  /* ---- buttons ---- */
  const buttons = [];
  const btnEls = document.querySelectorAll('button, input[type=submit], input[type=button], a[role=button]');
  const seenButtons = new Set();
  btnEls.forEach((el) => {
    const tag = el.tagName.toLowerCase();
    const text = (el.textContent || el.value || '').replace(/\\s+/g, ' ').trim() || null;
    const key = text || el.id || Math.random();
    if (seenButtons.has(key)) return;
    seenButtons.add(key);
    const label = extractLabel(el);
    const visible = isVisible(el);
    buttons.push({
      text: text || label,
      buttonType: (el.type || 'button').toLowerCase(),
      disabled: el.disabled || false,
      id: el.id || null,
      ariaLabel: el.getAttribute('aria-label') || null,
      role: el.getAttribute('role') || null,
      visible,
      boundingBox: visible ? getRect(el) : null,
    });
  });

  /* ---- checkboxes ---- */
  const checkboxes = [];
  document.querySelectorAll('input[type=checkbox]').forEach((el) => {
    checkboxes.push({
      name: el.name || null,
      label: extractLabel(el),
      checked: el.checked || false,
      required: el.required || false,
      disabled: el.disabled || false,
      visible: isVisible(el),
    });
  });

  /* ---- radio buttons ---- */
  const radios = [];
  document.querySelectorAll('input[type=radio]').forEach((el) => {
    radios.push({
      name: el.name || null,
      label: extractLabel(el),
      value: el.value || null,
      checked: el.checked || false,
      visible: isVisible(el),
    });
  });

  /* ---- dropdowns / select ---- */
  const dropdowns = [];
  document.querySelectorAll('select').forEach((el) => {
    const label = extractLabel(el);
    const visible = isVisible(el);
    dropdowns.push({
      name: el.name || null,
      label,
      options: Array.from(el.options).map((o) => o.text).filter(Boolean),
      multiple: el.multiple || false,
      disabled: el.disabled || false,
      required: el.required || false,
      visible,
    });
  });

  /* ---- forms ---- */
  const forms = [];
  document.querySelectorAll('form').forEach((el) => {
    const rect = getRect(el);
    const visible = isVisible(el);
    const id = el.id || null;
    const name = el.name || el.getAttribute('name') || null;
    forms.push({
      id,
      name,
      action: el.action || null,
      method: getFormMethod(el),
      autocomplete: el.autocomplete || null,
      visible,
      boundingBox: visible ? rect : null,
      label: extractLabel(el) || id || name || null,
    });
  });

  /* ---- tables ---- */
  const tables = [];
  document.querySelectorAll('table').forEach((el) => {
    const visible = isVisible(el);
    const caption = el.querySelector('caption');
    const headers = [];
    el.querySelectorAll('th').forEach((th) => {
      const txt = th.textContent.replace(/\\s+/g, ' ').trim();
      if (txt) headers.push(txt);
    });
    const rows = el.querySelectorAll('tr').length;
    const cols = el.querySelectorAll('tr:first-child th, tr:first-child td').length;
    tables.push({
      id: el.id || null,
      caption: caption ? caption.textContent.replace(/\\s+/g, ' ').trim() : null,
      headers,
      rowCount: Math.max(0, rows - (caption ? 1 : 0)),
      columnCount: cols,
      visible,
      boundingBox: visible ? getRect(el) : null,
    });
  });

  /* ---- dialogs / modals ---- */
  const dialogs = [];
  document.querySelectorAll('dialog, [role=dialog], [aria-modal=true]').forEach((el) => {
    const visible = isVisible(el);
    const title = (el.querySelector('[role=heading]') || el.querySelector('h1, h2, h3, h4')).textContent.replace(/\\s+/g, ' ').trim();
    dialogs.push({
      dialogType: el.tagName.toLowerCase() === 'dialog' ? 'modal' : 'modal',
      title: title || el.getAttribute('aria-label') || null,
      message: null,
      triggerElement: null,
      visible,
    });
  });

  /* ---- uploads / input[type=file] ---- */
  const uploads = [];
  document.querySelectorAll('input[type=file]').forEach((el) => {
    uploads.push({
      name: el.name || null,
      label: extractLabel(el),
      accept: el.accept ? el.accept.split(',').map((s) => s.trim()).filter(Boolean) : [],
      multiple: el.multiple || false,
      required: el.required || false,
      disabled: el.disabled || false,
      visible: isVisible(el),
    });
  });

  return { inputs, buttons, checkboxes, radios, dropdowns, forms, tables, dialogs, uploads };
}
"""


async def extract_all(page: Page) -> dict:
    """
    Extract all DOM element types from a page in a single browser call.

    Returns:
        dict with keys: inputs, buttons, checkboxes, radios, dropdowns,
                        forms, tables, dialogs, uploads
    """
    result = await page.evaluate(_EXTRACT_ALL_JS)
    return result
