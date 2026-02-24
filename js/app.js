/**
 * App modulare: download YouTube → portrait 9:16 con zoom e anteprima.
 * L'anteprima funziona subito: incolla il link e clicca "Genera anteprima" (senza scaricare prima).
 */

/* ===== Costanti ===== */
const POLL_INTERVAL_MS = 400;
const ZOOM_MIN = 0;
const ZOOM_MAX = 30;
const ZOOM_DEFAULT = 7;

/* ===== Riferimenti DOM (valorizzati in init) ===== */
let refs = {};

/* ===== Stato UI ===== */
function getZoom() {
  const z = parseFloat(refs.zoomInput.value);
  return Number.isFinite(z) ? Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z)) : ZOOM_DEFAULT;
}

function setStatus(text, type = '') {
  refs.status.textContent = text;
  refs.status.className = 'status ' + type;
}

function setProgressVisible(visible) {
  refs.progressWrap.classList.toggle('visible', !!visible);
}

function setProgressPercent(percent) {
  const p = Math.min(100, Math.max(0, percent));
  refs.progressBar.style.width = p + '%';
}

/* ===== API ===== */
async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (_) {}
  }
  return { res, data };
}

async function apiGet(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

/* ===== Download: avvio e polling ===== */
async function startDownload() {
  const url = refs.urlInput.value.trim();
  if (!url) {
    setStatus('Inserisci un link YouTube.', 'error');
    return;
  }

  refs.btnDownload.disabled = true;
  setProgressPercent(0);
  setStatus('Avvio…', 'loading');
  setProgressVisible(true);

  const { res, data } = await apiPost('/api/download', { url, zoom: getZoom() });

  if (!res.ok || !data.ok || !data.job_id) {
    const msg = data.error || (res.ok ? 'Errore durante l\'avvio.' : `Errore ${res.status}: ${res.statusText || 'server non raggiungibile'}. Avvia il server: python app.py`);
    setStatus(msg, 'error');
    refs.btnDownload.disabled = false;
    setProgressVisible(false);
    setProgressPercent(0);
    return;
  }

  await runPolling(data.job_id);
  refs.btnDownload.disabled = false;
  setProgressVisible(false);
  setProgressPercent(0);
}

function runPolling(jobId) {
  return new Promise((resolve) => {
    let pollId = null;

    const poll = async () => {
      try {
        const { res, data: s } = await apiGet('/api/status/' + jobId);
        setProgressPercent(s.progress ?? 0);
        setStatus(s.stage || '…', 'loading');

        if (s.done) {
          if (pollId) clearInterval(pollId);
          if (s.error) {
            setStatus(s.error, 'error');
            resolve();
            return;
          }
          if (s.download_url) {
            setStatus('Download file…', 'loading');
            const fileRes = await fetch(s.download_url);
            if (!fileRes.ok) {
              setStatus('Errore nel recupero del file.', 'error');
              resolve();
              return;
            }
            const blob = await fileRes.blob();
            const name = fileRes.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1] || 'video_portrait.mp4';
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = name;
            a.click();
            URL.revokeObjectURL(a.href);
            setProgressPercent(100);
            setStatus('Completato.', 'success');
          }
          resolve();
        }
      } catch (_) {
        if (pollId) clearInterval(pollId);
        setStatus('Errore di connessione. Riprova.', 'error');
        resolve();
      }
    };

    poll();
    pollId = setInterval(poll, POLL_INTERVAL_MS);
  });
}

/* ===== Anteprima (funziona subito: solo link + pulsante, senza scaricare prima) ===== */
async function handlePreview() {
  if (!refs.urlInput || !refs.btnPreview || !refs.previewPlaceholder || !refs.previewImg) return;
  const url = refs.urlInput.value.trim();
  if (!url) {
    setStatus('Inserisci un link YouTube sopra, poi clicca «Genera anteprima».', 'error');
    return;
  }

  refs.btnPreview.disabled = true;
  refs.previewPlaceholder.style.display = '';
  refs.previewPlaceholder.textContent = 'Scarico il video per l\'anteprima… (attendi qualche secondo)';
  refs.previewImg.style.display = 'none';
  refs.previewImg.onerror = null;
  setStatus('Preparazione anteprima…', 'loading');

  try {
    const res = await fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, zoom: getZoom() }),
      cache: 'no-store',
    });

    const contentType = (res.headers.get('content-type') || '').toLowerCase();

    if (!res.ok) {
      const data = contentType.includes('application/json')
        ? await res.json().catch(() => ({}))
        : {};
      const msg = data.error || `Errore ${res.status}: ${res.statusText || 'anteprima non disponibile'}`;
      refs.previewPlaceholder.textContent = msg;
      setStatus(msg, 'error');
      return;
    }

    if (!contentType.includes('image/')) {
      const text = await res.text();
      let msg = 'Risposta non valida dal server.';
      try {
        const data = JSON.parse(text);
        if (data && data.error) msg = data.error;
      } catch (_) {}
      refs.previewPlaceholder.textContent = msg;
      setStatus(msg, 'error');
      return;
    }

    const blob = await res.blob();
    if (refs.previewImg.src) {
      URL.revokeObjectURL(refs.previewImg.src);
    }
    refs.previewImg.removeAttribute('src');
    refs.previewImg.onload = () => URL.revokeObjectURL(refs.previewImg.src);
    refs.previewImg.onerror = () => {
      URL.revokeObjectURL(refs.previewImg.src);
      refs.previewPlaceholder.style.display = '';
      refs.previewPlaceholder.textContent = 'Errore nel mostrare l\'immagine. Riprova.';
      setStatus('Errore immagine anteprima.', 'error');
      refs.btnPreview.disabled = false;
    };
    const objectUrl = URL.createObjectURL(blob);
    refs.previewImg.src = objectUrl;
    refs.previewImg.style.display = 'block';
    refs.previewPlaceholder.style.display = 'none';
    setStatus('Anteprima pronta. Puoi cambiare zoom e rigenerare, oppure scaricare.', 'success');
  } catch (e) {
    refs.previewPlaceholder.style.display = '';
    refs.previewPlaceholder.textContent = 'Errore di connessione. Controlla che il server sia avviato (python app.py) e riprova.';
    setStatus('Errore di connessione.', 'error');
  } finally {
    refs.btnPreview.disabled = false;
  }
}

/* ===== Init ===== */
function init() {
  refs = {
    urlInput: document.getElementById('url'),
    btnDownload: document.getElementById('btnDownload'),
    status: document.getElementById('status'),
    progressWrap: document.getElementById('progressWrap'),
    progressBar: document.getElementById('progressBar'),
    zoomInput: document.getElementById('zoom'),
    btnPreview: document.getElementById('btnPreview'),
    previewPlaceholder: document.getElementById('previewPlaceholder'),
    previewImg: document.getElementById('previewImg'),
  };
  if (!refs.urlInput || !refs.btnDownload || !refs.btnPreview) return;

  refs.btnDownload.addEventListener('click', () => {
    startDownload().catch((e) => {
      setStatus((e && e.message) || 'Errore.', 'error');
    });
  });

  refs.urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') refs.btnDownload.click();
  });

  refs.btnPreview.addEventListener('click', handlePreview);

  refs.zoomInput.addEventListener('change', () => {
    const v = getZoom();
    if (Number(refs.zoomInput.value) !== v) refs.zoomInput.value = v;
  });
  refs.zoomInput.addEventListener('input', () => {
    const v = getZoom();
    if (Number(refs.zoomInput.value) !== v) refs.zoomInput.value = v;
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
