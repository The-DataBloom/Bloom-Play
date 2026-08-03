const STATS_MS = 1200;
const HARDWARE_MS = 20000;
const DEVICES_MS = 4000;
const SHOTS_MS = 6000;

const ACCESS_TOKEN = new URLSearchParams(window.location.search).get('token') || '';
const DEMO_MODE = window.__DEMO__ === true || new URLSearchParams(window.location.search).get('demo') === '1';

const viewEl    = document.getElementById('view');
const connEl    = document.getElementById('connStatus');
const connText  = document.getElementById('connText');
const hostName  = document.getElementById('hostName');
const hostDot   = document.querySelector('.host-dot');
const clockEl   = document.getElementById('clock');
const pageTitle = document.getElementById('pageTitle');
const pageSub   = document.getElementById('pageSub');
const footInfo  = document.getElementById('footInfo');

let currentView = 'overview';
let pollTimer = null;
let hardwareCache = null;
let overlayCfg = null;
let shotsCache = null;
let devicesCache = null;

let overviewBuilt = false;
let settingsBuilt = false;

const HIST_MAX = 60;
const hist = { cpu: [], gpu: [], ram: [], down: [], up: [], fps: [] };

const NAV_ITEMS = document.querySelectorAll('.side-item, .bn-item');

const VIEW_META = {
    overview:    { title: 'Overview',    sub: 'Live system telemetry' },
    hardware:    { title: 'Hardware',    sub: 'Full PC inventory' },
    screenshots: { title: 'Screenshots', sub: 'Remote capture & gallery' },
    devices:     { title: 'Devices',     sub: 'Connected clients' },
    settings:    { title: 'Settings',    sub: 'Overlay & remote control' },
};

const OVERLAY_COLORS = ['#7c6cff', '#4ecdc4', '#ff6b9d', '#ffa25c', '#6ea8ff', '#a78bfa', '#2dd4a7', '#f5c451'];

function api(url, opts = {}) {
    if (DEMO_MODE) return demoApi(url, opts);
    const sep = url.includes('?') ? '&' : '?';
    return fetch(url + sep + 'token=' + encodeURIComponent(ACCESS_TOKEN), {
        cache: 'no-store',
        ...opts,
        headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    });
}

const demo = { stats: null, hardware: null, shots: [], devices: [], blocked: [], overlay: null, seq: 0 };

function demoStats() {
    demo.seq++;
    const t = demo.seq / 5;
    const w = Math.sin(t) * 10 + Math.sin(t / 2.3) * 6;
    return {
        cpu: Math.max(4, Math.min(97, 46 + w)),
        cpu_temp: Math.max(30, Math.min(93, 60 + w / 2)),
        cpu_temp_status: 'OK',
        ram: { used: Math.max(6, Math.min(30, 12 + w / 3)), total: 32, percent: Math.max(8, Math.min(96, 38 + w)) },
        gpu: { name: 'NVIDIA GeForce RTX 4070', usage: Math.max(3, Math.min(96, 58 + w)),
                vram_used: 5.1, vram_total: 12, temp: Math.max(32, Math.min(90, 63 + w / 2)) },
        network: { download: Math.max(0.3, 26 + w * 1.5), upload: Math.max(0.2, 6.5 + w / 2), ping: Math.max(8, 33 + w / 3) },
        battery: { percent: 82, charging: false, health_percent: 91, health_label: 'Excellent' },
        fps: { fps: Math.max(20, 140 - Math.abs(w) * 2), status: 'Capturing' },
    };
}

demo.stats = demoStats();

demo.hardware = {
    cpu: { name: 'AMD Ryzen 7 7800X3D', brand: 'AMD', cores: 8, threads: 16, base_clock: 4.2, cache: '96KB L2, 96MB L3', architecture: 'x64' },
    gpu: { name: 'NVIDIA GeForce RTX 4070', vendor: 'NVIDIA', memory: '12 GB', driver: '31.0.15.2760' },
    ram: { size: '32 GB', type: 'DDR5', speed: 6000, brand: 'G.Skill', form_factor: 'DIMM', slots: 2 },
    disk: [
        { name: 'C:', type: 'SSD', model: 'Samsung 990 Pro', total: 512, used: 218, free: 294, percent: 43 },
        { name: 'D:', type: 'HDD', model: 'Seagate Barracuda', total: 1024, used: 640, free: 384, percent: 63 },
    ],
    system: { os: 'Windows 11 Pro', hostname: 'GAMING-RIG', arch: 'x64', kernel: '10.0.22631' },
    bios: { board: 'ASUSTeK ROG STRIX B650E-F', bios: '2007', serial: 'M60XXXXXXXXX' },
    display: {
        monitors: [{ name: 'ASUS ROG 240Hz', resolution: '2560x1440', refresh_rate: '240 Hz', primary: true }],
        primary_resolution: '2560x1440', refresh_rate: '240 Hz', screen_size: '27.0"', adapter: 'NVIDIA GeForce RTX 4070',
    },
    audio: { devices: [{ name: 'Realtek High Definition Audio', manufacturer: 'Realtek', status: 'OK' }, { name: 'HyperX Cloud II', manufacturer: 'HP', status: 'OK' }], primary_device: 'Realtek', manufacturer: 'Realtek' },
    battery: { name: 'Internal Battery', manufacturer: 'ASUS', chemistry: 'Lithium Ion', design_capacity: '5320 mWh', full_charge_capacity: '4850 mWh', serial_number: 'XXXX-YYYY', design_voltage: '15400 mV' },
    total_storage: '1536 GB',
};

for (let i = 0; i < 4; i++) {
    const d = new Date(Date.now() - i * 3600e3);
    demo.shots.push({ name: `Screenshot_${d.toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`, size: 1200000 + i * 300000, mtime: Math.floor(d.getTime() / 1000) });
}

demo.devices = [
    { ip: '192.168.1.42', user_agent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8)', connected_since: Date.now() / 1000 - 320 },
    { ip: '192.168.1.55', user_agent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4)', connected_since: Date.now() / 1000 - 95 },
];
demo.blocked = [{ ip: '192.168.1.99', remaining_seconds: 34 }];

demo.overlay = {
    enabled: true,
    color: '#7c6cff',
    position: 'top-right',
    font_size: 14,
    font_family: "Consolas, 'Segoe UI', monospace",
    fields: ['cpu', 'gpu', 'fps', 'ram', 'ping'],
    hotkey: 'Ctrl+Shift+O',
    available_fields: [['cpu', 'CPU %'], ['cpu_temp', 'CPU Temp'], ['gpu', 'GPU %'], ['gpu_temp', 'GPU Temp'], ['ram', 'RAM'], ['fps', 'FPS'], ['download', 'Download'], ['upload', 'Upload'], ['ping', 'Ping'], ['battery', 'Battery']],
    available_positions: ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
    available_fonts: ["Consolas, 'Segoe UI', monospace", "'Segoe UI', Tahoma, sans-serif", "'Courier New', monospace", 'Arial, sans-serif', 'Tahoma, sans-serif'],
};

function jsonOk(obj) {
    return Promise.resolve(new Response(JSON.stringify(obj), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
    }));
}

