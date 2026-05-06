/**
 * dashboard.js
 * Handles:
 * 1. WebRTC connection to /offer -> live video in <video>
 * 2. WebSocket connection to /ws/plates -> live plate results
 * 3. Canvas overlay for bounding boxes
 * 4. Detection log table updates
 * 5. Health polling for stream status badge
 */

const video      = document.getElementById('live-feed');
const canvas     = document.getElementById('overlay');
const ctx        = canvas.getContext('2d');
const noSignal   = document.getElementById('no-signal');
const plateText  = document.getElementById('plate-text');
const plateTime  = document.getElementById('plate-time');
const plateConf  = document.getElementById('plate-conf');
const logBody    = document.getElementById('log-body');
const streamBadge = document.getElementById('stream-status');
const detectBadge = document.getElementById('detection-status');

const HOST = window.location.hostname;
const WS_URL = `ws://${HOST}:8000/ws/plates`;
const OFFER_URL = `http://${HOST}:8000/offer`;
const HEALTH_URL = `http://${HOST}:8000/health`;

// ── WebRTC ─────────────────────────────────────────────────────────────────

let pc = null;

async function startWebRTC() {
  pc = new RTCPeerConnection({
    iceServers: []  // LAN only — no STUN/TURN needed
  });

  pc.ontrack = (event) => {
    if (event.track.kind === 'video') {
      video.srcObject = event.streams[0];
      video.onloadedmetadata = () => {
        noSignal.classList.add('hidden');
        updateStreamBadge(true);
      };
    }
  };

  pc.oniceconnectionstatechange = () => {
    if (['failed', 'disconnected', 'closed'].includes(pc.iceConnectionState)) {
      updateStreamBadge(false);
      noSignal.classList.remove('hidden');
      setTimeout(startWebRTC, 3000);  // auto reconnect
    }
  };

  // Add a transceiver to receive video
  pc.addTransceiver('video', { direction: 'recvonly' });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  // Wait for ICE gathering to complete
  await new Promise(resolve => {
    if (pc.iceGatheringState === 'complete') return resolve();
    pc.onicegatheringstatechange = () => {
      if (pc.iceGatheringState === 'complete') resolve();
    };
    setTimeout(resolve, 2000); // safety timeout
  });

  try {
    const res = await fetch(OFFER_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sdp: pc.localDescription.sdp,
        type: pc.localDescription.type
      })
    });
    const answer = await res.json();
    await pc.setRemoteDescription(new RTCSessionDescription(answer));
  } catch (e) {
    console.error('[WebRTC] Offer failed:', e);
    setTimeout(startWebRTC, 3000);
  }
}

// ── WebSocket ──────────────────────────────────────────────────────────────

function startWebSocket() {
  const ws = new WebSocket(WS_URL);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleDetection(data);
  };

  ws.onclose = () => {
    setTimeout(startWebSocket, 3000); // auto reconnect
  };

  ws.onerror = () => ws.close();
}

// ── Detection Handler ──────────────────────────────────────────────────────

function handleDetection(data) {
  // Update last plate panel
  plateText.textContent = data.plate || '---';
  plateTime.textContent = data.timestamp || '';
  plateConf.textContent = data.confidence ? `Confidence: ${(data.confidence * 100).toFixed(0)}%` : '';

  // Flash effect
  plateText.classList.remove('flash');
  void plateText.offsetWidth;
  plateText.classList.add('flash');

  // Update detection status badge
  detectBadge.textContent = `Detection: Active`;
  detectBadge.className = 'badge badge--success';

  // Draw bounding box on canvas
  if (data.bbox) drawBBox(data.bbox);

  // Add row to log table
  addLogRow(data);
}

function drawBBox(bbox) {
  const [x1, y1, x2, y2] = bbox;
  const scaleX = canvas.clientWidth  / 1280;
  const scaleY = canvas.clientHeight / 720;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = '#f5c518';
  ctx.lineWidth = 2.5;
  ctx.strokeRect(
    x1 * scaleX, y1 * scaleY,
    (x2 - x1) * scaleX,
    (y2 - y1) * scaleY
  );

  // Label above box
  ctx.fillStyle = '#f5c518';
  ctx.font = 'bold 14px monospace';
  ctx.fillText('PLATE', x1 * scaleX, (y1 * scaleY) - 6);

  // Fade the box after 2 seconds
  setTimeout(() => ctx.clearRect(0, 0, canvas.width, canvas.height), 2000);
}

function addLogRow(data) {
  // Remove empty-state row if present
  const empty = logBody.querySelector('.empty-row');
  if (empty) empty.closest('tr').remove();

  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td>${data.plate}</td>
    <td>${data.confidence ? (data.confidence * 100).toFixed(0) + '%' : '-'}</td>
    <td>${data.timestamp ? data.timestamp.split(' ')[1] : ''}</td>
  `;
  logBody.prepend(tr);

  // Keep log to 50 rows max
  while (logBody.rows.length > 50) logBody.deleteRow(logBody.rows.length - 1);
}

// ── Health Polling ─────────────────────────────────────────────────────────

function updateStreamBadge(connected) {
  streamBadge.textContent = connected ? 'Stream: Live' : 'Stream: Offline';
  streamBadge.className   = connected ? 'badge badge--success' : 'badge badge--error';
}

async function pollHealth() {
  try {
    const res  = await fetch(HEALTH_URL);
    const data = await res.json();
    updateStreamBadge(data.stream_connected);
  } catch { updateStreamBadge(false); }
}

// ── Theme Toggle ───────────────────────────────────────────────────────────

(function() {
  const btn = document.querySelector('[data-theme-toggle]');
  const html = document.documentElement;
  btn && btn.addEventListener('click', () => {
    const t = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', t);
    btn.textContent = t === 'dark' ? '\u263E' : '\u2600\uFE0F';
  });
})();

// ── Init ───────────────────────────────────────────────────────────────────

startWebRTC();
startWebSocket();
setInterval(pollHealth, 5000);
