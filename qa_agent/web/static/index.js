// Show/hide explore section based on mode
document.querySelectorAll('input[name="mode"]').forEach(radio => {
  radio.addEventListener('change', () => {
    document.getElementById('explore-section').style.display =
      document.querySelector('input[name="mode"]:checked').value === 'explore' ? '' : 'none';
  });
});

// Screenshot dependency logic (mirrors CLI coupling):
//   on_error and full_page require screenshots_enabled
//   on_interaction requires on_error  (matches --screenshots-all behaviour)
(function () {
  const ssEnabled    = document.getElementById('ss_enabled');
  const ssOnError    = document.getElementById('ss_on_error');
  const ssOnInteract = document.getElementById('ss_on_interaction');
  const ssFullPage   = document.getElementById('ss_full_page');

  function syncScreenshots() {
    const enabled = ssEnabled.checked;
    const onError = ssOnError.checked;

    ssOnError.disabled    = !enabled;
    ssFullPage.disabled   = !enabled;
    ssOnInteract.disabled = !enabled || !onError;

    if (!enabled) {
      ssOnError.checked    = false;
      ssFullPage.checked   = false;
      ssOnInteract.checked = false;
    }
    if (!onError) {
      ssOnInteract.checked = false;
    }
  }

  ssEnabled.addEventListener('change', syncScreenshots);
  ssOnError.addEventListener('change', syncScreenshots);
  syncScreenshots();
})();

// LLM provider → model options + env-var hint
(function () {
  const MODELS = {
    anthropic: [
      { value: '',                          label: 'Default (claude-sonnet-4-6)' },
      { value: 'claude-sonnet-4-6',         label: 'claude-sonnet-4-6' },
      { value: 'claude-opus-4-6',           label: 'claude-opus-4-6' },
      { value: 'claude-haiku-4-5-20251001', label: 'claude-haiku-4-5-20251001' },
    ],
    openai: [
      { value: '',            label: 'Default (gpt-4o)' },
      { value: 'gpt-4o',      label: 'gpt-4o' },
      { value: 'gpt-4o-mini', label: 'gpt-4o-mini' },
      { value: 'gpt-4-turbo', label: 'gpt-4-turbo' },
      { value: 'o1',          label: 'o1' },
      { value: 'o1-mini',     label: 'o1-mini' },
    ],
  };
  const KEY_HINTS = {
    anthropic: 'Requires <code>ANTHROPIC_API_KEY</code>',
    openai:    'Requires <code>OPENAI_API_KEY</code>',
  };

  function updateLLMOptions() {
    const provider = document.getElementById('llm_provider').value;
    const modelSel = document.getElementById('ai_model');
    const hint     = document.getElementById('llm_key_hint');
    const models   = MODELS[provider] || [];

    modelSel.innerHTML = models
      .map(m => `<option value="${m.value}">${m.label}</option>`)
      .join('');

    if (hint) hint.innerHTML = KEY_HINTS[provider] || '';
  }

  document.getElementById('llm_provider').addEventListener('change', updateLLMOptions);
  updateLLMOptions();
})();

// Load instructions from a local text/markdown file into the textarea
document.getElementById('instructions_file')?.addEventListener('change', function () {
  const file = this.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('instructions').value = e.target.result;
  };
  reader.readAsText(file);
  this.value = '';
});