function demoApi(url, opts) {
    const method = (opts && opts.method) || 'GET';
    const u = url.split('?')[0];

    if (method === 'GET') {
        if (u === '/stats') return jsonOk(demoStats());
        if (u === '/hardware') return jsonOk(demo.hardware);
        if (u === '/system') return jsonOk({ hostname: 'GAMING-RIG', os: 'Windows 11 Pro', total_storage: '1536 GB' });
        if (u === '/screenshot/list') return jsonOk({ folder: 'C:\\Users\\Gamer\\Pictures\\BloomPlay', screenshots: demo.shots });
        if (u === '/devices') return jsonOk({ devices: demo.devices });
        if (u === '/devices/blocked') return jsonOk({ blocked: demo.blocked });
        if (u === '/overlay/config') return jsonOk(demo.overlay);
    } else {
        if (u === '/screenshot/capture') {
            const d = new Date();
            demo.shots.unshift({ name: `Screenshot_${d.toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`, size: 900000, mtime: Math.floor(d.getTime() / 1000) });
            return jsonOk({ name: demo.shots[0].name, path: '', size: 900000 });
        }
        if (u === '/screenshot/delete') {
            try {
                const body = JSON.parse((opts && opts.body) || '{}');
                demo.shots = demo.shots.filter(s => s.name !== body.name);
            } catch {}
            return jsonOk({ deleted: true });
        }
        if (u === '/overlay/config') {
            try {
                const body = JSON.parse((opts && opts.body) || '{}');
                Object.assign(demo.overlay, body);
            } catch {}
            return jsonOk(demo.overlay);
        }
        if (u === '/export/pdf') {
            return Promise.resolve(new Response(new Blob(['%PDF-1.4 demo']), {
                status: 200,
                headers: { 'Content-Type': 'application/pdf' },
            }));
        }
        if (u === '/devices/disconnect') {
            const ip = new URLSearchParams(url.split('?')[1] || '').get('ip');
            demo.devices = demo.devices.filter(d => d.ip !== ip);
            return jsonOk({ disconnected: true });
        }
        if (u === '/devices/unblock') {
            demo.blocked = [];
            return jsonOk({ unblocked: true });
        }
        if (u === '/shutdown') return jsonOk({ status: 'shutting down' });
    }
    return jsonOk({});
}

function safe(val, fb = '—') {
    if (val === undefined || val === null || val === '') return fb;
    if (typeof val === 'object') { try { return JSON.stringify(val); } catch { return '[obj]'; } }
    return String(val);
}
function safeHtml(val, fb = '—') { return esc(safe(val, fb)); }
function num(v) { const n = Number(v); return isNaN(n) ? 0 : n; }
function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fillClass(v, warn = 70, crit = 85) {
    const n = num(v);
    if (n >= crit) return 'f-red';
    if (n >= warn) return 'f-yellow';
    return 'f-green';
}

function shotImgSrc(name) {
    if (!DEMO_MODE) {
        return '/screenshot/file?name=' + encodeURIComponent(name) + '&token=' + encodeURIComponent(ACCESS_TOKEN);
    }
    let h = 0;
    for (let i = 0; i < String(name).length; i++) h = (h * 31 + String(name).charCodeAt(i)) >>> 0;
    const hue = h % 360;
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200">' +
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
        '<stop offset="0" stop-color="hsl(' + hue + ',45%,22%)"/>' +
        '<stop offset="1" stop-color="hsl(' + ((hue + 45) % 360) + ',45%,9%)"/>' +
        '</linearGradient></defs><rect width="320" height="200" fill="url(#g)"/>' +
        '<circle cx="160" cy="92" r="24" fill="none" stroke="rgba(255,255,255,0.28)" stroke-width="3"/>' +
        '<circle cx="160" cy="92" r="7" fill="rgba(255,255,255,0.4)"/>' +
        '<path d="M126 138 L162 108 L188 126 L214 106 L240 130 L240 140 L126 140 Z" fill="rgba(255,255,255,0.18)"/>' +
        '</svg>');
}

function smoothPath(values, w, h, minV, maxV) {
    if (values.length < 2) return '';
    const range = (maxV - minV) || 1;
    const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - ((Math.min(maxV, Math.max(minV, v)) - minV) / range) * h]);
    let d = 'M ' + pts[0][0].toFixed(1) + ' ' + pts[0][1].toFixed(1);
    for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
        const c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
        const c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
        d += ' C ' + c1x.toFixed(1) + ' ' + c1y.toFixed(1) + ' ' + c2x.toFixed(1) + ' ' + c2y.toFixed(1) + ' ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
    }
    return d;
}
function areaPath(values, w, h, minV, maxV) {
    const line = smoothPath(values, w, h, minV, maxV);
    if (!line) return '';
    return line + ' L ' + w.toFixed(1) + ' ' + h.toFixed(1) + ' L 0 ' + h.toFixed(1) + ' Z';
}
function pushHist(key, v) {
    hist[key].push(num(v));
    if (hist[key].length > HIST_MAX) hist[key].shift();
}

function setText(id, txt) {
    const el = document.getElementById(id);
    if (el) el.textContent = txt;
}
function setStyle(id, prop, val) {
    const el = document.getElementById(id);
    if (el) el.style[prop] = val;
}
function setCssVar(id, prop, val) {
    const el = document.getElementById(id);
    if (el) el.style.setProperty(prop, val);
}

const toastEl = document.getElementById('toast');
let toastTimer = null;
function toast(msg, kind = 'ok') {
    toastEl.textContent = msg;
    toastEl.className = 'toast show ' + kind;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.className = 'toast ' + kind; }, 2600);
}

const modalOverlay = document.getElementById('modalOverlay');
const modalTitle   = document.getElementById('modalTitle');
const modalMsg     = document.getElementById('modalMsg');
const modalCancel  = document.getElementById('modalCancel');
const modalConfirm = document.getElementById('modalConfirm');
let confirmHandler = null;

function confirmBox(title, msg, onYes) {
    modalTitle.textContent = title;
    modalMsg.textContent = msg;
    confirmHandler = onYes;
    modalOverlay.classList.remove('hidden');
}
modalCancel.addEventListener('click', () => { modalOverlay.classList.add('hidden'); confirmHandler = null; });
modalOverlay.addEventListener('click', (e) => { if (e.target === modalOverlay) { modalOverlay.classList.add('hidden'); confirmHandler = null; } });
modalConfirm.addEventListener('click', () => {
    modalOverlay.classList.add('hidden');
    const h = confirmHandler;
    confirmHandler = null;
    if (h) h();
});

const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightboxImg');
function openLightbox(src) { lightboxImg.src = src; lightbox.classList.add('open'); }
document.getElementById('lbClose').addEventListener('click', () => lightbox.classList.remove('open'));
lightbox.addEventListener('click', (e) => { if (e.target === lightbox) lightbox.classList.remove('open'); });

