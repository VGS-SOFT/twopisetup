/**
 * dashboard.js
 * Video: MediaMTX WebRTC (port 8889) - handles 60fps delivery natively
 * ANPR:  FastAPI WebSocket (port 8000) - plate results, detection log
 * Stats: WebRTC getStats() - FPS, bitrate, ping, packets
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

const statFps     = document.getElementById('stat-fps');
const statBitrate = document.getElementById('stat-bitrate');
const statPing    = document.getElementById('stat-ping');
const statBytes   = document.getElementById('stat-bytes');
const statPackets = document.getElementById('stat-packets');
const statLost    = document.getElementById('stat-lost');
const statRes     = document.getElementById('stat-res');

const HOST = window.location.hostname;

// MediaMTX serves WebRTC on 8889
const MEDIAMTX_WHEP = `http://${HOST}:8889/gate/whep`;

// FastAPI still serves ANPR WebSocket on 8000
const WS_URL = `ws://${HOST}:8000/ws/plates`;

// ── MediaMTX WebRTC via WHEP protocol ──────────────────────────────────────
// WHEP = WebRTC HTTP Egress Protocol
// MediaMTX exposes a standard WHEP endpoint - much simpler than manual SDP

let pc = null;
let statsInterval = null;
let prevStats = { bytes: 0, packets: 0, ts: Date.now(), frames: 0 };

async function startMediaMTX() {
  if (pc) { try { pc.close(); } catch(e){} pc = null; }

  pc = new RTCPeerConnection({ iceServers: [] });

  pc.ontrack = (event) => {
    if (event.track.kind === 'video') {
      video.srcObject = event.streams[0];
      video.onloadedmetadata = () => {
        noSignal.classList.add('hidden');
        updateStreamBadge(true);
        canvas.width  = video.videoWidth  || 1280;
        canvas.height = video.videoHeight || 720;
        startStatsPolling();
      };
    }
  };

  pc.oniceconnectionstatechange = () => {
    if (['failed', 'disconnected', 'closed'].includes(pc.iceConnectionState)) {
      updateStreamBadge(false);
      noSignal.classList.remove('hidden');
      stopStatsPolling();
      setTimeout(startMediaMTX, 3000);
    }
  };

  pc.addTransceiver('video', { direction: 'recvonly' });
  pc.addTransceiver('audio', { direction: 'recvonly' });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  // Wait for ICE gathering
  await new Promise(resolve => {
    if (pc.iceGatheringState === 'complete') return resolve();
    pc.onicegatheringstatechange = () => {
      if (pc.iceGatheringState === 'complete') resolve();
    };
    setTimeout(resolve, 2000);
  });

  try {
    // WHEP: POST the SDP offer, get SDP answer back
    const res = await fetch(MEDIAMTX_WHEP, {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: pc.localDescription.sdp
    });

    if (!res.ok) throw new Error(`WHEP ${res.status}: ${await res.text()}`);

    const answerSdp = await res.text();
    await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });

  } catch (e) {
    console.error('[MediaMTX] WHEP failed:', e);
    setTimeout(startMediaMTX, 3000);
  }
}

// ── Stats Polling ─────────────────────────────────────────────────────

function startStatsPolling() {
  if (statsInterval) clearInterval(statsInterval);
  prevStats = { bytes: 0, packets: 0, ts: Date.now(), frames: 0 };
  statsInterval = setInterval(pollStats, 1000);
}

function stopStatsPolling() {
  clearInterval(statsInterval);
  statsInterval = null;
}

async function pollStats() {
  if (!pc) return;
  try {
    const stats = await pc.getStats();
    const now   = Date.now();
    const dt    = (now - prevStats.ts) / 1000;

    stats.forEach(report => {
      if (report.type === 'inbound-rtp' && report.kind === 'video') {
        const bytes   = report.bytesReceived   || 0;
        const packets = report.packetsReceived || 0;
        const lost    = report.packetsLost     || 0;
        const frames  = report.framesDecoded   || 0;
        const w       = report.frameWidth      || 0;
        const h       = report.frameHeight     || 0;

        const kbps    = dt > 0 ? ((( bytes - prevStats.bytes) * 8) / dt / 1000).toFixed(0) : 0;
        const fps     = dt > 0 ? ((frames - prevStats.frames) / dt).toFixed(1) : 0;
        const totalMB = (bytes / 1024 / 1024).toFixed(2);

        statFps.textContent     = `${fps} fps`;
        statBitrate.textContent = `${kbps} kbps`;
        statBytes.textContent   = `${totalMB} MB`;
        statPackets.textContent = packets.toLocaleString();
        statLost.textContent    = lost;
        if (w && h) statRes.textContent = `${w}x${h}`;

        statFps.className     = 'stat-value' + (fps < 15 ? ' bad' : fps < 45 ? ' warn' : '');
        statBitrate.className = 'stat-value' + (kbps < 500 ? ' bad' : kbps < 2000 ? ' warn' : '');
        statLost.className    = 'stat-value' + (lost > 50 ? ' bad' : lost > 10 ? ' warn' : '');

        prevStats = { bytes, packets, ts: now, frames };
      }

      if (report.type === 'candidate-pair' && report.state === 'succeeded') {
        const ms = ((report.currentRoundTripTime || 0) * 1000).toFixed(0);
        statPing.textContent  = `${ms} ms`;
        statPing.className    = 'stat-value' + (ms > 150 ? ' bad' : ms > 60 ? ' warn' : '');
      }
    });
  } catch(e) { console.warn('[Stats]', e); }
}

// ── WebSocket (ANPR results) ────────────────────────────────────────────────

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
  plateConf.textContent = data.confidence ? `Confidence: ${(data.confidence*100).toFixed(0)}%` : '';

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
  ctx.strokeRect(x1*scaleX, y1*scaleY, (x2-x1)*scaleX, (y2-y1)*scaleY);
  ctx.fillStyle   = '#f5c518';
  ctx.font        = 'bold 14px monospace';
  ctx.fillText('PLATE', x1*scaleX, y1*scaleY - 6);
  setTimeout(() => ctx.clearRect(0, 0, canvas.width, canvas.height), 2500);
}

function addLogRow(data) {
  const empty = logBody.querySelector('.empty-row');
  if (empty) empty.closest('tr').remove();
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td>${data.plate}</td>
    <td>${data.confidence ? (data.confidence*100).toFixed(0)+'%' : '-'}</td>
    <td>${data.timestamp ? data.timestamp.split(' ')[1] : ''}</td>
  `;
  logBody.prepend(tr);
  while (logBody.rows.length > 50) logBody.deleteRow(logBody.rows.length - 1);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function updateStreamBadge(connected) {
  streamBadge.textContent = connected ? 'Stream: Live' : 'Stream: Offline';
  streamBadge.className   = connected ? 'badge badge--success' : 'badge badge--error';
}

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

startMediaMTX();
startWebSocket();
