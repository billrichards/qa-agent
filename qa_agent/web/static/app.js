/* QA Agent – client-side JS */
'use strict';

// ── Form submission ────────────────────────────────────────────────────────────
(function () {
  const form = document.getElementById('run-form');
  if (!form) return;

  // Render viewport presets from the server registry, so the checkbox list
  // never drifts from the presets the backend actually accepts.
  loadViewportPresets();

  // Apply rerun config from session storage if present
  const rerunConfig = sessionStorage.getItem('qa_rerun_config');
  if (rerunConfig) {
    sessionStorage.removeItem('qa_rerun_config');
    try { applyConfig(JSON.parse(rerunConfig)); } catch (_) {}
  }

  // Load presets from localStorage into dropdown
  populatePresets();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('[type=submit]');
    const errEl = document.getElementById('form-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Starting…';

    const body = collectFormData(form);
    if (!body.urls.length) {
      errEl.textContent = 'Please enter at least one URL.';
      errEl.style.display = '';
      btn.disabled = false;
      btn.textContent = 'Run Test';
      return;
    }

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start test');
      window.location.href = '/run/' + data.job_id;
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = '';
      btn.disabled = false;
      btn.textContent = 'Run Test';
    }
  });

  document.getElementById('save-preset-btn')?.addEventListener('click', () => {
    const name = prompt('Preset name:');
    if (!name) return;
    const presets = getPresets();
    presets[name] = collectFormData(form);
    savePresets(presets);
    populatePresets();
  });

  document.getElementById('preset-select')?.addEventListener('change', function () {
    const presets = getPresets();
    if (this.value && presets[this.value]) {
      applyConfig(presets[this.value]);
    }
    this.value = '';
  });

  document.getElementById('reset-btn')?.addEventListener('click', () => {
    form.reset();
    document.getElementById('explore-section').style.display = 'none';
  });

  document.getElementById('export-config-btn')?.addEventListener('click', () => {
    const cfg = collectFormData(form);
    const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'qa-agent-config.json';
    a.click();
    URL.revokeObjectURL(a.href);
  });

  document.getElementById('import-config-input')?.addEventListener('change', function () {
    const file = this.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
      try {
        applyConfig(JSON.parse(e.target.result));
      } catch (_) {
        alert('Invalid config file.');
      }
    };
    reader.readAsText(file);
    this.value = '';
  });
})();


// ── Collect form data into API request body ────────────────────────────────────
function collectFormData(form) {
  const fd = new FormData(form);

  const urlsRaw = (fd.get('urls') || '').split('\n').map(u => u.trim()).filter(Boolean);
  const mode = fd.get('mode') || 'focused';

  const outputFormats = fd.getAll('output_formats');

  return {
    urls: urlsRaw,
    mode,
    output_formats: outputFormats.length ? outputFormats : ['console', 'markdown', 'json'],
    output_dir: fd.get('output_dir') || null,
    headless: !!fd.get('headless'),
    workers: parseInt(fd.get('workers') || '1', 10),
    viewports: collectViewports(fd),
    timeout: parseInt(fd.get('timeout') || '30000', 10),
    max_depth: parseInt(fd.get('max_depth') || '3', 10),
    max_pages: parseInt(fd.get('max_pages') || '100', 10),
    max_interactions_per_page: parseInt(fd.get('max_interactions_per_page') || '50', 10),
    test_keyboard: !!fd.get('test_keyboard'),
    test_mouse: !!fd.get('test_mouse'),
    test_forms: !!fd.get('test_forms'),
    test_accessibility: !!fd.get('test_accessibility'),
    test_console_errors: !!fd.get('test_console_errors'),
    test_network_errors: !!fd.get('test_network_errors'),
    test_wcag_compliance: !!fd.get('test_wcag_compliance'),
    same_domain_only: !!fd.get('same_domain_only'),
    ignore_patterns: (fd.get('ignore_patterns') || '').split('\n').map(s => s.trim()).filter(Boolean),
    instructions: fd.get('instructions') || null,
    ai_model: fd.get('ai_model') || 'claude-sonnet-4-6',
    use_plan_cache: !!fd.get('use_plan_cache'),
    screenshots: {
      enabled: !!fd.get('screenshots_enabled'),
      on_error: !!fd.get('screenshots_on_error'),
      on_interaction: !!fd.get('screenshots_on_interaction'),
      full_page: !!fd.get('screenshots_full_page'),
    },
    recording: {
      enabled: !!fd.get('recording_enabled'),
    },
    auth: {
      auth_url: fd.get('auth_url') || null,
      username: fd.get('auth_username') || null,
      password: fd.get('auth_password') || null,
      username_selector: fd.get('auth_username_selector') || null,
      password_selector: fd.get('auth_password_selector') || null,
      submit_selector: fd.get('auth_submit_selector') || null,
      cookies: fd.get('auth_cookies') || null,
      headers: fd.get('auth_headers') || null,
    },
  };
}