function fmtClock() {
    const d = new Date();
    clockEl.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
setInterval(fmtClock, 1000);
fmtClock();

function setOnline(online) {
    connEl.className = 'conn ' + (online ? 'online' : 'offline');
    connText.textContent = online ? 'Online' : 'Offline';
    hostDot.className = 'host-dot ' + (online ? 'online' : 'offline');
    if (!online) hostName.textContent = 'Disconnected';
}

function gaugeTile(id, ico, name, c1, c2, unit) {
    return `
        <div class="stat-tile gauge-tile" style="--g1:${c1};--g2:${c2}">
            <div class="gauge-wrap">
                <div class="gauge" id="${id}Gauge" style="--pct:0">
                    <span class="gauge-val" id="${id}Val">--</span>
                    <span class="gauge-unit">${unit}</span>
                </div>
                <div class="gauge-label"><span class="gauge-ico">${ico}</span>${name}</div>
            </div>
            <div class="stat-mini" id="${id}Mini">—</div>
        </div>`;
}

function hbarTile(id, ico, name, c1, c2, unit) {
    return `
        <div class="stat-tile hbar-tile" style="--g1:${c1};--g2:${c2}">
            <div class="hbar-head">
                <span class="hbar-ico">${ico}</span>
                <span class="hbar-name">${name}</span>
            </div>
            <div class="hbar-main">
                <span class="hbar-val" id="${id}Val">--</span>
                <span class="hbar-unit">${unit}</span>
            </div>
            <div class="hbar-track"><div class="hbar-fill" id="${id}Fill" style="width:0%"></div></div>
            <div class="stat-mini" id="${id}Mini">—</div>
        </div>`;
}

function sparkTile(id, ico, name, c1, c2, unit) {
    return `
        <div class="stat-tile spark-tile" style="--g1:${c1};--g2:${c2}">
            <div class="hbar-head">
                <span class="hbar-ico">${ico}</span>
                <span class="hbar-name">${name}</span>
            </div>
            <div class="hbar-main">
                <span class="hbar-val" id="${id}Val">--</span>
                <span class="hbar-unit">${unit}</span>
            </div>
            <svg class="spark-svg" viewBox="0 0 120 36" preserveAspectRatio="none">
                <path id="${id}Spark" class="spark-line" d=""/>
            </svg>
            <div class="stat-mini" id="${id}Mini">—</div>
        </div>`;
}

function buildOverview() {
    return `
    <div class="grid-4 stat-grid">
        ${gaugeTile('cpu', '◈', 'CPU', '#7c6cff', '#a78bfa', '%')}
        ${gaugeTile('gpu', '▤', 'GPU', '#ff6b9d', '#ffa25c', '%')}
        ${hbarTile('ram', '▥', 'RAM', '#2dd4a7', '#4ecdc4', 'GB')}
        ${sparkTile('fps', '⌬', 'FPS', '#4ecdc4', '#6ea8ff', '')}
    </div>

    <div class="card">
        <div class="card-head">
            <div class="card-ico c1">◈</div>
            <div class="card-title">Performance</div>
            <span class="card-sub">Last ${HIST_MAX}s · CPU / GPU / RAM</span>
            <div class="chart-legend">
                <span class="lg"><i style="background:#7c6cff"></i>CPU <b id="lgCpu">--</b></span>
                <span class="lg"><i style="background:#ff6b9d"></i>GPU <b id="lgGpu">--</b></span>
                <span class="lg"><i style="background:#2dd4a7"></i>RAM <b id="lgRam">--</b></span>
            </div>
        </div>
        <div class="chart-box">
            <svg id="perfChart" class="perf-svg" viewBox="0 0 600 200" preserveAspectRatio="none">
                <defs>
                    <linearGradient id="gradCpu" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0" stop-color="#7c6cff" stop-opacity="0.34"/><stop offset="1" stop-color="#7c6cff" stop-opacity="0"/>
                    </linearGradient>
                    <linearGradient id="gradGpu" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0" stop-color="#ff6b9d" stop-opacity="0.30"/><stop offset="1" stop-color="#ff6b9d" stop-opacity="0"/>
                    </linearGradient>
                    <linearGradient id="gradRam" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0" stop-color="#2dd4a7" stop-opacity="0.30"/><stop offset="1" stop-color="#2dd4a7" stop-opacity="0"/>
                    </linearGradient>
                </defs>
                <g class="cgrid">
                    <line x1="0" y1="0" x2="600" y2="0"/><line x1="0" y1="50" x2="600" y2="50"/>
                    <line x1="0" y1="100" x2="600" y2="100"/><line x1="0" y1="150" x2="600" y2="150"/>
                    <line x1="0" y1="200" x2="600" y2="200"/>
                </g>
                <path id="areaCpu" class="aline" fill="url(#gradCpu)" stroke="none"/>
                <path id="areaGpu" class="aline" fill="url(#gradGpu)" stroke="none"/>
                <path id="areaRam" class="aline" fill="url(#gradRam)" stroke="none"/>
                <path id="lineCpu" class="cline c-cpu"/>
                <path id="lineGpu" class="cline c-gpu"/>
                <path id="lineRam" class="cline c-ram"/>
            </svg>
        </div>
    </div>

    <div class="grid-2">
        <div class="card">
            <div class="card-head">
                <div class="card-ico c2">⇅</div>
                <div class="card-title">Network</div>
                <span class="card-sub">Live · Mbps</span>
            </div>
            <div class="net-grid">
                <div class="net-col">
                    <div class="stat-top" style="margin-bottom:4px"><span class="stat-name">Download</span></div>
                    <div class="stat-main"><span class="stat-value c-cyan" id="netDown">0.0</span><span class="stat-unit">Mbps</span></div>
                    <svg class="mini-chart" viewBox="0 0 300 80" preserveAspectRatio="none">
                        <defs>
                            <linearGradient id="gradDown" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0" stop-color="#4ecdc4" stop-opacity="0.38"/><stop offset="1" stop-color="#4ecdc4" stop-opacity="0"/>
                            </linearGradient>
                        </defs>
                        <g class="cgrid">
                            <line x1="0" y1="20" x2="300" y2="20"/><line x1="0" y1="40" x2="300" y2="40"/>
                            <line x1="0" y1="60" x2="300" y2="60"/><line x1="0" y1="80" x2="300" y2="80"/>
                        </g>
                        <path id="areaDown" fill="url(#gradDown)" stroke="none"/>
                        <path id="lineDown" class="aline a-down"/>
                    </svg>
                </div>
                <div class="net-col">
                    <div class="stat-top" style="margin-bottom:4px"><span class="stat-name">Upload</span></div>
                    <div class="stat-main"><span class="stat-value c-blue" id="netUp">0.0</span><span class="stat-unit">Mbps</span></div>
                    <svg class="mini-chart" viewBox="0 0 300 80" preserveAspectRatio="none">
                        <defs>
                            <linearGradient id="gradUp2" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0" stop-color="#6ea8ff" stop-opacity="0.38"/><stop offset="1" stop-color="#6ea8ff" stop-opacity="0"/>
                            </linearGradient>
                        </defs>
                        <g class="cgrid">
                            <line x1="0" y1="20" x2="300" y2="20"/><line x1="0" y1="40" x2="300" y2="40"/>
                            <line x1="0" y1="60" x2="300" y2="60"/><line x1="0" y1="80" x2="300" y2="80"/>
                        </g>
                        <path id="areaUp" fill="url(#gradUp2)" stroke="none"/>
                        <path id="lineUp" class="aline a-up"/>
                    </svg>
                </div>
            </div>
            <div class="ping-row">
                <span class="ping-name">Ping</span>
                <span class="signal-meter good" id="pingMeter"><i></i><i></i><i></i><i></i><i></i></span>
                <b id="pingVal">--</b><span class="stat-unit">ms</span>
                <span class="ping-tag good" id="pingTag">—</span>
            </div>
        </div>

        <div class="card">
            <div class="card-head">
                <div class="card-ico c4">◉</div>
                <div class="card-title">Temperatures</div>
                <span class="card-sub">°C</span>
            </div>
            <div class="therm-grid">
                <div class="therm">
                    <div class="therm-track"><div class="therm-fill" id="cpuThermFill" style="height:0%"></div></div>
                    <div class="therm-val"><b id="cpuTempBig">—</b><span>°C</span></div>
                    <div class="therm-label">CPU</div>
                    <div class="stat-mini" id="cpuTempStatus">Sensor unavailable</div>
                </div>
                <div class="therm">
                    <div class="therm-track"><div class="therm-fill" id="gpuThermFill" style="height:0%"></div></div>
                    <div class="therm-val"><b id="gpuTempBig">—</b><span>°C</span></div>
                    <div class="therm-label">GPU</div>
                    <div class="stat-mini" id="gpuTempMini">Sensor unavailable</div>
                </div>
            </div>
        </div>
    </div>

    <div class="grid-2">
        <div class="stat-tile battery-tile" style="--g1:#2dd4a7;--g2:#4ecdc4">
            <div class="hbar-head">
                <span class="hbar-ico">▮</span>
                <span class="hbar-name">Battery</span>
            </div>
            <div class="hbar-main">
                <span class="hbar-val" id="batVal">--</span>
                <span class="hbar-unit">%</span>
            </div>
            <div class="bat-track"><div class="bat-fill" id="batFill" style="width:0%"></div></div>
            <div class="stat-mini" id="batMini">—</div>
        </div>
        <div class="stat-tile health-tile" style="--g1:#f5c451;--g2:#ffa25c">
            <div class="hbar-head">
                <span class="hbar-ico">◐</span>
                <span class="hbar-name">Battery Health</span>
            </div>
            <div class="hbar-main">
                <span class="hbar-val" id="bhVal">--</span>
                <span class="hbar-unit">%</span>
            </div>
            <div class="health-track"><div class="health-fill" id="bhFill" style="width:0%"></div></div>
            <div class="stat-mini" id="bhMini">—</div>
        </div>
    </div>
    `;
}

function updateGauge(id, pct) {
    const v = Math.min(100, Math.max(0, num(pct)));
    setCssVar(id + 'Gauge', '--pct', v);
}

function updateBar(id, pct) {
    const v = Math.min(100, Math.max(0, num(pct)));
    setStyle(id + 'Fill', 'width', v + '%');
}

function updateSpark(id, arr) {
    const el = document.getElementById(id + 'Spark');
    if (!el || !arr || arr.length < 2) return;
    const W = 120, H = 36;
    const maxV = Math.max(...arr, 1);
    const pts = arr.map((v, i) => [(i / (arr.length - 1)) * W, H - (v / maxV) * H]);
    let d = 'M ' + pts[0][0].toFixed(1) + ' ' + pts[0][1].toFixed(1);
    for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
        const c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
        const c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
        d += ' C ' + c1x.toFixed(1) + ' ' + c1y.toFixed(1) + ' ' + c2x.toFixed(1) + ' ' + c2y.toFixed(1) + ' ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
    }
    el.setAttribute('d', d);
}

