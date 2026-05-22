// Toggle finding detail rows
document.querySelectorAll('.finding-row').forEach(row => {
  row.addEventListener('click', () => {
    const detail = row.querySelector('.finding-detail');
    if (detail) detail.style.display = detail.style.display === 'none' ? '' : 'none';
  });
});

// Re-run with same config: pre-fill form on index page
(function () {
  const configEl = document.getElementById('session-config-data');
  if (!configEl) return;
  const config = JSON.parse(configEl.textContent);
  document.getElementById('rerun-btn').addEventListener('click', e => {
    e.preventDefault();
    if (config.urls && config.urls.length) {
      sessionStorage.setItem('qa_rerun_config', JSON.stringify(config));
      window.location.href = '/';
    }
  });
}());