// ── Viewports ──────────────────────────────────────────────────────────────────

// A config may be restored before the async preset fetch resolves; hold the
// selection here and apply it once the checkboxes exist.
let _pendingViewports = null;

async function loadViewportPresets() {
  const container = document.getElementById('viewport-presets');
  if (!container) return;

  let presets = [];
  try {
    const res = await fetch('/api/viewports');
    if (res.ok) presets = (await res.json()).presets || [];
  } catch (_) {
    // Leave the list empty; custom sizes and the default still work.
  }

  container.innerHTML = '';
  for (const vp of presets) {
    const label = document.createElement('label');
    label.className = 'check-label';

    const input = document.createElement('input');
    input.type = 'checkbox';
    input.name = 'viewport_preset';
    input.value = vp.name;

    const text = document.createElement('span');
    text.textContent = ` ${vp.name} (${vp.width}\u00d7${vp.height})`;

    label.append(input, text);
    if (vp.description) label.title = vp.description;
    container.appendChild(label);
  }

  if (_pendingViewports) {
    const pending = _pendingViewports;
    _pendingViewports = null;
    applyViewports(pending);
  }
}

function collectViewports(fd) {
  // Preset names first, then any custom sizes typed alongside them.
  const names = fd.getAll('viewport_preset');
  const custom = (fd.get('viewport_custom') || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  // An empty list makes the server fall back to a single default viewport,
  // which is what an untouched form should do.
  return names.concat(custom);
}

function applyViewports(cfg) {
  const form = document.getElementById('run-form');
  if (!form) return;

  // Accept both the new list and the legacy scalar pair from older saved configs.
  let names = cfg.viewports;
  if (!names || !names.length) {
    if (cfg.viewport_width && cfg.viewport_height) {
      names = [`${cfg.viewport_width}x${cfg.viewport_height}`];
    } else {
      return;
    }
  }
  names = names.map((v) => (typeof v === 'string' ? v : v && v.name)).filter(Boolean);

  const boxes = form.querySelectorAll('input[name="viewport_preset"]');
  if (!boxes.length) {
    _pendingViewports = cfg;  // presets not rendered yet
    return;
  }

  const known = new Set();
  boxes.forEach((box) => {
    box.checked = names.includes(box.value);
    known.add(box.value);
  });

  // Anything that is not a preset goes back into the custom field.
  const customEl = form.querySelector('#viewport_custom');
  if (customEl) customEl.value = names.filter((n) => !known.has(n)).join(', ');
}


// ── Apply a config object back to the form ─────────────────────────────────────
function applyConfig(cfg) {
  const form = document.getElementById('run-form');
  if (!form) return;

  if (cfg.urls) form.querySelector('#urls').value = cfg.urls.join('\n');
  if (cfg.mode) {
    const radio = form.querySelector(`input[name="mode"][value="${cfg.mode}"]`);
    if (radio) {
      radio.checked = true;
      document.getElementById('explore-section').style.display =
        cfg.mode === 'explore' ? '' : 'none';
    }
  }
  setCheck(form, 'headless', cfg.headless !== false);
  setNum(form, 'workers', cfg.workers);
  applyViewports(cfg);
  setNum(form, 'timeout', cfg.timeout);
  setNum(form, 'max_depth', cfg.max_depth);
  setNum(form, 'max_pages', cfg.max_pages);
  const outputDirEl = form.querySelector('#output_dir');
  if (outputDirEl && cfg.output_dir) outputDirEl.value = cfg.output_dir;
}

function setCheck(form, name, val) {
  const el = form.querySelector(`[name="${name}"]`);
  if (el) el.checked = !!val;
}

function setNum(form, name, val) {
  const el = form.querySelector(`[name="${name}"]`);
  if (el && val !== undefined) el.value = val;
}


// ── Preset storage (localStorage) ─────────────────────────────────────────────
function getPresets() {
  try { return JSON.parse(localStorage.getItem('qa_presets') || '{}'); } catch (_) { return {}; }
}

function savePresets(presets) {
  localStorage.setItem('qa_presets', JSON.stringify(presets));
}

function populatePresets() {
  const sel = document.getElementById('preset-select');
  if (!sel) return;
  const presets = getPresets();
  const names = Object.keys(presets);
  // Remove old preset options (keep first placeholder option)
  while (sel.options.length > 1) sel.remove(1);
  names.forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  });
  sel.style.display = names.length ? '' : 'none';
}