function tempColor(t) {
    if (t === null || t === undefined) return 'linear-gradient(180deg,#3a3a5c,#2a2a44)';
    if (t >= 85) return 'linear-gradient(180deg,#ff6b6b,#ff2d55)';
    if (t >= 70) return 'linear-gradient(180deg,#ffa25c,#ff6b6b)';
    if (t >= 55) return 'linear-gradient(180deg,#f5c451,#ffa25c)';
    return 'linear-gradient(180deg,#2dd4a7,#4ecdc4)';
}

function updateOverview(data) {
    const cpu = num(data.cpu);
    const gpuObj = data.gpu || {};
    const gpu = num(gpuObj.usage);
    const ram = data.ram || {};
    const ramPct = num(ram.percent);
    const net = data.network || {};
    const down = num(net.download), up = num(net.upload), ping = num(net.ping);
    const bat = data.battery || {};
    const fpsObj = data.fps || {};

    pushHist('cpu', cpu); pushHist('gpu', gpu); pushHist('ram', ramPct);
    pushHist('down', down); pushHist('up', up);

    updateGauge('cpu', cpu);
    setText('cpuVal', Math.round(cpu));
    setText('cpuMini', cpu >= 85 ? 'High load' : cpu >= 70 ? 'Moderate load' : 'Normal load');

    updateGauge('gpu', gpu);
    setText('gpuVal', Math.round(gpu));
    setText('gpuMini', safeHtml(gpuObj.name, 'GPU'));

    updateBar('ram', ramPct);
    setText('ramVal', num(ram.used).toFixed(1));
    setText('ramMini', num(ram.total) ? `${Math.round(ramPct)}% of ${num(ram.total).toFixed(0)} GB` : '—');

    const fps = fpsObj.fps;
    pushHist('fps', fps === null || fps === undefined ? 0 : Math.round(fps));
    updateSpark('fps', hist.fps);
    setText('fpsVal', fps === null || fps === undefined ? 'N/A' : Math.round(fps));
    setText('fpsMini', safeHtml(fpsObj.status, ''));

    const W = 600, H = 200;
    document.getElementById('lineCpu').setAttribute('d', smoothPath(hist.cpu, W, H, 0, 100));
    document.getElementById('areaCpu').setAttribute('d', areaPath(hist.cpu, W, H, 0, 100));
    document.getElementById('lineGpu').setAttribute('d', smoothPath(hist.gpu, W, H, 0, 100));
    document.getElementById('areaGpu').setAttribute('d', areaPath(hist.gpu, W, H, 0, 100));
    document.getElementById('lineRam').setAttribute('d', smoothPath(hist.ram, W, H, 0, 100));
    document.getElementById('areaRam').setAttribute('d', areaPath(hist.ram, W, H, 0, 100));
    setText('lgCpu', Math.round(cpu) + '%');
    setText('lgGpu', Math.round(gpu) + '%');
    setText('lgRam', Math.round(ramPct) + '%');

    const NW = 300, NH = 80;
    const netMax = Math.max(Math.max(...hist.down, 1), Math.max(...hist.up, 1)) * 1.15;
    document.getElementById('lineDown').setAttribute('d', smoothPath(hist.down, NW, NH, 0, netMax));
    document.getElementById('areaDown').setAttribute('d', areaPath(hist.down, NW, NH, 0, netMax));
    document.getElementById('lineUp').setAttribute('d', smoothPath(hist.up, NW, NH, 0, netMax));
    document.getElementById('areaUp').setAttribute('d', areaPath(hist.up, NW, NH, 0, netMax));
    setText('netDown', down.toFixed(1));
    setText('netUp', up.toFixed(1));

    setText('pingVal', Math.round(ping));
    let cls = 'bad', lvl = 0;
    if (ping < 20)      { cls = 'good'; lvl = 5; }
    else if (ping < 50) { cls = 'good'; lvl = 4; }
    else if (ping < 100) { cls = 'ok';  lvl = 3; }
    else if (ping < 200) { cls = 'ok';  lvl = 2; }
    else                 { cls = 'bad'; lvl = 1; }
    const tag = document.getElementById('pingTag');
    if (tag) {
        tag.textContent = cls === 'good' ? 'Great' : cls === 'ok' ? 'Good' : 'Poor';
        tag.className = 'ping-tag ' + cls;
    }
    const meter = document.getElementById('pingMeter');
    if (meter) {
        meter.className = 'signal-meter ' + cls;
        meter.querySelectorAll('i').forEach((b, i) => b.classList.toggle('on', i < lvl));
    }

    const cpuT = data.cpu_temp;
    const gpuT = gpuObj.temp;
    const cpuFill = document.getElementById('cpuThermFill');
    const gpuFill = document.getElementById('gpuThermFill');
    if (cpuT === null || cpuT === undefined) {
        setStyle('cpuThermFill', 'height', '0%');
        setText('cpuTempBig', '—');
        setText('cpuTempStatus', 'Sensor unavailable');
    } else {
        setStyle('cpuThermFill', 'height', Math.min(100, num(cpuT)) + '%');
        if (cpuFill) cpuFill.style.background = tempColor(num(cpuT));
        setText('cpuTempBig', Math.round(cpuT));
        setText('cpuTempStatus', safeHtml(data.cpu_temp_status, 'Live reading'));
    }
    if (gpuT === null || gpuT === undefined) {
        setStyle('gpuThermFill', 'height', '0%');
        setText('gpuTempBig', '—');
        setText('gpuTempMini', 'Sensor unavailable');
    } else {
        setStyle('gpuThermFill', 'height', Math.min(100, num(gpuT)) + '%');
        if (gpuFill) gpuFill.style.background = tempColor(num(gpuT));
        setText('gpuTempBig', Math.round(gpuT));
        setText('gpuTempMini', gpuT >= 85 ? 'Hot' : gpuT >= 70 ? 'Warm' : 'Normal');
    }

    const pct = bat.percent;
    if (pct === null || pct === undefined || pct === 'N/A') {
        updateBar('bat', 0);
        setText('batVal', '—'); setText('batMini', 'No battery (desktop)');
    } else {
        updateBar('bat', pct);
        setText('batVal', Math.round(num(pct)));
        setText('batMini', bat.charging ? '⚡ Charging' : 'On battery');
    }

    const hp = bat.health_percent;
    const bhFill = document.getElementById('bhFill');
    if (hp === null || hp === undefined) {
        updateBar('bh', 0);
        if (bhFill) bhFill.style.background = 'linear-gradient(90deg,#3a3a5c,#2a2a44)';
        setText('bhVal', '—'); setText('bhMini', 'Unavailable');
    } else {
        updateBar('bh', hp);
        if (bhFill) {
            const col = hp >= 80 ? '#22c55e' : hp >= 60 ? '#eab308' : hp >= 40 ? '#f97316' : '#ef4444';
            bhFill.style.background = 'linear-gradient(90deg,' + col + ',' + col + 'cc)';
        }
        setText('bhVal', Math.round(num(hp)));
        setText('bhMini', safeHtml(bat.health_label, num(hp) >= 80 ? 'Excellent' : 'Good'));
    }
}

