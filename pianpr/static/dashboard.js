/**
 * dashboard.js
 * Handles:
 * 1. WebRTC connection -> live video
 * 2. WebSocket -> live plate results
 * 3. Canvas overlay for bounding boxes
 * 4. Detection log table
 * 5. Live stats bar: FPS, bitrate, ping, data received, packets
 */

const video       = document.getElementById('live-feed');
const canvas      = document.getElementById('overlay');
const ctx         = canvas.getContext('2d');
const noSignal    = document.getElementById('no-signal');
const plateText   = document.getElementById('plate-text');
const plateTime   = document.getElementById('plate-time');
const plateConf   = document.getElementById('plate-conf');
const logBody     = document.getElementById('log-body');
const streamBadge = document.getElementById('stream-status');
const detectBadge = document.getElementById('detection-status');

// Stats elements
const statFps     = document.getElementById('stat-fps');
const statBitrate = document.getElementById('stat-bitrate');
const statPing    = document.getElementById('stat-ping');
const statBytes   = document.getElementById('stat-bytes');
const statPackets = document.getElementById('stat-packets');
const statLost    = document.getElementById('stat-lost');
const statRes     = document.getElementById('stat-res');

const HOST     = window.location.hostname;
const WS_URL   = `ws://${HOST}:8000/ws/plates`;
const OFFER_URL = `http://${HOST}:8000/offer`;

// ── WebRTC ────────────────────────────────────────────────────────────────

let pc = null;
let statsInterval = null;

// Tracks previous stats for delta calculations
let prevStats = { bytes: 0, packets: 0, ts: 0, frames: 0 };

async function startWebRTC() {
  if (pc) { pc.close(); pc = null; }

  pc = new RTCPeerConnection({ iceServers: [] }); // LAN only

  pc.ontrack = (event) => {
    if (event.track.kind === 'video') {
      video.srcObject = event.streams[0];
      video.onloadedmetadata = () => {
        noSignal.classList.add('hidden');
        updateStreamBadge(true);
        syncCanvasSize();
        startStatsPolling();
      };
    }
  };

  pc.oniceconnectionstatechange = () => {
    if (['failed', 'disconnected', 'closed'].includes(pc.iceConnectionState)) {
      updateStreamBadge(false);
      noSignal.classList.remove('hidden');
      stopStatsPolling();
      setTimeout(startWebRTC, 3000);
    }
  };

  pc.addTransceiver('video', { direction: 'recvonly' });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  // Wait for ICE gathering
  await new Promise(resolve => {
    if (pc.iceGatheringState === 'complete') return resolve();
    pc.onicegatheringstatechange = () => { if (pc.iceGatheringState === 'complete') resolve(); };
    setTimeout(resolve, 2000);
  });

  try {
    const res    = await fetch(OFFER_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
    });
    const answer = await res.json();
    await pc.setRemoteDescription(new RTCSessionDescription(answer));
  } catch (e) {
    console.error('[WebRTC] Offer failed:', e);
    setTimeout(startWebRTC, 3000);
  }
}

// Sync canvas size to video element for accurate bbox overlay
function syncCanvasSize() {
  canvas.width  = video.videoWidth  || 1280;
  canvas.height = video.videoHeight || 720;
}

// ── Stats Polling ─────────────────────────────────────────────────────

function startStatsPolling() {
  if (statsInterval) clearInterval(statsInterval);
  prevStats = { bytes: 0, packets: 0, ts: Date.now(), frames: 0 };
  statsInterval = setInterval(pollStats, 1000);
}

function stopStatsPolling() {
  if (statsInterval) clearInterval(statsInterval);
  statsInterval = null;
  resetStats();
}

function resetStats() {
  statFps.textContent     = '--';
  statBitrate.textContent = '-- kbps';
  statPing.textContent    = '-- ms';
  statBytes.textContent   = '-- MB';
  statPackets.textContent = '--';
  statLost.textContent    = '--';
  statRes.textContent     = '--';
}

