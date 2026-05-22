(function () {
  const JOB_ID = document.getElementById('run-header').dataset.jobId;
  const log = document.getElementById('log');
  const statusBadge = document.getElementById('status-badge');
  const stopBtn = document.getElementById('stop-btn');
  const statsEl = document.getElementById('run-stats');
  const statPages = document.getElementById('stat-pages');
  const statFindings = document.getElementById('stat-findings');
  const statUrl = document.getElementById('stat-url');
  const completeBanner = document.getElementById('complete-banner');
  const errorBanner = document.getElementById('error-banner');
  const stoppedBanner = document.getElementById('stopped-banner');
  const autoscroll = document.getElementById('autoscroll');
  let findingCount = 0;
  let pageCount = 0;

  function setStatus(status) {
    statusBadge.className = 'badge badge-' + status;
    statusBadge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    if (status === 'running') {
      stopBtn.style.display = '';
      statsEl.style.display = '';
    }
    if (['completed', 'failed', 'stopped'].includes(status)) {
      stopBtn.style.display = 'none';
    }
  }

  document.getElementById('clear-log-btn').addEventListener('click', () => { log.innerHTML = ''; });

  stopBtn.addEventListener('click', () => {
    stopBtn.disabled = true;
    stopBtn.textContent = 'Stopping after current page…';
    fetch('/api/stop/' + JOB_ID, { method: 'POST' }).catch(() => {});
  });

  // ── Elapsed timer ─────────────────────────────────────────────────────────────
  const statElapsed = document.getElementById('stat-elapsed');
  let startTime = null;
  let elapsedInterval = null;

  function startTimer() {
    if (elapsedInterval) return;
    startTime = Date.now();
    elapsedInterval = setInterval(() => {
      const secs = Math.floor((Date.now() - startTime) / 1000);
      const m = Math.floor(secs / 60);
      const s = secs % 60;
      statElapsed.textContent = m + ':' + String(s).padStart(2, '0');
    }, 1000);
  }

  function stopTimer() {
    if (elapsedInterval) {
      clearInterval(elapsedInterval);
      elapsedInterval = null;
    }
  }

  // ── Log filtering ─────────────────────────────────────────────────────────────
  let activeFilter = 'all';

  function lineMatchesFilter(line, filter) {
    if (filter === 'all') return true;
    if (filter === 'finding') return line.classList.contains('log-finding');
    if (filter === 'error') return line.classList.contains('log-error') || (line.classList.contains('log-finding') && line.classList.contains('log-critical')) || (line.classList.contains('log-finding') && line.classList.contains('log-high'));
    return true;
  }

  document.querySelectorAll('.log-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      activeFilter = btn.dataset.filter;
      document.querySelectorAll('.log-filter').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      log.querySelectorAll('.log-line').forEach(line => {
        line.style.display = lineMatchesFilter(line, activeFilter) ? '' : 'none';
      });
      if (autoscroll.checked) log.scrollTop = log.scrollHeight;
    });
  });

  function appendLog(msg, cls) {
    const line = document.createElement('div');
    line.className = 'log-line' + (cls ? ' ' + cls : '');
    line.textContent = msg;
    line.style.display = lineMatchesFilter(line, activeFilter) ? '' : 'none';
    log.appendChild(line);
    if (autoscroll.checked && line.style.display !== 'none') log.scrollTop = log.scrollHeight;
  }

  // ── SSE stream ────────────────────────────────────────────────────────────────
  // Pre-check actual job status before opening SSE — the job may still be queued
  // or may have already finished if the user is loading a page for an old job.
  function startStream() {
    const es = new EventSource('/api/stream/' + JOB_ID);
    startTimer();

    es.addEventListener('log', e => {
      const data = JSON.parse(e.data);
      appendLog(data.message);
    });

    es.addEventListener('progress', e => {
      const data = JSON.parse(e.data);
      pageCount++;
      statPages.textContent = pageCount;
      statUrl.textContent = data.url || '';
      appendLog(data.message, 'log-progress');
    });

    es.addEventListener('finding', e => {
      const data = JSON.parse(e.data);
      findingCount++;
      statFindings.textContent = findingCount;
      appendLog('[' + data.severity.toUpperCase() + '] ' + data.title, 'log-finding log-' + data.severity);
    });

    es.addEventListener('complete', e => {
      const data = JSON.parse(e.data);
      es.close();
      stopTimer();
      setStatus(data.status || 'completed');
      statFindings.textContent = data.total_findings || findingCount;
      if (data.status === 'stopped') {
        stoppedBanner.style.display = '';
        if (data.session_id && data.domain) {
          const link = document.getElementById('stopped-link');
          link.href = '/session/' + data.domain + '/' + data.session_id;
          document.getElementById('stopped-session-link').style.display = '';
        }
      } else {
        completeBanner.style.display = '';
        if (data.session_id && data.domain) {
          document.getElementById('session-link').href = '/session/' + data.domain + '/' + data.session_id;
        }
      }
    });

    es.addEventListener('error', e => {
      if (e.data) {
        const data = JSON.parse(e.data);
        es.close();
        stopTimer();
        setStatus('failed');
        errorBanner.style.display = '';
        errorBanner.textContent = 'Error: ' + data.message;
      }
    });

    es.onerror = () => {
      es.close();
      stopTimer();
      fetch('/api/status/' + JOB_ID)
        .then(r => r.json())
        .then(d => {
          setStatus(d.status);
          statFindings.textContent = d.total_findings || findingCount;
          if (d.status === 'completed' && d.session_id) {
            completeBanner.style.display = '';
            document.getElementById('session-link').href = '/session/' + d.domain + '/' + d.session_id;
          } else if (d.status === 'failed') {
            errorBanner.style.display = '';
            errorBanner.textContent = 'Error: ' + (d.error || 'Unknown error');
          }
        })
        .catch(() => appendLog('Connection lost. Refresh to check status.', 'log-error'));
    };
  }

  fetch('/api/status/' + JOB_ID)
    .then(r => r.json())
    .then(d => {
      const finalStates = ['completed', 'stopped', 'failed'];
      setStatus(d.status);
      if (finalStates.includes(d.status)) {
        statFindings.textContent = d.total_findings || 0;
        if (d.status === 'completed' && d.session_id) {
          completeBanner.style.display = '';
          document.getElementById('session-link').href = '/session/' + d.domain + '/' + d.session_id;
        } else if (d.status === 'stopped') {
          stoppedBanner.style.display = '';
          if (d.session_id && d.domain) {
            document.getElementById('stopped-link').href = '/session/' + d.domain + '/' + d.session_id;
            document.getElementById('stopped-session-link').style.display = '';
          }
        } else if (d.status === 'failed') {
          errorBanner.style.display = '';
          errorBanner.textContent = 'Error: ' + (d.error || 'Unknown error');
        }
      } else {
        startStream();
      }
    })
    .catch(() => {
      // Status check failed — fall back to opening SSE directly
      setStatus('running');
      startStream();
    });

}());