const HW_HIDDEN = new Set(['unknown', 'default', 'default monitor', 'generic pnp monitor', 'monitor', 'none', 'n/a', 'not applicable', 'unknown unknown', 'default default']);

function hwNameOk(v) {
    if (v === undefined || v === null) return false;
    const n = String(v).trim().toLowerCase();
    if (!n || HW_HIDDEN.has(n)) return false;
    if (n.startsWith('default ')) return false;
    return true;
}

function hwRow(label, value) {
    if (!hwNameOk(value)) return '';
    return `<div class="hw-row"><span class="hw-label">${esc(label)}</span><span class="hw-value">${esc(value)}</span></div>`;
}

function renderHardware(hw) {
    const cpu = hw.cpu || {}, gpu = hw.gpu || {}, ram = hw.ram || {}, sys = hw.system || {},
          bios = hw.bios || {}, disp = hw.display || {}, audio = hw.audio || {}, bat = hw.battery || {};
    const disks = hw.disk || [];

    const diskHtml = disks.filter(d => hwNameOk(d.name) || hwNameOk(d.model)).length ? disks.filter(d => hwNameOk(d.name) || hwNameOk(d.model)).map(d => `
        <div class="disk-item">
            <div class="disk-top">
                <span class="disk-name">${esc(d.name)}</span>
                <span class="disk-meta">${esc(d.type || '')} · ${d.used}/${d.total} GB · ${d.percent}% used</span>
            </div>
            ${hwNameOk(d.model) ? `<div class="disk-model">${esc(d.model)}</div>` : ''}
            <div class="bar-track"><div class="bar-fill ${fillClass(d.percent)}" style="width:${Math.min(100, d.percent)}%"></div></div>
            <div class="disk-model" style="margin-top:4px">${d.free} GB free of ${d.total} GB</div>
        </div>`).join('') : '<div class="hw-row"><span class="hw-label">No disk info</span></div>';

    const monitorHtml = (disp.monitors || []).filter(m => hwNameOk(m.name)).map(m => `
        <div class="sub-item"><span class="sub-name">${esc(m.name)}</span>
        <span class="sub-detail">${esc(m.resolution || '')} ${esc(m.refresh_rate || '')}${m.primary ? ' · Primary' : ''}</span></div>`).join('');

    const audioHtml = (audio.devices || []).filter(a => hwNameOk(a.name)).map(a => `
        <div class="sub-item"><span class="sub-name">${esc(a.name)}</span>
        <span class="sub-detail">${esc(a.status || '')}${hwNameOk(a.manufacturer) ? ' · ' + esc(a.manufacturer) : ''}</span></div>`).join('');

    return `
    <div class="card">
        <div class="card-head">
            <div class="card-ico c1">▤</div>
            <div class="card-title">Hardware Inventory</div>
            <div class="card-actions">
                <button class="btn btn-primary btn-sm" id="pdfBtn">⬇ Export PDF</button>
            </div>
        </div>
        <div class="hw-wrap">
            <div class="hw-panel hp-cpu">
                <div class="hw-panel-head"><div class="hw-panel-ico">◈</div><div class="hw-panel-title">Processor</div><span class="hw-panel-tag">CPU</span></div>
                ${hwRow('Model', cpu.name)}${hwRow('Brand', cpu.brand)}${hwRow('Cores', cpu.cores)}${hwRow('Threads', cpu.threads)}${hwRow('Base Clock', cpu.base_clock ? cpu.base_clock + ' GHz' : '')}${hwRow('Cache', cpu.cache)}${hwRow('Architecture', cpu.architecture)}
            </div>
            <div class="hw-panel hp-gpu">
                <div class="hw-panel-head"><div class="hw-panel-ico">▣</div><div class="hw-panel-title">Graphics</div><span class="hw-panel-tag">GPU</span></div>
                ${hwRow('Model', gpu.name)}${hwRow('Vendor', gpu.vendor)}${hwRow('VRAM', gpu.memory)}${hwRow('Driver', gpu.driver)}
            </div>
            <div class="hw-panel hp-ram">
                <div class="hw-panel-head"><div class="hw-panel-ico">▥</div><div class="hw-panel-title">Memory</div><span class="hw-panel-tag">RAM</span></div>
                ${hwRow('Total Size', ram.size)}${hwRow('Type', ram.type)}${hwRow('Speed', ram.speed ? ram.speed + ' MHz' : '')}${hwRow('Brand', ram.brand)}${hwRow('Form Factor', ram.form_factor)}${hwRow('Slots', ram.slots)}
            </div>
            <div class="hw-panel hp-disk">
                <div class="hw-panel-head"><div class="hw-panel-ico">▦</div><div class="hw-panel-title">Storage</div><span class="hw-panel-tag">${disks.length} Vol</span></div>
                ${diskHtml}
            </div>
            <div class="hw-panel hp-sys">
                <div class="hw-panel-head"><div class="hw-panel-ico">◳</div><div class="hw-panel-title">System</div><span class="hw-panel-tag">OS</span></div>
                ${hwRow('Operating System', sys.os)}${hwRow('Hostname', sys.hostname)}${hwRow('Architecture', sys.arch)}${hwRow('Kernel', sys.kernel)}${hwRow('Total Storage', hw.total_storage)}
            </div>
            <div class="hw-panel hp-mobo">
                <div class="hw-panel-head"><div class="hw-panel-ico">◫</div><div class="hw-panel-title">Motherboard</div><span class="hw-panel-tag">BIOS</span></div>
                ${hwRow('Board', bios.board)}${hwRow('BIOS Version', bios.bios)}${hwRow('Serial', bios.serial)}
            </div>
            <div class="hw-panel hp-display">
                <div class="hw-panel-head"><div class="hw-panel-ico">◷</div><div class="hw-panel-title">Display</div><span class="hw-panel-tag">${(disp.monitors || []).length} Mon</span></div>
                ${hwRow('Screen Size', disp.screen_size)}${hwRow('Resolution', disp.primary_resolution)}${hwRow('Refresh Rate', disp.refresh_rate)}${hwRow('Adapter', disp.adapter)}
                <div style="margin-top:8px;border-top:1px solid rgba(255,255,255,0.06)">${monitorHtml || hwRow('No monitor info', '')}</div>
            </div>
            <div class="hw-panel hp-audio">
                <div class="hw-panel-head"><div class="hw-panel-ico">♪</div><div class="hw-panel-title">Audio</div><span class="hw-panel-tag">${(audio.devices || []).length} Dev</span></div>
                ${hwRow('Primary Device', audio.primary_device)}${hwRow('Manufacturer', audio.manufacturer)}
                <div style="margin-top:8px;border-top:1px solid rgba(255,255,255,0.06)">${audioHtml || hwRow('No audio devices', '')}</div>
            </div>
            <div class="hw-panel hp-batt">
                <div class="hw-panel-head"><div class="hw-panel-ico">▮</div><div class="hw-panel-title">Battery</div><span class="hw-panel-tag">Specs</span></div>
                ${hwRow('Name', bat.name)}${hwRow('Manufacturer', bat.manufacturer)}${hwRow('Chemistry', bat.chemistry)}${hwRow('Design Capacity', bat.design_capacity)}${hwRow('Full Charge Capacity', bat.full_charge_capacity)}${hwRow('Serial Number', bat.serial_number)}${hwRow('Design Voltage', bat.design_voltage)}
            </div>
        </div>
    </div>`;
}