async function pollStats() {
  if (!pc) return;

  try {
    const stats = await pc.getStats();
    const now   = Date.now();
    const dt    = (now - prevStats.ts) / 1000; // seconds since last poll

    stats.forEach(report => {

      // — Inbound video stream stats
      if (report.type === 'inbound-rtp' && report.kind === 'video') {
        const bytes   = report.bytesReceived   || 0;
        const packets = report.packetsReceived || 0;
        const lost    = report.packetsLost     || 0;
        const frames  = report.framesDecoded   || 0;
        const w       = report.frameWidth      || 0;
        const h       = report.frameHeight     || 0;

        // Bitrate kbps
        const byteDelta = bytes - prevStats.bytes;
        const kbps      = dt > 0 ? ((byteDelta * 8) / dt / 1000).toFixed(0) : 0;

        // FPS
        const frameDelta = frames - prevStats.frames;
        const fps        = dt > 0 ? (frameDelta / dt).toFixed(1) : 0;

        // Total data received MB
        const totalMB = (bytes / 1024 / 1024).toFixed(2);

        // Update display
        statFps.textContent     = `${fps} fps`;
        statBitrate.textContent = `${kbps} kbps`;
        statBytes.textContent   = `${totalMB} MB`;
        statPackets.textContent = packets.toLocaleString();
        statLost.textContent    = lost;
        if (w && h) statRes.textContent = `${w}x${h}`;

        // Colour coding
        statFps.className     = 'stat-value' + (fps < 15 ? ' bad' : fps < 25 ? ' warn' : '');
        statBitrate.className = 'stat-value' + (kbps < 500 ? ' bad' : kbps < 2000 ? ' warn' : '');
        statLost.className    = 'stat-value' + (lost > 50 ? ' bad' : lost > 10 ? ' warn' : '');

        prevStats.bytes   = bytes;
        prevStats.packets = packets;
        prevStats.frames  = frames;
        prevStats.ts      = now;
      }

      // — Round-trip time (ping)
      if (report.type === 'remote-inbound-rtp' && report.kind === 'video') {
        const rtt = report.roundTripTime;
        if (rtt !== undefined) {
          const ms = (rtt * 1000).toFixed(0);
          statPing.textContent  = `${ms} ms`;
          statPing.className    = 'stat-value' + (ms > 150 ? ' bad' : ms > 60 ? ' warn' : '');
        }
      }

      // — Candidate pair (fallback ping from currentRoundTripTime)
      if (report.type === 'candidate-pair' && report.state === 'succeeded') {
        if (report.currentRoundTripTime !== undefined) {
          const ms = (report.currentRoundTripTime * 1000).toFixed(0);
          // Only update if remote-inbound-rtp didn't already set it
          if (statPing.textContent === '-- ms') {
            statPing.textContent = `${ms} ms`;
            statPing.className   = 'stat-value' + (ms > 150 ? ' bad' : ms > 60 ? ' warn' : '');
          }
        }
      }
    });
  } catch (e) {
    console.warn('[Stats] getStats error:', e);
  }
}

// ── WebSocket ──────────────────────────────────────────────────────────────

function startWebSocket() {
  const ws = new WebSocket(WS_URL);
  ws.onmessage = (e) => handleDetection(JSON.parse(e.data));
  ws.onclose   = ()  => setTimeout(startWebSocket, 3000);
  ws.onerror   = ()  => ws.close();
}

// ── Detection Handler ──────────────────────────────────────────────────────

function handleDetection(data) {
  plateText.textContent = data.plate || '---';
  plateTime.textContent = data.timestamp || '';
  plateConf.textContent = data.confidence ? `Confidence: ${(data.confidence * 100).toFixed(0)}%` : '';

  plateText.classList.remove('flash');
  void plateText.offsetWidth;
  plateText.classList.add('flash');

  detectBadge.textContent = 'Detection: Active';
  detectBadge.className   = 'badge badge--success';

  if (data.bbox) drawBBox(data.bbox);
  addLogRow(data);
}

function drawBBox(bbox) {
  const [x1, y1, x2, y2] = bbox;
  const scaleX = canvas.clientWidth  / (canvas.width  || 1280);
  const scaleY = canvas.clientHeight / (canvas.height || 720);

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = '#f5c518';
  ctx.lineWidth   = 2.5;
  ctx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY);

  ctx.fillStyle = '#f5c518';
  ctx.font      = 'bold 14px monospace';
  ctx.fillText('PLATE', x1 * scaleX, (y1 * scaleY) - 6);

  setTimeout(() => ctx.clearRect(0, 0, canvas.width, canvas.height), 2500);
}

function addLogRow(data) {
  const empty = logBody.querySelector('.empty-row');
  if (empty) empty.closest('tr').remove();

  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td>${data.plate}</td>
    <td>${data.confidence ? (data.confidence * 100).toFixed(0) + '%' : '-'}</td>
    <td>${data.timestamp ? data.timestamp.split(' ')[1] : ''}</td>
  `;
  logBody.prepend(tr);
  while (logBody.rows.length > 50) logBody.deleteRow(logBody.rows.length - 1);
}

// ── Stream Badge ───────────────────────────────────────────────────────────

function updateStreamBadge(connected) {
  streamBadge.textContent = connected ? 'Stream: Live' : 'Stream: Offline';
  streamBadge.className   = connected ? 'badge badge--success' : 'badge badge--error';
}

// ── Theme Toggle ───────────────────────────────────────────────────────────

(function () {
  const btn  = document.querySelector('[data-theme-toggle]');
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