function wireHardware() {
    const pdfBtn = document.getElementById('pdfBtn');
    if (pdfBtn) pdfBtn.addEventListener('click', exportPdf);
}

async function exportPdf() {
    toast('Generating PDF…');
    try {
        const res = await api('/export/pdf', { method: 'POST' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'BloomPlay_Hardware.pdf';
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
        toast('PDF downloaded');
    } catch {
        toast('PDF export failed', 'err');
    }
}

function renderScreenshots(data) {
    const shots = (data && data.screenshots) || [];
    const folder = (data && data.folder) || '';
    const total = (data && data.total) || shots.length;

    const gallery = shots.length ? `<div class="gallery">
        ${shots.map(s => `
            <div class="shot" data-name="${esc(s.name)}">
                <img src="${shotImgSrc(s.name)}" alt="${esc(s.name)}" loading="lazy">
                <div class="shot-meta">
                    <span class="shot-time">${new Date(s.mtime * 1000).toLocaleString()}</span>
                    <button class="shot-del" data-del="${esc(s.name)}">✕</button>
                </div>
            </div>`).join('')}
    </div>` : `
    <div class="empty-state">
        <div class="es-ico">◉</div>
        <h3>No screenshots yet</h3>
        <p>Capture a full screen or active window to build your gallery.</p>
    </div>`;

    return `
    <div class="card">
        <div class="card-head">
            <div class="card-ico c3">◉</div>
            <div class="card-title">Capture</div>
            <span class="card-sub">Saved on the PC</span>
        </div>
        <div class="ss-toolbar">
            <button class="btn btn-primary" id="shotFull">◉ Capture Full Screen</button>
            <button class="btn" id="shotWin">▢ Capture Active Window</button>
            <button class="btn" id="shotRefresh">⟳ Refresh</button>
            <span class="ss-folder" title="${esc(folder)}">📁 ${esc(folder || 'Screenshot folder')}</span>
            <span class="ss-count-badge">${total} ${total === 1 ? 'screenshot' : 'screenshots'}</span>
        </div>
        ${gallery}
    </div>`;
}

function wireScreenshots() {
    const fullBtn = document.getElementById('shotFull');
    const winBtn = document.getElementById('shotWin');
    const refresh = document.getElementById('shotRefresh');
    if (fullBtn) fullBtn.addEventListener('click', () => captureShot('full'));
    if (winBtn) winBtn.addEventListener('click', () => captureShot('window'));
    if (refresh) refresh.addEventListener('click', loadShots);

    document.querySelectorAll('.shot').forEach(shot => {
        shot.addEventListener('click', (e) => {
            if (e.target.closest('.shot-del')) return;
            openLightbox(shot.querySelector('img').src);
        });
    });
    document.querySelectorAll('.shot-del').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.del;
            confirmBox('Delete screenshot?', `This permanently removes "${name}" from the PC.`, () => deleteShot(name));
        });
    });
}

async function captureShot(kind) {
    toast('Capturing…');
    try {
        const res = await api('/screenshot/capture', { method: 'POST', body: JSON.stringify({ kind }) });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const d = await res.json();
        toast('Saved: ' + d.name);
        loadShots();
    } catch {
        toast('Capture failed', 'err');
    }
}

async function deleteShot(name) {
    try {
        const res = await api('/screenshot/delete', { method: 'POST', body: JSON.stringify({ name }) });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        toast('Deleted');
        loadShots();
    } catch {
        toast('Delete failed', 'err');
    }
}

function renderDevices(data) {
    const devices = (data && data.devices) || [];
    const blocked = (data && data.blocked) || [];

    const devHtml = devices.length ? devices.map(d => {
        const since = Math.floor(num(d.connected_since) / 60) * 60;
        return `
        <div class="dev-row">
            <div class="dev-ico">${(d.user_agent || '').toLowerCase().includes('mobile') ? '📱' : '💻'}</div>
            <div class="dev-info">
                <div class="dev-ip">${esc(d.ip)}</div>
                <div class="dev-ua">${esc(d.user_agent || 'Unknown device')}</div>
                <div class="dev-since">Connected ${new Date(since * 1000).toLocaleString()}</div>
            </div>
            <button class="btn btn-danger btn-sm" data-disc="${esc(d.ip)}">Disconnect</button>
        </div>`;
    }).join('') : `
        <div class="empty-state">
            <div class="es-ico">⌘</div>
            <h3>No devices connected</h3>
            <p>Open the dashboard on another device to see it here.</p>
        </div>`;

    const blockHtml = blocked.length ? `
    <div class="card">
        <div class="card-head"><div class="card-ico c4">⊘</div><div class="card-title">Blocked Devices</div></div>
        ${blocked.map(b => {
            const rem = Math.ceil(num(b.remaining_seconds) / 10) * 10;
            return `
            <div class="dev-row">
                <div class="dev-ico">⊘</div>
                <div class="dev-info">
                    <div class="dev-ip">${esc(b.ip)}</div>
                    <div class="dev-since">Blocked for ${rem}s more</div>
                </div>
                <button class="btn btn-sm" data-unblock="${esc(b.ip)}">Unblock</button>
            </div>`;
        }).join('')}
    </div>` : '';

    return `
    <div class="card">
        <div class="card-head">
            <div class="card-ico c2">⌘</div>
            <div class="card-title">Connected Devices</div>
            <span class="card-sub">${devices.length} active</span>
        </div>
        ${devHtml}
    </div>
    ${blockHtml}`;
}

function wireDevices() {
    document.querySelectorAll('[data-disc]').forEach(btn => {
        btn.addEventListener('click', () => {
            const ip = btn.dataset.disc;
            confirmBox('Disconnect device?', `"${ip}" will be disconnected and blocked for 60 seconds.`, async () => {
                try {
                    await api('/devices/disconnect?ip=' + encodeURIComponent(ip), { method: 'POST' });
                    toast('Disconnected');
                    loadDevices();
                } catch { toast('Failed', 'err'); }
            });
        });
    });
    document.querySelectorAll('[data-unblock]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const ip = btn.dataset.unblock;
            try {
                await api('/devices/unblock?ip=' + encodeURIComponent(ip), { method: 'POST' });
                toast('Unblocked');
                loadDevices();
            } catch { toast('Failed', 'err'); }
        });
    });
}

function renderSettings(cfg) {
    if (!cfg) return '';
    const fields = cfg.available_fields || [];
    const positions = cfg.available_positions || ['top-left', 'top-right', 'bottom-left', 'bottom-right'];
    const fonts = cfg.available_fonts || [];
    const sel = new Set(cfg.fields || []);

    const swatches = OVERLAY_COLORS.map(c =>
        `<button class="swatch ${cfg.color === c ? 'selected' : ''}" data-color="${c}" style="background:${c}"></button>`).join('');

    const posCells = positions.map(p => {
        const abbr = p.split('-').map(s => s[0]).join('');
        return `<button class="pos-cell ${abbr} ${cfg.position === p ? 'selected' : ''}" data-pos="${p}"></button>`;
    }).join('');

    const chips = fields.map(([key, label]) => `
        <button class="chip ${sel.has(key) ? 'selected' : ''}" data-field="${key}">
            <span class="tick">✓</span>${esc(label)}
        </button>`).join('');

    const fontOpts = fonts.map(f => {
        const label = f.split(',')[0].replace(/'/g, '').trim();
        return `<option value="${esc(f)}" ${cfg.font_family === f ? 'selected' : ''} style="font-family:${esc(f)}">${esc(label)}</option>`;
    }).join('');

    return `
    <div class="card">
        <div class="card-head"><div class="card-ico c1">◈</div><div class="card-title">Overlay</div><span class="card-sub">Live on the PC</span></div>
        <div class="settings-group">
            <div class="set-row">
                <div><div class="set-label">Enable in-game overlay</div><div class="set-desc">Shows live stats in a screen corner</div></div>
                <button class="toggle ${cfg.enabled ? 'on' : ''}" id="ovToggle"></button>
            </div>
            <div class="set-row">
                <div><div class="set-label">Accent color</div><div class="set-desc">Overlay text & bars color</div></div>
                <div class="swatches">${swatches}
                    <input type="color" class="swatch swatch-custom" id="ovCustomColor" value="${esc(cfg.color)}">
                </div>
            </div>
            <div class="set-row">
                <div><div class="set-label">Custom color (hex)</div><div class="set-desc">Type a hex code like #ff6b9d</div></div>
                <input type="text" class="hex-input" id="ovColorHex" value="${esc(cfg.color)}" maxlength="7" spellcheck="false" placeholder="#7c6cff">
            </div>
            <div class="set-row">
                <div><div class="set-label">Position</div><div class="set-desc">Where the overlay sits</div></div>
                <div class="pos-grid">${posCells}</div>
            </div>
            <div class="set-row">
                <div><div class="set-label">Text size</div><div class="set-desc">Overlay font size</div></div>
                <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                    <span class="range-val" id="ovSizeVal">${cfg.font_size}</span>
                    <input type="range" min="10" max="28" value="${cfg.font_size}" class="range" id="ovSize">
                </div>
            </div>
            <div class="set-row">
                <div><div class="set-label">Font family</div><div class="set-desc">Overlay font — pick from the list</div></div>
                <div class="font-col">
                    <select class="select font-select" id="ovFont">${fontOpts}</select>
                    <div class="font-sample" id="ovFontSample" style="font-family:${esc(cfg.font_family)}">AaBbCc 0123 — overlay sample</div>
                </div>
            </div>
            <div class="set-row">
                <div><div class="set-label">Show / hide hotkey</div><div class="set-desc">Press this combo to toggle the overlay in-game</div></div>
                <div class="hotkey-wrap">
                    <input type="text" class="hotkey-input" id="ovHotkey" value="${esc(cfg.hotkey || 'Ctrl+Shift+O')}" maxlength="40" spellcheck="false" placeholder="Ctrl+Shift+O">
                    <button class="btn btn-sm btn-primary" id="ovHotkeySave">Save</button>
                </div>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card-head"><div class="card-ico c3">▦</div><div class="card-title">Overlay Fields</div>
            <button class="btn btn-sm" id="ovAll">All</button>
            <button class="btn btn-sm" id="ovNone">Clear</button>
        </div>
        <div class="chips-meta" id="ovChipsMeta"></div>
        <div class="chips">${chips}</div>
    </div>

    <div class="card">
        <div class="card-head"><div class="card-ico c4">⏻</div><div class="card-title">Remote Control</div><span class="card-sub">Danger zone</span></div>
        <div class="set-row">
            <div><div class="set-label">Shut down BloomPlay</div><div class="set-desc">Closes the app, overlay, API and this dashboard on the PC</div></div>
            <button class="btn btn-danger" id="quitBtn">Shutdown</button>
        </div>
    </div>`;
}

function refreshFontSample() {
    const sample = document.getElementById('ovFontSample');
    if (sample && overlayCfg && overlayCfg.font_family) sample.style.fontFamily = overlayCfg.font_family;
}

function applyOverlayLocal() {
    if (!overlayCfg) return;
    const cfg = overlayCfg;

    const toggle = document.getElementById('ovToggle');
    if (toggle) toggle.className = 'toggle ' + (cfg.enabled ? 'on' : '');

    document.querySelectorAll('.swatch[data-color]').forEach(sw => {
        sw.classList.toggle('selected', sw.dataset.color === cfg.color);
    });
    const custom = document.getElementById('ovCustomColor');
    if (custom && document.activeElement !== custom) custom.value = cfg.color || '#7c6cff';
    const hex = document.getElementById('ovColorHex');
    if (hex && document.activeElement !== hex) hex.value = cfg.color || '#7c6cff';

    document.querySelectorAll('.pos-cell').forEach(cell => {
        cell.classList.toggle('selected', cell.dataset.pos === cfg.position);
    });

    const size = document.getElementById('ovSize');
    const sizeVal = document.getElementById('ovSizeVal');
    if (size) size.value = cfg.font_size || 14;
    if (sizeVal) sizeVal.textContent = cfg.font_size || 14;

    const font = document.getElementById('ovFont');
    if (font && document.activeElement !== font && cfg.font_family) {
        if (Array.from(font.options).some(o => o.value === cfg.font_family)) {
            font.value = cfg.font_family;
        } else if (font.options.length) {
            font.value = font.options[0].value;
        }
    }

    const hotkey = document.getElementById('ovHotkey');
    if (hotkey && document.activeElement !== hotkey && cfg.hotkey) hotkey.value = cfg.hotkey;

    document.querySelectorAll('.chip').forEach(chip => {
        chip.classList.toggle('selected', (cfg.fields || []).includes(chip.dataset.field));
    });

    const meta = document.getElementById('ovChipsMeta');
    if (meta) meta.textContent = `${(cfg.fields || []).length} of ${(cfg.available_fields || []).length} fields shown`;

    refreshFontSample();
}

function wireSettings() {
    const toggle = document.getElementById('ovToggle');
    if (toggle) toggle.addEventListener('click', () => {
        overlayCfg.enabled = !overlayCfg.enabled;
        toggle.className = 'toggle ' + (overlayCfg.enabled ? 'on' : '');
        patchOverlay({ enabled: overlayCfg.enabled });
    });

    document.querySelectorAll('.swatch[data-color]').forEach(sw => {
        sw.addEventListener('click', () => {
            overlayCfg.color = sw.dataset.color;
            document.querySelectorAll('.swatch[data-color]').forEach(s => s.classList.toggle('selected', s.dataset.color === overlayCfg.color));
            refreshFontSample();
            patchOverlay({ color: overlayCfg.color });
        });
    });

    const custom = document.getElementById('ovCustomColor');
    if (custom) custom.addEventListener('input', () => {
        overlayCfg.color = custom.value;
        const hex = document.getElementById('ovColorHex');
        if (hex) hex.value = custom.value;
        document.querySelectorAll('.swatch[data-color]').forEach(s => s.classList.toggle('selected', false));
        refreshFontSample();
        patchOverlay({ color: custom.value });
    });

    const hex = document.getElementById('ovColorHex');
    if (hex) {
        hex.addEventListener('input', () => {
            const v = hex.value.trim();
            if (!/^#[0-9a-fA-F]{6}$/.test(v)) return;
            overlayCfg.color = v;
            document.querySelectorAll('.swatch[data-color]').forEach(s => s.classList.toggle('selected', false));
            refreshFontSample();
        });
        hex.addEventListener('change', () => {
            let v = hex.value.trim();
            if (!/^#[0-9a-fA-F]{6}$/.test(v)) {
                toast('Invalid hex code', 'err');
                hex.value = overlayCfg.color || '#7c6cff';
                return;
            }
            overlayCfg.color = v;
            const customColor = document.getElementById('ovCustomColor');
            if (customColor) customColor.value = v;
            document.querySelectorAll('.swatch[data-color]').forEach(s => s.classList.toggle('selected', false));
            refreshFontSample();
            patchOverlay({ color: v });
        });
    }

    document.querySelectorAll('.pos-cell').forEach(cell => {
        cell.addEventListener('click', () => {
            overlayCfg.position = cell.dataset.pos;
            document.querySelectorAll('.pos-cell').forEach(c => c.classList.toggle('selected', c.dataset.pos === overlayCfg.position));
            refreshFontSample();
            patchOverlay({ position: overlayCfg.position });
        });
    });

    const size = document.getElementById('ovSize');
    const sizeVal = document.getElementById('ovSizeVal');
    if (size) size.addEventListener('input', () => {
        overlayCfg.font_size = Number(size.value);
        if (sizeVal) sizeVal.textContent = size.value;
        refreshFontSample();
        patchOverlay({ font_size: Number(size.value) });
    });

    const font = document.getElementById('ovFont');
    if (font) font.addEventListener('change', () => {
        overlayCfg.font_family = font.value;
        refreshFontSample();
        patchOverlay({ font_family: font.value });
    });

    const hotkey = document.getElementById('ovHotkey');
    const hotkeySave = document.getElementById('ovHotkeySave');
    if (hotkey && hotkeySave) hotkeySave.addEventListener('click', () => {
        let v = hotkey.value.trim();
        if (!v) { toast('Hotkey cannot be empty', 'err'); return; }
        overlayCfg.hotkey = v;
        toast('Hotkey saved: ' + v);
        patchOverlay({ hotkey: v });
    });

    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const key = chip.dataset.field;
            const fields = overlayCfg.fields || [];
            const i = fields.indexOf(key);
            if (i >= 0) fields.splice(i, 1); else fields.push(key);
            overlayCfg.fields = fields;
            applyOverlayLocal();
            patchOverlay({ fields });
        });
    });

    const allBtn = document.getElementById('ovAll');
    if (allBtn) allBtn.addEventListener('click', () => {
        overlayCfg.fields = (overlayCfg.available_fields || []).map(f => f[0]);
        applyOverlayLocal();
        patchOverlay({ fields: overlayCfg.fields });
    });
    const noneBtn = document.getElementById('ovNone');
    if (noneBtn) noneBtn.addEventListener('click', () => {
        overlayCfg.fields = [];
        applyOverlayLocal();
        patchOverlay({ fields: [] });
    });

    const quitBtn = document.getElementById('quitBtn');
    if (quitBtn) quitBtn.addEventListener('click', () => {
        confirmBox('Shut down BloomPlay?', 'This closes the app, overlay, API and dashboard on the PC.', async () => {
            try {
                await api('/shutdown', { method: 'POST' });
                toast('Shutting down…');
            } catch { toast('Failed', 'err'); }
        });
    });
}

async function patchOverlay(patch) {
    try {
        const res = await api('/overlay/config', { method: 'POST', body: JSON.stringify(patch) });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const updated = await res.json();
        Object.assign(overlayCfg, updated);
        applyOverlayLocal();
    } catch {
        toast('Could not save setting', 'err');
    }
}

let offlineShown = false;

function offlineHtml() {
    return `<div class="offline-wrap">
        <div class="o-ico">📡</div>
        <h2>Can't reach the PC</h2>
        <p>BloomPlay seems offline. Make sure it's running on your PC and both devices are on the same network.</p>
        <button class="btn btn-primary" onclick="location.reload()">Retry</button>
    </div>`;
}

function showOffline() {
    if (offlineShown) return;
    offlineShown = true;
    viewEl.innerHTML = offlineHtml();
}

async function loadStats() {
    try {
        const res = await api('/stats');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        setOnline(true);
        offlineShown = false;
        if (!overviewBuilt || !document.getElementById('perfChart')) {
            viewEl.innerHTML = buildOverview();
            overviewBuilt = true;
        }
        updateOverview(data);
    } catch {
        setOnline(false);
        if (currentView === 'overview') showOffline();
    }
}

async function loadHardware() {
    try {
        const res = await api('/hardware');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const fresh = await res.json();
        if (JSON.stringify(fresh) !== JSON.stringify(hardwareCache)) {
            hardwareCache = fresh;
            viewEl.innerHTML = renderHardware(fresh);
            wireHardware();
        } else {
            hardwareCache = fresh;
        }
    } catch {
        setOnline(false);
        if (currentView === 'hardware') showOffline();
    }
}

async function loadShots() {
    try {
        const res = await api('/screenshot/list');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        const key = JSON.stringify(data);
        if (key !== shotsCache) {
            shotsCache = key;
            viewEl.innerHTML = renderScreenshots(data);
            wireScreenshots();
        }
    } catch {
        setOnline(false);
        if (currentView === 'screenshots') showOffline();
    }
}

async function loadDevices() {
    try {
        const [dRes, bRes] = await Promise.all([api('/devices'), api('/devices/blocked')]);
        if (!dRes.ok || !bRes.ok) throw new Error('HTTP ' + dRes.status);
        const devices = await dRes.json();
        const blocked = await bRes.json();
        const devList = (devices && devices.devices) || [];
        const blockList = (blocked && blocked.blocked) || [];
        const key = JSON.stringify({
            devices: devList.map(d => ({ ip: d.ip, ua: d.user_agent, since: Math.floor(num(d.connected_since) / 60) * 60 })),
            blocked: blockList.map(b => ({ ip: b.ip, rem: Math.ceil(num(b.remaining_seconds) / 10) * 10 })),
        });
        if (key !== devicesCache) {
            devicesCache = key;
            viewEl.innerHTML = renderDevices({ devices: devList, blocked: blockList });
            wireDevices();
        }
    } catch {
        setOnline(false);
        if (currentView === 'devices') showOffline();
    }
}

async function loadSettings() {
    try {
        const res = await api('/overlay/config');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const cfg = await res.json();
        overlayCfg = cfg;
        if (!settingsBuilt || !document.getElementById('ovToggle')) {
            viewEl.innerHTML = renderSettings(cfg);
            settingsBuilt = true;
            wireSettings();
        }
        applyOverlayLocal();
    } catch {
        setOnline(false);
        if (currentView === 'settings') showOffline();
    }
}

async function loadSystem() {
    try {
        const res = await api('/system');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const s = await res.json();
        if (s.hostname) hostName.textContent = s.hostname;
        setOnline(true);
    } catch { setOnline(false); }
}

function setView(view) {
    if (view === currentView && viewEl.innerHTML) return;
    currentView = view;
    offlineShown = false;
    overviewBuilt = false;
    settingsBuilt = false;
    hardwareCache = null;
    shotsCache = null;
    devicesCache = null;
    NAV_ITEMS.forEach(item => item.classList.toggle('active', item.dataset.view === view));
    const meta = VIEW_META[view];
    pageTitle.textContent = meta.title;
    pageSub.textContent = meta.sub;
    startPolling();
}

function startPolling() {
    clearInterval(pollTimer);
    pollTimer = setInterval(poll, 1000);
    poll();
}

function poll() {
    if (currentView === 'overview') loadStats();
    else if (currentView === 'hardware') loadHardware();
    else if (currentView === 'screenshots') loadShots();
    else if (currentView === 'devices') loadDevices();
    else if (currentView === 'settings') loadSettings();
}

NAV_ITEMS.forEach(item => item.addEventListener('click', () => setView(item.dataset.view)));

(function init() {
    fmtClock();
    loadSystem();
    setView('overview');
})();
