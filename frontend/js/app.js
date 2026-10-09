// Main Application Controller & WebSocket Hub

// Global API Base Handler for Vercel & Remote Deployments
window.__API_BASE__ = localStorage.getItem("smart_cctv_api_base") || (window.location.hostname.includes("vercel.app") ? "http://localhost:8000" : "");

const _originalFetch = window.fetch;
window.fetch = function(url, options) {
    if (typeof url === "string" && (url.startsWith("/api/") || url.startsWith("/storage/"))) {
        const base = window.__API_BASE__ || "";
        url = base + url;
    }
    return _originalFetch.call(this, url, options);
};

function getApiBaseUrl() {
    return window.__API_BASE__ || "";
}

function promptSetApiBase() {
    const current = window.__API_BASE__ || "http://localhost:8000";
    const newBase = prompt("Masukkan URL Host Backend CCTV API (contoh: http://localhost:8000 atau https://cctv-server.domain.com):", current);
    if (newBase !== null) {
        const sanitized = newBase.trim().replace(/\/+$/, "");
        localStorage.setItem("smart_cctv_api_base", sanitized);
        window.__API_BASE__ = sanitized;
        window.location.reload();
    }
}

let currentTab = "liveViewTab";
let ws = null;
let systemMetricsTimer = null;
let overlayStates = {}; // camId -> boolean (true: HUD, false: raw)
let vmsClips = [];
let currentClipId = null;
let currentUser = JSON.parse(localStorage.getItem("smart_cctv_user") || '{"username":"admin","full_name":"Super Administrator","role":"ADMIN","token":""}');

document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

async function initApp() {
    initAuthRbac();
    setupTabNavigation();
    initWebSocket();
    startSystemMetricsPolling();
    loadLiveFeeds();

    // Hook forms
    const addCamForm = document.getElementById("addCameraForm");
    if (addCamForm) addCamForm.addEventListener("submit", handleAddCameraSubmit);

    const editCamForm = document.getElementById("editCameraForm");
    if (editCamForm) editCamForm.addEventListener("submit", handleEditCameraSubmit);

    const addVehForm = document.getElementById("addVehicleForm");
    if (addVehForm) addVehForm.addEventListener("submit", submitNewVehicleRegistry);

    // Setup timeline canvas resize listener
    window.addEventListener("resize", () => {
        if (currentTab === "playbackTab" && vmsClips.length > 0) {
            renderTimelineScrubber();
        }
    });
}

function setupTabNavigation() {
    const navItems = document.querySelectorAll(".nav-tab-btn");
    navItems.forEach(btn => {
        btn.addEventListener("click", () => {
            const target = btn.dataset.tab;
            switchTab(target);
        });
    });
}

function switchTab(tabId) {
    currentTab = tabId;

    // Toggle nav active styles
    document.querySelectorAll(".nav-tab-btn").forEach(btn => {
        if (btn.dataset.tab === tabId) {
            btn.classList.add("bg-sky-500/15", "text-sky-400", "border-sky-500/40");
            btn.classList.remove("text-slate-400", "hover:bg-slate-800/60");
        } else {
            btn.classList.remove("bg-sky-500/15", "text-sky-400", "border-sky-500/40");
            btn.classList.add("text-slate-400", "hover:bg-slate-800/60");
        }
    });

    // Toggle views
    document.querySelectorAll(".tab-content-panel").forEach(panel => {
        if (panel.id === tabId) {
            panel.classList.remove("hidden");
        } else {
            panel.classList.add("hidden");
        }
    });

    // Stream connection management: release HTTP/1.1 connections when leaving liveViewTab
    if (tabId !== "liveViewTab") {
        document.querySelectorAll(".cam-stream-img").forEach(img => {
            if (img.src && !img.src.includes("no_signal.png") && !img.dataset.streamSrc) {
                img.dataset.streamSrc = img.src;
            }
            img.src = "/assets/no_signal.png";
        });
    } else {
        document.querySelectorAll(".cam-stream-img").forEach(img => {
            if (img.dataset.streamSrc) {
                img.src = img.dataset.streamSrc;
            }
        });
    }

    // Trigger tab specific inits
    if (tabId === "canvasStudioTab") {
        initCanvasStudio();
    } else if (tabId === "analyticsTab") {
        initAnalyticsCharts();
    } else if (tabId === "anprTab") {
        initAnprModule();
    } else if (tabId === "alertsTab") {
        loadAlertsHistory();
    } else if (tabId === "playbackTab") {
        initVmsPlaybackTab();
    } else if (tabId === "settingsTab") {
        loadSettingsCameras();
        loadServerSettings();
        loadStorageStatus();
        loadGcsConfig();
        loadAuditLogs();
    } else if (tabId === "liveViewTab") {
        loadLiveFeeds();
    }
}

// WebSocket Connection
function initWebSocket() {
    let wsUrl;
    const base = getApiBaseUrl();
    if (base) {
        const clean = base.replace(/^http/, base.startsWith("https") ? "wss" : "ws");
        wsUrl = `${clean}/ws/events`;
    } else {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsUrl = `${protocol}//${window.location.host}/ws/events`;
    }

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log("[WS] Connected to live event stream");
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleIncomingLiveEvent(data);
        } catch (e) {
            console.error("WS parse error:", e);
        }
    };

    ws.onclose = () => {
        console.warn("[WS] Disconnected, retrying in 3s...");
        setTimeout(initWebSocket, 3000);
    };
}

function handleIncomingLiveEvent(data) {
    if (data.type === "ALERT") {
        // Trigger sound
        playSecurityAlarm();

        // Show Red Alarm Banner
        showEmergencyBanner(data.message);

        // Refresh alert history if on alerts tab
        if (currentTab === "alertsTab") {
            loadAlertsHistory();
        }
        if (currentTab === "anprTab") {
            fetchAnprLogs();
        }
    }
}

function showEmergencyBanner(message) {
    const banner = document.getElementById("emergencyAlertBanner");
    const msgEl = document.getElementById("emergencyAlertMsg");
    if (!banner || !msgEl) return;

    msgEl.innerText = message;
    banner.classList.remove("hidden");

    setTimeout(() => {
        banner.classList.add("hidden");
    }, 7000);
}

// Live Video Streams
async function loadLiveFeeds() {
    try {
        const res = await fetch("/api/cameras");
        const cameras = await res.json();
        const grid = document.getElementById("liveFeedsGrid");
        if (!grid) return;

        if (cameras.length === 0) {
            grid.innerHTML = `
                <div class="col-span-full py-16 text-center text-slate-400 bg-slate-900/40 rounded-2xl border border-dashed border-slate-700">
                    <p class="text-base font-semibold">Belum ada kamera yang didaftarkan.</p>
                    <button onclick="openModal('addCameraModal')" class="mt-3 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-sm font-semibold transition">
                        + Tambah Kamera Pertama
                    </button>
                </div>
            `;
            return;
        }

        grid.innerHTML = cameras.map(cam => {
            const classBadges = (cam.target_classes || []).map(c => {
                const mapNames = { car: '🚗 Mobil', motorcycle: '🛵 Motor', person: '🚶 Orang', bus: '🚌 Bus', truck: '🚛 Truk', bicycle: '🚲 Sepeda' };
                return `<span class="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300 border border-slate-700">${mapNames[c] || c}</span>`;
            }).join(" ");

            const isOverlay = overlayStates[cam.id] !== false;
            const isStreamOn = cam.is_enabled !== false;
            const isAiOn = cam.ai_enabled !== false;
            const base = getApiBaseUrl();
            const streamUrl = isStreamOn ? (isOverlay ? `${base}/api/cameras/${cam.id}/stream` : `${base}/api/cameras/${cam.id}/stream?overlay=false`) : '/assets/no_signal.png';

            return `
            <div class="bg-slate-900/90 rounded-2xl border border-slate-700/60 overflow-hidden shadow-xl flex flex-col group relative">
                <div class="px-4 py-2.5 bg-slate-800/80 border-b border-slate-700/60 flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full ${isStreamOn ? (cam.status === 'ONLINE' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500') : 'bg-slate-500'}"></span>
                        <h3 class="font-bold text-sm text-slate-100 tracking-wide">${cam.name}</h3>
                        ${!isStreamOn ? '<span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-semibold border border-amber-500/30">STREAM OFF</span>' : ''}
                        ${!isAiOn ? '<span class="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px] font-semibold border border-purple-500/30">AI BYPASS</span>' : ''}
                    </div>
                    <div class="flex items-center gap-2 text-xs">
                        <button onclick="toggleCameraOverlay('${cam.id}')" id="overlayBtn-${cam.id}" class="px-2 py-1 rounded ${isOverlay ? 'bg-sky-600/30 text-sky-400 border border-sky-500/40 hover:bg-sky-600/50' : 'bg-slate-700/60 text-slate-300 border border-slate-600 hover:bg-slate-600'} text-[11px] font-semibold transition" title="Toggle Clean Raw vs AI Overlay HUD">
                            ${isOverlay ? '👁️ HUD: ON' : '📷 Raw Clean'}
                        </button>
                        <button onclick="triggerManualClip('${cam.id}')" class="px-2 py-1 rounded bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 border border-rose-500/30 text-[11px] font-semibold transition flex items-center gap-1" title="Rekam Bukti Klip 20 Detik (10s Pre + 10s Post)">
                            🔴 Klip 20s
                        </button>
                        <span class="text-emerald-400 font-mono font-bold">${isStreamOn ? `${cam.current_fps} FPS` : '0 FPS'}</span>
                    </div>
                </div>
                <div class="relative bg-black aspect-video flex items-center justify-center overflow-hidden">
                    <img id="streamImg-${cam.id}" src="${streamUrl}" data-stream-src="${streamUrl}" class="cam-stream-img w-full h-full object-contain" alt="${cam.name}" onerror="this.src='/assets/no_signal.png'">
                    ${!isStreamOn ? `
                    <div class="absolute inset-0 bg-slate-950/85 backdrop-blur-[2px] flex flex-col items-center justify-center p-4 text-center">
                        <span class="text-3xl mb-1">⏸️</span>
                        <span class="text-sm font-bold text-slate-200">Ingestion Stream Dimatikan</span>
                        <span class="text-xs text-slate-400 mt-1 max-w-xs">Penerimaan video dihentikan sementara untuk menghemat bandwidth jaringan edge & CPU.</span>
                        <button onclick="toggleCameraStream('${cam.id}', true)" class="mt-3 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shadow transition">
                            ▶️ Aktifkan Stream Sekarang
                        </button>
                    </div>
                    ` : ''}
                </div>
                <div class="px-3 py-2 bg-slate-800/20 border-t border-slate-700/40 flex flex-wrap gap-1 items-center">
                    <span class="text-[11px] text-slate-400 mr-1">Deteksi AI:</span>
                    ${classBadges}
                </div>
                <div class="p-3 bg-slate-800/40 border-t border-slate-700/50 flex items-center justify-between text-xs text-slate-400">
                    <span>Model: <strong class="text-slate-200">${cam.assigned_model}</strong></span>
                    <div class="flex items-center gap-2">
                        <button onclick="analyzeCameraWithGemini('${cam.id}', '${cam.name.replace(/'/g, "\\'")}')" class="px-2 py-1 bg-gradient-to-r from-purple-600/30 to-indigo-600/30 hover:from-purple-600/50 hover:to-indigo-600/50 text-purple-300 border border-purple-500/40 rounded font-medium transition flex items-center gap-1 shadow-sm" title="Analisis Forensik Cerdas Frame Kamera ini dengan Gemini Vision">
                            ✨ Gemini AI
                        </button>
                        <button onclick="openEditCameraModal('${cam.id}')" class="text-slate-300 hover:text-white px-2 py-1 bg-slate-700/50 rounded font-medium transition rbac-admin-only">
                            ✏️ Edit
                        </button>
                        <button onclick="switchTab('canvasStudioTab'); selectStudioCamera('${cam.id}')" class="text-sky-400 hover:text-sky-300 font-medium rbac-admin-only">
                            📐 Garis Hitung ➔
                        </button>
                    </div>
                </div>
            </div>

            `;
        }).join("");
    } catch (e) {
        console.error("Error loading live feeds:", e);
    }
}

// Camera Management Handlers
async function handleAddCameraSubmit(e) {
    e.preventDefault();
    const name = document.getElementById("camNameInput").value.trim();
    const type = document.getElementById("camTypeSelect").value;
    const url = document.getElementById("camUrlInput").value.trim();
    const model = document.getElementById("camModelSelect").value;
    const fps = parseInt(document.getElementById("camFpsSelect").value) || 0;

    // Collect checked classes
    const checkedClasses = Array.from(document.querySelectorAll('input[name="addCamClass"]:checked')).map(cb => cb.value);

    try {
        const res = await fetch("/api/cameras", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                source_type: type,
                source_url: url,
                assigned_model: model,
                target_classes: checkedClasses.length > 0 ? checkedClasses : ["person", "car", "motorcycle", "bus", "truck", "bicycle"],
                fps_limit: fps
            })
        });

        if (res.ok) {
            closeModal("addCameraModal");
            document.getElementById("addCameraForm").reset();
            loadLiveFeeds();
            if (currentTab === "settingsTab") loadSettingsCameras();
        }
    } catch (err) {
        console.error("Add camera failed:", err);
    }
}

async function openEditCameraModal(camId) {
    try {
        const res = await fetch(`/api/cameras/${camId}`);
        if (!res.ok) return;
        const cam = await res.json();

        document.getElementById("editCamIdInput").value = cam.id;
        document.getElementById("editCamNameInput").value = cam.name;
        document.getElementById("editCamTypeSelect").value = cam.source_type;
        document.getElementById("editCamUrlInput").value = cam.source_url;
        document.getElementById("editCamModelSelect").value = cam.assigned_model;
        document.getElementById("editCamFpsSelect").value = cam.fps_limit !== undefined ? cam.fps_limit : 25;

        // Set checked classes
        const classes = cam.target_classes || [];
        document.querySelectorAll('input[name="editCamClass"]').forEach(cb => {
            cb.checked = classes.includes(cb.value);
        });

        openModal("editCameraModal");
    } catch (e) {
        console.error("Error fetching camera for edit:", e);
    }
}

async function handleEditCameraSubmit(e) {
    e.preventDefault();
    const camId = document.getElementById("editCamIdInput").value;
    const name = document.getElementById("editCamNameInput").value.trim();
    const type = document.getElementById("editCamTypeSelect").value;
    const url = document.getElementById("editCamUrlInput").value.trim();
    const model = document.getElementById("editCamModelSelect").value;
    const fps = parseInt(document.getElementById("editCamFpsSelect").value) || 0;

    const checkedClasses = Array.from(document.querySelectorAll('input[name="editCamClass"]:checked')).map(cb => cb.value);

    try {
        const res = await fetch(`/api/cameras/${camId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                source_type: type,
                source_url: url,
                assigned_model: model,
                target_classes: checkedClasses.length > 0 ? checkedClasses : ["person", "car", "motorcycle", "bus", "truck", "bicycle"],
                fps_limit: fps
            })
        });

        if (res.ok) {
            closeModal("editCameraModal");
            loadLiveFeeds();
            if (currentTab === "settingsTab") loadSettingsCameras();
        }
    } catch (err) {
        console.error("Update camera failed:", err);
    }
}

async function loadSettingsCameras() {
    const tbody = document.getElementById("settingsCamerasTableBody");
    if (!tbody) return;
    try {
        const res = await fetch("/api/cameras");
        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-rose-400">Gagal memuat kamera (${res.status})</td></tr>`;
            return;
        }
        const cameras = await res.json();
        if (!cameras || cameras.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-slate-500">Belum ada kamera terdaftar. Klik "+ Tambah Kamera Baru" di atas.</td></tr>`;
            return;
        }

        tbody.innerHTML = cameras.map(cam => {
            const classBadges = (cam.target_classes || []).map(c => {
                const mapNames = { car: 'Mobil', motorcycle: 'Motor', person: 'Orang', bus: 'Bus', truck: 'Truk', bicycle: 'Sepeda' };
                return `<span class="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300 border border-slate-700">${mapNames[c] || c}</span>`;
            }).join(" ");

            const fpsLabel = cam.fps_limit === 0 ? "Asli (Max)" : `${cam.fps_limit} FPS`;
            const isStreamOn = cam.is_enabled !== false;
            const isAiOn = cam.ai_enabled !== false;

            return `
            <tr class="border-b border-slate-700/50 hover:bg-slate-800/40">
                <td class="py-3 px-4">
                    <div class="font-semibold text-slate-200">${cam.name}</div>
                    <div class="flex flex-wrap gap-1 mt-1">${classBadges}</div>
                </td>
                <td class="py-3 px-4 text-xs font-mono text-slate-300">${cam.source_type}</td>
                <td class="py-3 px-4 text-xs">
                    <button onclick="toggleCameraStream('${cam.id}', ${!isStreamOn})" class="px-2.5 py-1 rounded-full text-xs font-semibold ${isStreamOn ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-600/30' : 'bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700'} transition rbac-admin-only">
                        ${isStreamOn ? '🟢 Stream Aktif' : '⏸️ Dinonaktifkan'}
                    </button>
                </td>
                <td class="py-3 px-4 text-xs">
                    <button onclick="toggleCameraAi('${cam.id}', ${!isAiOn})" class="px-2.5 py-1 rounded-full text-xs font-semibold ${isAiOn ? 'bg-purple-600/20 text-purple-400 border border-purple-500/40 hover:bg-purple-600/30' : 'bg-amber-600/20 text-amber-400 border border-amber-500/40 hover:bg-amber-600/30'} transition rbac-admin-only">
                        ${isAiOn ? '⚡ AI Aktif' : '💤 Standby (Hemat CPU)'}
                    </button>
                </td>
                <td class="py-3 px-4 text-xs text-sky-400 font-medium">${cam.assigned_model} (${fpsLabel})</td>
                <td class="py-3 px-4 text-xs">
                    <span class="px-2 py-0.5 rounded ${isStreamOn && cam.status === 'ONLINE' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700/60 text-slate-400'} font-bold">${isStreamOn ? cam.status : 'MUTED'}</span>
                </td>
                <td class="py-3 px-4 text-right whitespace-nowrap">
                    <button onclick="openEditCameraModal('${cam.id}')" class="text-xs text-sky-400 hover:text-sky-300 px-2.5 py-1 bg-sky-500/10 rounded-lg hover:bg-sky-500/20 mr-1.5 transition rbac-admin-only">✏️ Edit</button>
                    <button onclick="deleteCamera('${cam.id}')" class="text-xs text-rose-400 hover:text-rose-300 px-2.5 py-1 bg-rose-500/10 rounded-lg hover:bg-rose-500/20 transition rbac-admin-only">🗑️ Hapus</button>
                </td>
            </tr>
            `;
        }).join("");

        applyRbacPermissions();
    } catch (e) {
        console.error("Error loading settings cameras:", e);
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-rose-400">Gagal terhubung ke API server.</td></tr>`;
    }
}

function toggleCameraOverlay(camId) {
    overlayStates[camId] = !(overlayStates[camId] !== false);
    const isOverlay = overlayStates[camId];
    const img = document.getElementById(`streamImg-${camId}`);
    if (img) {
        const newSrc = isOverlay ? `/api/cameras/${camId}/stream` : `/api/cameras/${camId}/stream?overlay=false`;
        img.src = newSrc;
        img.dataset.streamSrc = newSrc;
    }
    const btn = document.getElementById(`overlayBtn-${camId}`);
    if (btn) {
        btn.innerHTML = isOverlay ? '👁️ HUD: ON' : '📷 Raw Clean';
        if (isOverlay) {
            btn.className = "px-2 py-1 rounded bg-sky-600/30 text-sky-400 border border-sky-500/40 hover:bg-sky-600/50 text-[11px] font-semibold transition";
        } else {
            btn.className = "px-2 py-1 rounded bg-slate-700/60 text-slate-300 border border-slate-600 hover:bg-slate-600 text-[11px] font-semibold transition";
        }
    }
}

async function toggleCameraStream(camId, enable) {
    try {
        const res = await fetch(`/api/cameras/${camId}/toggle-stream?enable=${enable}`, { method: "PATCH" });
        if (res.ok) {
            logAuditAction("TOGGLE_STREAM", "CAMERA", `Set camera ${camId} stream enabled=${enable}`);
            loadLiveFeeds();
            if (currentTab === "settingsTab") loadSettingsCameras();
        }
    } catch (e) {
        console.error("Toggle stream error:", e);
    }
}

async function toggleCameraAi(camId, enable) {
    try {
        const res = await fetch(`/api/cameras/${camId}/toggle-ai?enable=${enable}`, { method: "PATCH" });
        if (res.ok) {
            logAuditAction("TOGGLE_AI", "CAMERA", `Set camera ${camId} AI inference enabled=${enable}`);
            loadLiveFeeds();
            if (currentTab === "settingsTab") loadSettingsCameras();
        }
    } catch (e) {
        console.error("Toggle AI error:", e);
    }
}

async function triggerManualClip(camId) {
    showEmergencyBanner(`🔴 Perekaman bukti klip 20s dimulai. Mengompilasi buffer 10s pre-event...`);
    try {
        const res = await fetch(`/api/clips/trigger-manual?camera_id=${camId}`, { method: "POST" });
        const data = await res.json();
        logAuditAction("TRIGGER_CLIP", "VMS", `Manual clip recorded for camera ${camId}`);
        setTimeout(() => {
            if (currentTab === "playbackTab") fetchVmsClips();
        }, 3500);
    } catch (e) {
        console.error("Trigger manual clip error:", e);
    }
}

async function deleteCamera(camId) {
    if (!confirm("Hapus kamera ini dari sistem?")) return;
    try {
        await fetch(`/api/cameras/${camId}`, { method: "DELETE" });
        loadSettingsCameras();
        loadLiveFeeds();
    } catch (e) {
        console.error("Delete camera error:", e);
    }
}

// Alerts History
async function loadAlertsHistory() {
    try {
        const res = await fetch("/api/alerts/history?limit=30");
        const alerts = await res.json();
        const tbody = document.getElementById("alertsHistoryTableBody");
        if (!tbody) return;

        if (alerts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center py-6 text-slate-500">Belum ada peringatan keamanan terekam.</td></tr>`;
            return;
        }

        tbody.innerHTML = alerts.map(a => `
            <tr class="border-b border-slate-700/50 hover:bg-slate-800/40">
                <td class="py-3 px-3 text-xs text-slate-400">${a.timestamp || "-"}</td>
                <td class="py-3 px-3">
                    <span class="px-2 py-0.5 rounded text-xs font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">${a.rule_type}</span>
                </td>
                <td class="py-3 px-3 text-xs text-slate-200 font-medium">${a.message}</td>
                <td class="py-3 px-3">
                    ${a.snapshot_path ? `<img src="/storage/snapshots/${a.snapshot_path.split('/').pop()}" onclick="showImageModal(this.src)" class="h-8 w-12 object-cover rounded cursor-pointer border border-slate-700 hover:scale-110 transition shadow">` : '-'}
                </td>
            </tr>
        `).join("");
    } catch (e) {
        console.error("Error loading alert history:", e);
    }
}

async function triggerTestAlert() {
    try {
        await fetch("/api/alerts/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                rule_type: "MANUAL_TEST",
                message: "Uji coba sirine dan sistem peringatan darurat!"
            })
        });
    } catch (e) {
        console.error("Test alert error:", e);
    }
}

// System Resources Polling
function startSystemMetricsPolling() {
    fetchSystemMetrics();
    systemMetricsTimer = setInterval(fetchSystemMetrics, 3000);
}

async function fetchSystemMetrics() {
    try {
        const res = await fetch("/api/system/metrics");
        const data = await res.json();

        const cpuEl = document.getElementById("cpuMetricVal");
        const ramEl = document.getElementById("ramMetricVal");
        const gpuEl = document.getElementById("gpuMetricVal");
        const uptimeEl = document.getElementById("uptimeMetricVal");

        if (cpuEl) cpuEl.innerText = `${data.cpu_percent}%`;
        if (ramEl) ramEl.innerText = `${data.ram_percent}% (${data.ram_used_gb}/${data.ram_total_gb}GB)`;
        if (gpuEl) gpuEl.innerText = data.gpu_info;
        if (uptimeEl) uptimeEl.innerText = data.uptime;
    } catch (e) {
        // Silent fail
    }
}

// Modal Helpers
function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove("hidden");
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add("hidden");
}

function showImageModal(src) {
    const modal = document.getElementById("imageViewerModal");
    const img = document.getElementById("imageViewerModalImg");
    if (modal && img) {
        img.src = src;
        modal.classList.remove("hidden");
    }
}

// Server Configuration Management
async function loadServerSettings() {
    try {
        const res = await fetch("/api/system/settings");
        if (!res.ok) return;
        const cfg = await res.json();

        const srvProject = document.getElementById("srvProjectNameInput");
        const srvFps = document.getElementById("srvDefaultFpsSelect");
        const srvDetConf = document.getElementById("srvDetectionConfInput");
        const srvAnprConf = document.getElementById("srvAnprConfInput");
        const srvRet = document.getElementById("srvRetentionDaysInput");
        const srvTgToken = document.getElementById("srvTgTokenInput");
        const srvTgChat = document.getElementById("srvTgChatIdInput");
        const srvGeminiKey = document.getElementById("srvGeminiApiKeyInput");
        const srvGeminiModel = document.getElementById("srvGeminiModelSelect");

        if (srvProject) srvProject.value = cfg.project_name || "";
        if (srvFps) srvFps.value = cfg.default_stream_fps !== undefined ? cfg.default_stream_fps : 25;
        if (srvDetConf) srvDetConf.value = cfg.detection_conf_threshold || 0.35;
        if (srvAnprConf) srvAnprConf.value = cfg.anpr_conf_threshold || 0.30;
        if (srvRet) srvRet.value = cfg.data_retention_days || 30;
        if (srvTgToken) srvTgToken.value = cfg.telegram_bot_token || "";
        if (srvTgChat) srvTgChat.value = cfg.telegram_chat_id || "";
        if (srvGeminiKey) srvGeminiKey.value = cfg.gemini_api_key || "";
        if (srvGeminiModel && cfg.gemini_model) srvGeminiModel.value = cfg.gemini_model;

        const quickKey = document.getElementById("quickGeminiApiKeyInput");
        const quickModel = document.getElementById("quickGeminiModelSelect");
        if (quickKey) quickKey.value = cfg.gemini_api_key || "";
        if (quickModel && cfg.gemini_model) quickModel.value = cfg.gemini_model;
    } catch (e) {

        console.error("Failed to load server settings:", e);
    }
}

async function handleSaveServerSettings(e) {
    e.preventDefault();
    const statusEl = document.getElementById("serverSettingsStatus");
    if (statusEl) {
        statusEl.innerText = "Menyimpan pengaturan...";
        statusEl.className = "text-xs text-sky-400 font-semibold";
    }

    const payload = {
        project_name: document.getElementById("srvProjectNameInput")?.value.trim(),
        default_stream_fps: parseInt(document.getElementById("srvDefaultFpsSelect")?.value) || 0,
        detection_conf_threshold: parseFloat(document.getElementById("srvDetectionConfInput")?.value) || 0.35,
        anpr_conf_threshold: parseFloat(document.getElementById("srvAnprConfInput")?.value) || 0.30,
        data_retention_days: parseInt(document.getElementById("srvRetentionDaysInput")?.value) || 30,
        telegram_bot_token: document.getElementById("srvTgTokenInput")?.value.trim(),
        telegram_chat_id: document.getElementById("srvTgChatIdInput")?.value.trim(),
        gemini_api_key: document.getElementById("srvGeminiApiKeyInput")?.value.trim(),
        gemini_model: document.getElementById("srvGeminiModelSelect")?.value
    };

    try {
        const res = await fetch("/api/system/settings", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            if (statusEl) {
                statusEl.innerText = "✓ Pengaturan server berhasil disimpan!";
                statusEl.className = "text-xs text-emerald-400 font-semibold";
                setTimeout(() => { statusEl.innerText = ""; }, 4000);
            }
        } else {
            if (statusEl) {
                statusEl.innerText = "✗ Gagal menyimpan pengaturan.";
                statusEl.className = "text-xs text-rose-400 font-semibold";
            }
        }
    } catch (err) {
        console.error("Save server settings error:", err);
        if (statusEl) {
            statusEl.innerText = "✗ Terjadi kesalahan koneksi server.";
            statusEl.className = "text-xs text-rose-400 font-semibold";
        }
    }
}

function toggleGeminiKeyVisibility() {
    const input = document.getElementById("srvGeminiApiKeyInput");
    if (input) {
        input.type = input.type === "password" ? "text" : "password";
    }
}

async function testGeminiConnection() {
    const statusEl = document.getElementById("geminiConnectionStatus");
    const key = document.getElementById("srvGeminiApiKeyInput")?.value.trim();
    const model = document.getElementById("srvGeminiModelSelect")?.value;

    if (statusEl) {
        statusEl.classList.remove("hidden");
        statusEl.innerText = "⏳ Menghubungkan & menguji API Key ke Google AI Studio...";
        statusEl.className = "text-xs px-3 py-2 rounded-lg font-medium bg-purple-950/60 border border-purple-500/40 text-purple-300 block";
    }

    try {
        const res = await fetch("/api/system/test-gemini", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: key, model: model })
        });
        const result = await res.json();

        if (statusEl) {
            if (result.success) {
                statusEl.className = "text-xs px-3 py-2 rounded-lg font-medium bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 block";
                statusEl.innerText = "✓ " + result.message + (result.reply ? ` (Balasan: "${result.reply}")` : "");
            } else {
                statusEl.className = "text-xs px-3 py-2 rounded-lg font-medium bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
                statusEl.innerText = "✗ " + result.message;
            }
        }
    } catch (e) {
        if (statusEl) {
            statusEl.className = "text-xs px-3 py-2 rounded-lg font-medium bg-rose-950/60 border border-rose-500/40 text-rose-300 block";
            statusEl.innerText = "✗ Gagal terhubung ke server pengujian Gemini API.";
        }
    }
}

// Quick Gemini Modal Handlers
function toggleQuickGeminiKeyVisibility() {
    const input = document.getElementById("quickGeminiApiKeyInput");
    if (input) input.type = input.type === "password" ? "text" : "password";
}

async function testQuickGeminiConnection() {
    const statusEl = document.getElementById("quickGeminiStatusMsg");
    const key = document.getElementById("quickGeminiApiKeyInput")?.value.trim();
    const model = document.getElementById("quickGeminiModelSelect")?.value;

    if (statusEl) {
        statusEl.classList.remove("hidden");
        statusEl.innerText = "⏳ Menghubungkan & menguji API Key ke Google AI Studio...";
        statusEl.className = "text-xs p-2.5 rounded-xl font-medium bg-sky-50 border border-sky-200 text-sky-800 block";
    }

    try {
        const res = await fetch("/api/system/test-gemini", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: key, model: model })
        });
        const result = await res.json();

        if (statusEl) {
            if (result.success) {
                statusEl.className = "text-xs p-2.5 rounded-xl font-medium bg-emerald-50 border border-emerald-200 text-emerald-800 block";
                statusEl.innerText = "✓ " + result.message + (result.reply ? ` (Balasan: "${result.reply}")` : "");
            } else {
                statusEl.className = "text-xs p-2.5 rounded-xl font-medium bg-rose-50 border border-rose-200 text-rose-800 block";
                statusEl.innerText = "✗ " + result.message;
            }
        }
    } catch (e) {
        if (statusEl) {
            statusEl.className = "text-xs p-2.5 rounded-xl font-medium bg-rose-50 border border-rose-200 text-rose-800 block";
            statusEl.innerText = "✗ Gagal terhubung ke server pengujian Gemini API.";
        }
    }
}

async function handleQuickGeminiSave(e) {
    e.preventDefault();
    const statusEl = document.getElementById("quickGeminiStatusMsg");
    const key = document.getElementById("quickGeminiApiKeyInput")?.value.trim();
    const model = document.getElementById("quickGeminiModelSelect")?.value;

    if (statusEl) {
        statusEl.classList.remove("hidden");
        statusEl.innerText = "Menyimpan pengaturan...";
        statusEl.className = "text-xs p-2.5 rounded-xl font-medium bg-sky-50 text-sky-700 block";
    }

    try {
        const res = await fetch("/api/system/settings", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                gemini_api_key: key,
                gemini_model: model
            })
        });

        if (res.ok) {
            if (statusEl) {
                statusEl.className = "text-xs p-2.5 rounded-xl font-medium bg-emerald-50 border border-emerald-200 text-emerald-800 block";
                statusEl.innerText = "✓ Pengaturan Google Gemini berhasil disimpan!";
            }
            // Sync with settings tab
            const srvKey = document.getElementById("srvGeminiApiKeyInput");
            const srvModel = document.getElementById("srvGeminiModelSelect");
            if (srvKey) srvKey.value = key;
            if (srvModel) srvModel.value = model;

            setTimeout(() => {
                closeModal("geminiApiKeyModal");
                if (statusEl) statusEl.classList.add("hidden");
            }, 1200);
        } else {
            if (statusEl) {
                statusEl.className = "text-xs p-2.5 rounded-xl font-medium bg-rose-50 border border-rose-200 text-rose-800 block";
                statusEl.innerText = "✗ Gagal menyimpan pengaturan.";
            }
        }
    } catch (err) {
        if (statusEl) {
            statusEl.className = "text-xs p-2.5 rounded-xl font-medium bg-rose-50 border border-rose-200 text-rose-800 block";
            statusEl.innerText = "✗ Terjadi kesalahan koneksi server.";
        }
    }
}

function quickReceiptPrompt() {
    const input = document.getElementById("geminiCustomPromptInput");
    if (input) {
        input.value = "Deteksi dan ekstraksi seluruh informasi struk kasir ini secara detail: Nama Toko, Tanggal, Jam, No. Resi, Rincian seluruh barang belanja beserta harga, Diskon, Pajak, dan Total Pembayaran.";
    }
    runGeminiModalAnalysis(true);
}

// State for active Gemini Analysis Target
let activeGeminiTarget = {
    type: "snapshot", // 'snapshot' or 'camera'
    source: "",       // snapshot URL/path or camera_id
    displayName: ""
};


let lastGeminiRawReport = "";

function analyzeViewerSnapshotWithGemini() {
    const img = document.getElementById("imageViewerModalImg");
    if (!img || !img.src) return;

    activeGeminiTarget = {
        type: "snapshot",
        source: img.src,
        displayName: "Snapshot Rekaman"
    };

    closeModal("imageViewerModal");
    openGeminiForensicsModal();
    runGeminiModalAnalysis(false);
}

function analyzeCameraWithGemini(camId, camName) {
    activeGeminiTarget = {
        type: "camera",
        source: camId,
        displayName: camName || "Kamera Live"
    };

    openGeminiForensicsModal();
    runGeminiModalAnalysis(false);
}

function openGeminiForensicsModal() {
    const modalImg = document.getElementById("geminiModalImg");
    const sourceText = document.getElementById("geminiModalSourceText");
    const subtitle = document.getElementById("geminiModalSubtitle");
    const modelBadge = document.getElementById("geminiModalModelBadge");
    const selectedModel = document.getElementById("srvGeminiModelSelect")?.value || "gemini-1.5-flash";

    if (modelBadge) modelBadge.innerText = selectedModel;
    if (subtitle) subtitle.innerText = `Investigasi Forensik Terhadap: ${activeGeminiTarget.displayName}`;
    if (sourceText) sourceText.innerText = `Target: ${activeGeminiTarget.displayName}`;

    if (modalImg) {
        if (activeGeminiTarget.type === "camera") {
            // Live snapshot from camera
            modalImg.src = `/api/cameras/${activeGeminiTarget.source}/stream?overlay=false&t=${Date.now()}`;
        } else {
            modalImg.src = activeGeminiTarget.source;
        }
    }

    openModal("geminiVisionModal");
}

function quickPrompt(text) {
    const input = document.getElementById("geminiCustomPromptInput");
    if (input) {
        input.value = text;
        runGeminiModalAnalysis(true);
    }
}

async function runGeminiModalAnalysis(isCustomPrompt = false) {
    const loadingEl = document.getElementById("geminiModalLoading");
    const outputEl = document.getElementById("geminiModalOutput");
    const timestampEl = document.getElementById("geminiModalTimestamp");
    const customPromptInput = document.getElementById("geminiCustomPromptInput");
    const model = document.getElementById("srvGeminiModelSelect")?.value || "gemini-1.5-flash";

    if (loadingEl) loadingEl.classList.remove("hidden");

    let prompt = null;
    if (isCustomPrompt && customPromptInput && customPromptInput.value.trim()) {
        prompt = customPromptInput.value.trim();
    }

    const payload = {
        model: model,
        prompt: prompt
    };

    if (activeGeminiTarget.type === "camera") {
        payload.camera_id = activeGeminiTarget.source;
    } else {
        payload.snapshot_path = activeGeminiTarget.source;
    }

    try {
        const res = await fetch("/api/ai/gemini-analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (loadingEl) loadingEl.classList.add("hidden");

        if (res.ok && data.success) {
            lastGeminiRawReport = data.analysis;
            if (outputEl) {
                outputEl.innerHTML = renderGeminiMarkdown(data.analysis);
            }
            if (timestampEl) {
                timestampEl.innerText = `✓ Selesai (${data.model} @ ${data.timestamp || new Date().toLocaleTimeString()})`;
            }
        } else {
            const err = data.detail || data.message || "Gagal memproses analisis gambar.";
            if (outputEl) {
                outputEl.innerHTML = `
                    <div class="p-4 bg-rose-950/40 border border-rose-500/40 rounded-xl text-rose-300">
                        <strong class="font-bold block mb-1">⚠️ Gagal Menjalankan Analisis Gemini Vision</strong>
                        <p class="text-xs">${err}</p>
                        <p class="text-[11px] text-slate-400 mt-2">Pastikan Google Gemini API Key Anda sudah dimasukkan dengan benar pada tab <strong>Pengaturan</strong>.</p>
                    </div>
                `;
            }
            if (timestampEl) {
                timestampEl.innerText = "Status: Gagal";
            }
        }
    } catch (err) {
        if (loadingEl) loadingEl.classList.add("hidden");
        console.error("Gemini analysis error:", err);
        if (outputEl) {
            outputEl.innerHTML = `
                <div class="p-4 bg-rose-950/40 border border-rose-500/40 rounded-xl text-rose-300">
                    <strong class="font-bold block mb-1">Terjadi Kesalahan Jaringan</strong>
                    <p class="text-xs">${err.message || 'Koneksi ke server AI terputus.'}</p>
                </div>
            `;
        }
        if (timestampEl) {
            timestampEl.innerText = "Status: Terjadi Kesalahan";
        }
    }
}

function copyGeminiReport() {
    if (!lastGeminiRawReport) {
        alert("Belum ada laporan analisis yang dapat disalin.");
        return;
    }
    navigator.clipboard.writeText(lastGeminiRawReport).then(() => {
        const btn = document.getElementById("btnCopyGemini");
        if (btn) {
            const orig = btn.innerHTML;
            btn.innerHTML = "✓ Disalin!";
            btn.className = "px-3 py-2 bg-emerald-700 text-white rounded-xl text-xs font-medium transition flex items-center gap-1.5";
            setTimeout(() => {
                btn.innerHTML = orig;
                btn.className = "px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium border border-slate-700 transition flex items-center gap-1.5";
            }, 2500);
        }
    }).catch(err => {
        console.error("Copy failed:", err);
    });
}

function renderGeminiMarkdown(md) {
    if (!md) return "";

    // Parse Markdown tables first
    const lines = md.split("\n");
    let inTable = false;
    let tableRows = [];
    let processedLines = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (line.startsWith("|") && line.endsWith("|")) {
            const rawCells = line.slice(1, -1).split("|").map(c => c.trim());
            // Check if delimiter row like |---|---|
            if (rawCells.every(c => c.replace(/[\-:\s]/g, "") === "")) {
                continue;
            }
            if (!inTable) {
                inTable = true;
                tableRows = [];
                tableRows.push({ isHeader: true, cells: rawCells });
            } else {
                tableRows.push({ isHeader: false, cells: rawCells });
            }
        } else {
            if (inTable) {
                inTable = false;
                processedLines.push(buildHtmlTable(tableRows));
                tableRows = [];
            }
            processedLines.push(lines[i]);
        }
    }
    if (inTable) {
        processedLines.push(buildHtmlTable(tableRows));
    }

    function buildHtmlTable(rows) {
        if (!rows || rows.length === 0) return "";
        let html = '<div class="overflow-x-auto my-3"><table class="w-full text-xs text-left border border-slate-700/80 rounded-xl overflow-hidden">';
        const header = rows.find(r => r.isHeader);
        if (header) {
            html += '<thead class="bg-slate-800 text-sky-300 font-bold"><tr>';
            html += header.cells.map(c => `<th class="px-3 py-2 border-b border-slate-700">${c}</th>`).join("");
            html += '</tr></thead>';
        }
        html += '<tbody class="divide-y divide-slate-800 bg-slate-900/60">';
        rows.filter(r => !r.isHeader).forEach(r => {
            html += '<tr class="hover:bg-slate-800/40">';
            html += r.cells.map(c => `<td class="px-3 py-2 text-slate-200">${c}</td>`).join("");
            html += '</tr>';
        });
        html += '</tbody></table></div>';
        return html;
    }

    let html = processedLines.join("\n")
        .replace(/^### (.*$)/gim, '<div class="mt-4 mb-2 pb-1 border-b border-sky-500/30 text-sky-300 font-bold text-xs uppercase tracking-wider flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-sky-400"></span>$1</div>')
        .replace(/^## (.*$)/gim, '<div class="mt-4 mb-2 text-white font-bold text-sm text-sky-200 border-b border-sky-500/20 pb-1">$1</div>')
        .replace(/\*\*(.*?)\*\*/gim, '<strong class="text-white font-bold">$1</strong>')
        .replace(/^\s*[\-\*]\s+(.*$)/gim, '<div class="ml-3 my-0.5 text-slate-300 flex items-start gap-2"><span class="text-sky-400 font-bold">•</span><span>$1</span></div>')
        .replace(/^\s*(\d+)\.\s+(.*$)/gim, '<div class="ml-2 my-0.5 text-slate-300 flex items-start gap-2"><span class="font-bold text-sky-400 text-xs">$1.</span><span>$2</span></div>')
        .replace(/\n\n+/g, '<div class="my-2.5"></div>')
        .replace(/\n/g, '<br/>');

    return html;
}


async function testTelegramAlert() {
    const statusEl = document.getElementById("serverSettingsStatus");
    if (statusEl) {
        statusEl.innerText = "Mengirim pesan uji Telegram...";
        statusEl.className = "text-xs text-sky-400 font-semibold";
    }

    try {
        const res = await fetch("/api/system/test-telegram", { method: "POST" });
        const result = await res.json();
        if (result.success) {
            if (statusEl) {
                statusEl.innerText = "✓ " + result.message;
                statusEl.className = "text-xs text-emerald-400 font-semibold";
            }
        } else {
            if (statusEl) {
                statusEl.innerText = "✗ " + result.message;
                statusEl.className = "text-xs text-rose-400 font-semibold";
            }
        }
    } catch (e) {
        if (statusEl) {
            statusEl.innerText = "✗ Gagal terhubung ke endpoint telegram.";
            statusEl.className = "text-xs text-rose-400 font-semibold";
        }
    }
}

async function restartStreamsService() {
    const statusEl = document.getElementById("serverSettingsStatus");
    if (statusEl) {
        statusEl.innerText = "Memuat ulang pipeline kamera AI...";
        statusEl.className = "text-xs text-sky-400 font-semibold";
    }

    try {
        const res = await fetch("/api/system/restart-streams", { method: "POST" });
        const data = await res.json();
        if (statusEl) {
            statusEl.innerText = "✓ " + (data.message || "Pipeline berhasil dimuat ulang");
            statusEl.className = "text-xs text-emerald-400 font-semibold";
            setTimeout(() => { statusEl.innerText = ""; }, 4000);
        }
        loadLiveFeeds();
        loadSettingsCameras();
    } catch (e) {
        console.error("Restart stream error:", e);
        if (statusEl) {
            statusEl.innerText = "✗ Terjadi kesalahan koneksi saat memuat ulang.";
            statusEl.className = "text-xs text-rose-400 font-semibold";
            setTimeout(() => { statusEl.innerText = ""; }, 4000);
        }
    }
}

// ==========================================
// VMS PLAYBACK & TIMELINE SCRUBBER
// ==========================================

async function initVmsPlaybackTab() {
    // 1. Set default date to today YYYY-MM-DD
    const datePicker = document.getElementById("vmsDatePicker");
    if (datePicker && !datePicker.value) {
        const today = new Date().toISOString().split("T")[0];
        datePicker.value = today;
    }

    // 2. Populate camera select
    const camSelect = document.getElementById("vmsCameraSelect");
    if (camSelect) {
        try {
            const res = await fetch("/api/cameras");
            const cameras = await res.json();
            const currentVal = camSelect.value;
            camSelect.innerHTML = `<option value="">Semua Kamera</option>` + cameras.map(c => `
                <option value="${c.id}" ${currentVal === c.id ? 'selected' : ''}>${c.name}</option>
            `).join("");
        } catch (e) {
            console.error("Failed to load cameras for VMS select:", e);
        }
    }

    // 3. Setup click on timeline canvas
    setupTimelineCanvasInteraction();

    // 4. Fetch clips
    fetchVmsClips();
}

async function fetchVmsClips() {
    const datePicker = document.getElementById("vmsDatePicker");
    const camSelect = document.getElementById("vmsCameraSelect");
    const container = document.getElementById("clipsListContainer");
    const badge = document.getElementById("clipsCountBadge");

    const date = datePicker ? datePicker.value : "";
    const camId = camSelect ? camSelect.value : "";

    let url = `/api/clips?`;
    if (date) url += `date=${date}&`;
    if (camId) url += `camera_id=${camId}&`;

    try {
        const res = await fetch(url);
        vmsClips = await res.json();

        if (badge) badge.innerText = `${vmsClips.length} Klip`;

        if (!container) return;

        if (vmsClips.length === 0) {
            container.innerHTML = `
                <div class="text-center py-12 text-slate-500 text-xs">
                    Tidak ada rekaman klip kejadian pada filter tanggal ini.
                </div>
            `;
            renderTimelineScrubber([]);
            return;
        }

        container.innerHTML = vmsClips.map(clip => {
            const isBlacklist = clip.event_type === "BLACKLIST_HIT";
            const badgeBg = isBlacklist ? "bg-rose-500/20 text-rose-400 border-rose-500/30" : "bg-sky-500/20 text-sky-400 border-sky-500/30";
            const timeStr = clip.start_time ? clip.start_time.split("T")[1]?.slice(0, 8) || clip.start_time : "-";

            return `
            <div onclick="playClip('${clip.id}')" class="p-2.5 rounded-xl bg-slate-800/40 hover:bg-slate-800 border border-slate-700/60 hover:border-sky-500/50 cursor-pointer transition flex items-center justify-between gap-3 ${currentClipId === clip.id ? 'border-sky-500 bg-slate-800/80 shadow-md' : ''}">
                <div class="flex items-center gap-2.5 min-w-0">
                    <div class="w-10 h-10 rounded-lg bg-slate-900 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center">
                        ${clip.thumbnail_path ? `<img src="/storage/clips/${clip.thumbnail_path.split('/').pop()}" class="w-full h-full object-cover">` : '<span class="text-xs">🎬</span>'}
                    </div>
                    <div class="truncate">
                        <div class="text-xs font-bold text-slate-200 truncate">${clip.details || clip.event_type}</div>
                        <div class="text-[11px] text-slate-400 font-mono mt-0.5">${timeStr} • ${clip.duration_seconds.toFixed(0)}s</div>
                    </div>
                </div>
                <div class="shrink-0 flex flex-col items-end gap-1">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${badgeBg}">${clip.event_type}</span>
                    <span class="text-[10px] text-slate-500">${(clip.file_size_bytes / (1024 * 1024)).toFixed(1)} MB</span>
                </div>
            </div>
            `;
        }).join("");

        renderTimelineScrubber(vmsClips);

        // Auto select first clip if none is selected
        if (!currentClipId && vmsClips.length > 0) {
            playClip(vmsClips[0].id);
        }
    } catch (e) {
        console.error("Error fetching VMS clips:", e);
    }
}

function renderTimelineScrubber(clips = vmsClips) {
    const canvas = document.getElementById("timelineCanvas");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const container = document.getElementById("timelineContainer");
    if (!container) return;

    // Adjust canvas resolution
    canvas.width = container.clientWidth * (window.devicePixelRatio || 1) || 800;
    canvas.height = container.clientHeight * (window.devicePixelRatio || 1) || 64;

    const W = canvas.width;
    const H = canvas.height;
    const dpr = window.devicePixelRatio || 1;

    // Background
    ctx.fillStyle = "#090d16";
    ctx.fillRect(0, 0, W, H);

    // Draw 24-hour vertical grid lines (one every hour = 24 segments)
    ctx.lineWidth = 1;
    for (let h = 0; h <= 24; h++) {
        const x = (h / 24) * W;
        ctx.strokeStyle = h % 4 === 0 ? "rgba(148, 163, 184, 0.25)" : "rgba(148, 163, 184, 0.08)";
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, H);
        ctx.stroke();

        if (h % 4 === 0 && h < 24) {
            ctx.fillStyle = "rgba(148, 163, 184, 0.5)";
            ctx.font = `${10 * dpr}px monospace`;
            ctx.fillText(`${String(h).padStart(2, '0')}:00`, x + 4, 14 * dpr);
        }
    }

    // Draw Event Blocks
    clips.forEach(clip => {
        if (!clip.start_time) return;
        const dateObj = new Date(clip.start_time);
        const secOfDay = dateObj.getHours() * 3600 + dateObj.getMinutes() * 60 + dateObj.getSeconds();
        const startX = (secOfDay / 86400) * W;
        const clipW = Math.max(10 * dpr, (clip.duration_seconds / 86400) * W * 15);

        const isBlacklist = clip.event_type === "BLACKLIST_HIT";
        const isSelected = currentClipId === clip.id;

        ctx.fillStyle = isBlacklist ? "rgba(244, 63, 94, 0.85)" : "rgba(14, 165, 233, 0.85)";
        if (isSelected) {
            ctx.fillStyle = "#ffffff";
        }

        const blockY = 22 * dpr;
        const blockH = H - blockY - (8 * dpr);

        ctx.beginPath();
        if (ctx.roundRect) {
            ctx.roundRect(startX, blockY, clipW, blockH, 3 * dpr);
        } else {
            ctx.rect(startX, blockY, clipW, blockH);
        }
        ctx.fill();

        if (isSelected) {
            ctx.strokeStyle = isBlacklist ? "#f43f5e" : "#0284c7";
            ctx.lineWidth = 2 * dpr;
            ctx.stroke();
        }
    });
}

function setupTimelineCanvasInteraction() {
    const container = document.getElementById("timelineContainer");
    if (!container || container.dataset.hooked) return;
    container.dataset.hooked = "true";

    container.addEventListener("click", (e) => {
        if (vmsClips.length === 0) return;
        const rect = container.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const pct = clickX / rect.width;
        const clickedSec = pct * 86400;

        // Find nearest clip within 30 minutes (1800s)
        let closestClip = null;
        let minDiff = Infinity;

        vmsClips.forEach(clip => {
            if (!clip.start_time) return;
            const d = new Date(clip.start_time);
            const s = d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds();
            const diff = Math.abs(clickedSec - s);
            if (diff < minDiff) {
                minDiff = diff;
                closestClip = clip;
            }
        });

        if (closestClip) {
            playClip(closestClip.id);
        }
    });
}

function playClip(clipId) {
    currentClipId = clipId;
    const clip = vmsClips.find(c => c.id === clipId);
    if (!clip) return;

    const player = document.getElementById("vmsVideoPlayer");
    const titleEl = document.getElementById("currentClipTitle");
    const badgeEl = document.getElementById("currentClipBadge");
    const metaEl = document.getElementById("currentClipMeta");
    const dlBtn = document.getElementById("vmsDownloadBtn");

    if (player) {
        player.src = `/api/clips/${clip.id}/stream`;
        player.load();
        player.play().catch(() => {});
    }

    if (titleEl) {
        titleEl.innerText = `${clip.details || clip.event_type} (${clip.duration_seconds.toFixed(0)}s)`;
    }

    if (badgeEl) {
        badgeEl.innerText = clip.event_type;
        badgeEl.className = clip.event_type === "BLACKLIST_HIT"
            ? "px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/40"
            : "px-2 py-0.5 rounded text-xs font-semibold bg-sky-500/20 text-sky-400 border border-sky-500/40";
    }

    if (metaEl) {
        const timeStr = clip.start_time ? new Date(clip.start_time).toLocaleString("id-ID") : "-";
        metaEl.innerHTML = `Waktu Kejadian: <strong>${timeStr}</strong> • Berkas: <code>${clip.file_name}</code> (${(clip.file_size_bytes / (1024 * 1024)).toFixed(2)} MB)`;
    }

    if (dlBtn) {
        dlBtn.classList.remove("hidden");
    }

    renderTimelineScrubber();
    const container = document.getElementById("clipsListContainer");
    if (container) {
        container.querySelectorAll("div[onclick^='playClip']").forEach(div => {
            if (div.getAttribute("onclick").includes(clipId)) {
                div.classList.add("border-sky-500", "bg-slate-800/80");
            } else {
                div.classList.remove("border-sky-500", "bg-slate-800/80");
            }
        });
    }
}

function downloadCurrentClip() {
    if (!currentClipId) return;
    const link = document.createElement("a");
    link.href = `/api/clips/${currentClipId}/stream`;
    link.download = `clip_${currentClipId}.mp4`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

async function triggerManualClipRecording() {
    const camSelect = document.getElementById("vmsCameraSelect");
    const camId = camSelect ? camSelect.value : "";
    triggerManualClip(camId);
}

// ==========================================
// STORAGE & NAS BACKUP SYNCHRONIZATION
// ==========================================

async function loadStorageStatus() {
    try {
        const res = await fetch("/api/storage/status");
        if (!res.ok) return;
        const data = await res.json();

        const diskEl = document.getElementById("storageDiskUsage");
        const progressEl = document.getElementById("storageDiskProgress");
        const countEl = document.getElementById("storageClipsCount");
        const sizeEl = document.getElementById("storageClipsSize");
        const syncStatusEl = document.getElementById("storageSyncStatus");
        const freedEl = document.getElementById("storageGcsFreed");
        const targetEl = document.getElementById("storageGcsTarget");
        const badgeEl = document.getElementById("gcsStatusBadge");

        if (diskEl) diskEl.innerText = `${data.used_gb} GB / ${data.total_gb} GB`;
        if (progressEl) progressEl.style.width = `${Math.min(100, data.used_percent)}%`;
        if (countEl) countEl.innerText = `${data.clips_stored} Klip`;
        if (sizeEl) sizeEl.innerText = `Snapshot: ${data.snapshots_stored} | Bebas: ${data.free_gb} GB`;
        if (freedEl) freedEl.innerText = `${data.gcs_freed_mb || '0.00'} MB`;
        if (targetEl) targetEl.innerText = data.gcs_bucket ? `gs://${data.gcs_bucket}` : 'Lokal / Belum Ada';
        if (syncStatusEl) syncStatusEl.innerText = `Terakhir: ${data.last_sync}`;

        if (badgeEl) {
            if (data.gcs_configured) {
                badgeEl.className = "px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
                badgeEl.innerText = `✓ Terhubung (gs://${data.gcs_bucket})`;
            } else {
                badgeEl.className = "px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30";
                badgeEl.innerText = "Menunggu Konfigurasi";
            }
        }
    } catch (e) {
        console.error("Load storage status error:", e);
    }
}

async function loadGcsConfig() {
    try {
        const res = await fetch("/api/storage/gcs-config");
        if (!res.ok) return;
        const config = await res.json();

        const bucketInput = document.getElementById("gcsBucketNameInput");
        const projInput = document.getElementById("gcsProjectIdInput");
        const autoDelInput = document.getElementById("gcsAutoDeleteInput");
        const credsInput = document.getElementById("gcsCredentialsInput");

        if (bucketInput && config.bucket_name) bucketInput.value = config.bucket_name;
        if (projInput && config.project_id) projInput.value = config.project_id;
        if (autoDelInput) autoDelInput.checked = config.auto_delete_local !== false;
        if (credsInput && config.credentials_preview) {
            credsInput.placeholder = `[Tersimpan: ${config.credentials_preview}] Masukkan kunci baru jika ingin memperbarui.`;
        }
    } catch (e) {
        console.error("Load GCS config error:", e);
    }
}

async function saveGcsConfig(e) {
    if (e && e.preventDefault) e.preventDefault();
    const feedbackBox = document.getElementById("gcsFeedbackBox");

    const bucketName = document.getElementById("gcsBucketNameInput").value.trim();
    const projectId = document.getElementById("gcsProjectIdInput").value.trim();
    const credentials = document.getElementById("gcsCredentialsInput").value.trim();
    const autoDelete = document.getElementById("gcsAutoDeleteInput").checked;

    if (!bucketName) {
        alert("Harap masukkan nama Google Cloud Storage Bucket");
        return;
    }

    try {
        const payload = {
            bucket_name: bucketName,
            project_id: projectId,
            auto_delete_local: autoDelete,
            enabled: true
        };
        if (credentials) {
            payload.credentials_json = credentials;
        }

        const res = await fetch("/api/storage/gcs-config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await res.json();

        if (feedbackBox) {
            feedbackBox.className = "p-3 rounded-lg text-xs bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 block";
            feedbackBox.innerHTML = `✓ <strong>Tersimpan:</strong> ${result.message}`;
        }
        logAuditAction("CONFIG_CHANGE", "STORAGE_GCS", `Updated GCS Bucket to gs://${bucketName}`);
        loadStorageStatus();
    } catch (err) {
        console.error("Save GCS config error:", err);
        if (feedbackBox) {
            feedbackBox.className = "p-3 rounded-lg text-xs bg-rose-950/70 text-rose-300 border border-rose-500/40 block";
            feedbackBox.innerHTML = `✗ <strong>Gagal menyimpan:</strong> ${err.message}`;
        }
    }
}

async function testGcsConnection() {
    const btn = document.getElementById("testGcsBtn");
    const feedbackBox = document.getElementById("gcsFeedbackBox");

    const bucketName = document.getElementById("gcsBucketNameInput").value.trim();
    const projectId = document.getElementById("gcsProjectIdInput").value.trim();
    const credentials = document.getElementById("gcsCredentialsInput").value.trim();

    if (!bucketName) {
        alert("Harap masukkan nama GCS Bucket terlebih dahulu untuk diuji.");
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerText = "⏳ Menguji Koneksi GCS...";
    }

    try {
        const payload = {
            bucket_name: bucketName,
            project_id: projectId,
            credentials_json: credentials || null
        };
        const res = await fetch("/api/storage/test-gcs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await res.json();

        if (feedbackBox) {
            feedbackBox.classList.remove("hidden");
            if (result.success) {
                feedbackBox.className = "p-3 rounded-lg text-xs bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 block";
                feedbackBox.innerHTML = `✓ <strong>Koneksi Berhasil:</strong> ${result.message}`;
            } else {
                feedbackBox.className = "p-3 rounded-lg text-xs bg-amber-950/70 text-amber-300 border border-amber-500/40 block";
                feedbackBox.innerHTML = `⚠️ <strong>Hasil Pengujian:</strong> ${result.message}`;
            }
        }
    } catch (err) {
        if (feedbackBox) {
            feedbackBox.className = "p-3 rounded-lg text-xs bg-rose-950/70 text-rose-300 border border-rose-500/40 block";
            feedbackBox.innerHTML = `✗ <strong>Gagal:</strong> ${err.message}`;
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = "⚡ Uji Koneksi GCS Bucket";
        }
    }
}

async function syncToGcsNow() {
    const btn = document.getElementById("syncGcsBtn");
    const feedbackBox = document.getElementById("gcsFeedbackBox");

    if (btn) {
        btn.disabled = true;
        btn.innerText = "⏳ Mengunggah ke GCS...";
    }

    try {
        const res = await fetch("/api/storage/sync-to-gcs", { method: "POST" });
        const result = await res.json();

        if (feedbackBox) {
            feedbackBox.classList.remove("hidden");
            if (result.success) {
                feedbackBox.className = "p-3 rounded-lg text-xs bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 block";
                feedbackBox.innerHTML = `✓ <strong>Sinkronisasi Sukses:</strong> ${result.message}`;
                showEmergencyBanner(`☁️ Berhasil mengunggah ${result.files_synced} video ke Google Cloud Storage!`);
            } else {
                feedbackBox.className = "p-3 rounded-lg text-xs bg-amber-950/70 text-amber-300 border border-amber-500/40 block";
                feedbackBox.innerHTML = `⚠️ <strong>Pemberitahuan:</strong> ${result.message || result.error}`;
            }
        }
        logAuditAction("CLOUD_SYNC", "STORAGE_GCS", `Uploaded clips to Google Cloud Storage`);
        loadStorageStatus();
    } catch (err) {
        if (feedbackBox) {
            feedbackBox.className = "p-3 rounded-lg text-xs bg-rose-950/70 text-rose-300 border border-rose-500/40 block";
            feedbackBox.innerHTML = `✗ <strong>Gagal:</strong> ${err.message}`;
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = "☁️ Unggah Semua Rekaman ke GCS Sekarang";
        }
    }
}

async function syncStorageNow() {
    const btn = document.getElementById("syncStorageBtn");
    const syncStatusEl = document.getElementById("storageSyncStatus");
    if (btn) {
        btn.disabled = true;
        btn.innerText = "⏳ Menyinkronkan...";
    }
    if (syncStatusEl) syncStatusEl.innerText = "Status: Mentransfer berkas ke target penyimpanan...";

    try {
        const res = await fetch("/api/storage/sync-now", { method: "POST" });
        const result = await res.json();

        logAuditAction("CLOUD_SYNC", "STORAGE", `Synced ${result.files_synced || 0} files`);
        if (syncStatusEl) {
            syncStatusEl.innerText = `✓ ${result.message || 'Sinkronisasi selesai'}`;
        }
        showEmergencyBanner(`☁️ Sinkronisasi Cadangan Selesai! ${result.files_synced || 0} file bukti diproses.`);
        loadStorageStatus();
    } catch (e) {
        console.error("Storage sync error:", e);
        if (syncStatusEl) syncStatusEl.innerText = "✗ Gagal melakukan sinkronisasi.";
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = "⚡ Sinkronkan Sekarang";
        }
    }
}

// ==========================================
// AUDIT TRAIL LOGGING & MONITORING
// ==========================================

async function loadAuditLogs() {
    const tbody = document.getElementById("auditLogsTableBody");
    if (!tbody) return;

    try {
        const res = await fetch("/api/audit/logs?limit=50");
        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-rose-400">Gagal memuat log audit.</td></tr>`;
            return;
        }
        const logs = await res.json();
        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-slate-500 text-xs">Belum ada riwayat aktivitas pengguna.</td></tr>`;
            return;
        }

        tbody.innerHTML = logs.map(l => {
            const timeStr = l.timestamp ? new Date(l.timestamp).toLocaleString("id-ID") : "-";
            const roleBadgeClass = l.user_role === "ADMIN" ? "bg-sky-500/20 text-sky-400 border-sky-500/30" : (l.user_role === "OPERATOR" ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-purple-500/20 text-purple-400 border-purple-500/30");

            return `
            <tr class="border-b border-slate-700/50 hover:bg-slate-800/40 text-xs">
                <td class="py-2.5 px-3 text-slate-400 font-mono whitespace-nowrap">${timeStr}</td>
                <td class="py-2.5 px-3 font-semibold text-slate-200">
                    ${l.username} <span class="px-1.5 py-0.5 rounded text-[10px] border ${roleBadgeClass}">${l.user_role || 'USER'}</span>
                </td>
                <td class="py-2.5 px-3 font-mono font-bold text-sky-300">${l.action_type}</td>
                <td class="py-2.5 px-3 text-slate-400">${l.entity_name || '-'}</td>
                <td class="py-2.5 px-3 text-slate-300">${l.details || '-'}</td>
                <td class="py-2.5 px-3 font-mono text-slate-500 text-[11px]">${l.ip_address || '127.0.0.1'}</td>
            </tr>
            `;
        }).join("");
    } catch (e) {
        console.error("Load audit logs error:", e);
    }
}

async function logAuditAction(actionType, entityName, details) {
    try {
        await fetch("/api/audit/logs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                action_type: actionType,
                entity_name: entityName,
                details: details,
                username: currentUser.username,
                user_role: currentUser.role
            })
        });
    } catch (e) {
        // Silent fail
    }
}

// ==========================================
// USER AUTHENTICATION & MULTI-LEVEL RBAC
// ==========================================

function initAuthRbac() {
    updateCurrentUserUI();
    applyRbacPermissions();
}

function updateCurrentUserUI() {
    const roleBadgeHeader = document.getElementById("currentUserRoleBadge");
    const modalUsername = document.getElementById("modalUsernameDisplay");
    const modalBadge = document.getElementById("modalRoleBadge");
    const modalAvatar = document.getElementById("modalUserAvatar");
    const rolePermsList = document.getElementById("rolePermsList");

    const roleInfo = {
        ADMIN: {
            icon: "👑",
            title: `Super Admin (${currentUser.username})`,
            badge: "ADMIN",
            perms: `• Menambah, mengedit, dan menghapus kamera<br>• Konfigurasi garis virtual & ambang batas deteksi AI<br>• Kontrol penuh siklus stream & inferensi AI<br>• Pencadangan Cloud/NAS & manajemen pengguna`
        },
        OPERATOR: {
            icon: "🛡️",
            title: `Petugas Satpam (${currentUser.username})`,
            badge: "OPERATOR",
            perms: `• Pemantauan Live Multi-View real-time<br>• Respons alarm sirene darurat & banner alert<br>• Perekaman klip video kejadian 20 detik<br>• Melihat VMS Player & Log Plat ANPR (Read-Only)`
        },
        AUDITOR: {
            icon: "📊",
            title: `Auditor Sistem (${currentUser.username})`,
            badge: "AUDITOR",
            perms: `• Akses penuh ke Traffic Analytics Dashboard<br>• Unduh berkas laporan Excel (.xlsx) & PDF<br>• Pemeriksaan Security Audit Trail & log sistem<br>• Peninjauan arsip rekaman klip VMS (Read-Only)`
        }
    };

    const currentInfo = roleInfo[currentUser.role] || roleInfo.ADMIN;

    if (roleBadgeHeader) roleBadgeHeader.innerHTML = `${currentInfo.icon} ${currentInfo.title}`;
    if (modalUsername) modalUsername.innerText = currentUser.full_name || currentUser.username;
    if (modalBadge) {
        modalBadge.innerText = currentUser.role;
        modalBadge.className = currentUser.role === "ADMIN" ? "px-2 py-0.5 rounded text-xs font-semibold bg-sky-600/30 text-sky-400 border border-sky-500/40" : (currentUser.role === "OPERATOR" ? "px-2 py-0.5 rounded text-xs font-semibold bg-emerald-600/30 text-emerald-400 border border-emerald-500/40" : "px-2 py-0.5 rounded text-xs font-semibold bg-purple-600/30 text-purple-400 border border-purple-500/40");
    }
    if (modalAvatar) modalAvatar.innerText = currentInfo.icon;
    if (rolePermsList) rolePermsList.innerHTML = currentInfo.perms;

    // Highlight active role button in modal
    document.querySelectorAll(".role-switch-btn").forEach(btn => {
        if (btn.dataset.role === currentUser.role) {
            btn.classList.add("border-sky-500", "bg-sky-500/20");
            btn.classList.remove("border-slate-700");
        } else {
            btn.classList.remove("border-sky-500", "bg-sky-500/20");
            btn.classList.add("border-slate-700");
        }
    });
}

function switchUserRole(role) {
    const roleProfiles = {
        ADMIN: { username: "admin", full_name: "Super Administrator", role: "ADMIN" },
        OPERATOR: { username: "satpam", full_name: "Petugas Operator Satpam", role: "OPERATOR" },
        AUDITOR: { username: "auditor", full_name: "Auditor Kepatuhan & Analitik", role: "AUDITOR" }
    };

    currentUser = roleProfiles[role] || roleProfiles.ADMIN;
    localStorage.setItem("smart_cctv_user", JSON.stringify(currentUser));

    logAuditAction("ROLE_SWITCH", "AUTH", `Simulated role change to ${role}`);
    updateCurrentUserUI();
    applyRbacPermissions();
    closeModal("userProfileModal");
    showEmergencyBanner(`Peran aktif berhasil diubah ke: ${currentUser.role} (${currentUser.full_name})`);
}

async function handleAuthLogin(e) {
    e.preventDefault();
    const uInput = document.getElementById("loginUsernameInput");
    const pInput = document.getElementById("loginPasswordInput");
    const statusMsg = document.getElementById("loginStatusMsg");

    const username = uInput ? uInput.value.trim() : "";
    const password = pInput ? pInput.value.trim() : "";

    if (!username || !password) return;

    if (statusMsg) statusMsg.innerText = "Memverifikasi...";

    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        if (res.ok) {
            const data = await res.json();
            currentUser = {
                username: data.user.username,
                full_name: data.user.full_name,
                role: data.user.role,
                token: data.access_token
            };
            localStorage.setItem("smart_cctv_user", JSON.stringify(currentUser));
            updateCurrentUserUI();
            applyRbacPermissions();
            closeModal("userProfileModal");
            logAuditAction("LOGIN", "AUTH", `User ${username} logged in successfully`);
            showEmergencyBanner(`✓ Berhasil login sebagai: ${currentUser.full_name} (${currentUser.role})`);
        } else {
            if (statusMsg) {
                statusMsg.innerText = "✗ Username atau password salah";
                statusMsg.className = "text-[11px] text-rose-400";
            }
        }
    } catch (err) {
        console.error("Login error:", err);
        if (statusMsg) {
            statusMsg.innerText = "✗ Koneksi server gagal";
            statusMsg.className = "text-[11px] text-rose-400";
        }
    }
}

function applyRbacPermissions() {
    const role = currentUser.role;

    // Elements that only ADMIN can modify
    const adminElements = document.querySelectorAll(".rbac-admin-only, #serverSettingsForm button[type='submit'], #syncStorageBtn");
    adminElements.forEach(el => {
        if (role !== "ADMIN") {
            el.disabled = true;
            el.classList.add("opacity-50", "cursor-not-allowed");
            el.title = "Hanya Administrator yang memiliki izin konfigurasi sistem.";
        } else {
            el.disabled = false;
            el.classList.remove("opacity-50", "cursor-not-allowed");
            el.title = "";
        }
    });

    // Hide or disable Studio Draw Tools if not ADMIN
    const studioSaveBtn = document.getElementById("saveLinesBtn");
    const studioAddBtn = document.getElementById("startDrawingLineBtn");
    if (studioSaveBtn && studioAddBtn) {
        if (role !== "ADMIN") {
            studioSaveBtn.disabled = true;
            studioAddBtn.disabled = true;
            studioSaveBtn.classList.add("opacity-50", "cursor-not-allowed");
            studioAddBtn.classList.add("opacity-50", "cursor-not-allowed");
        } else {
            studioSaveBtn.disabled = false;
            studioAddBtn.disabled = false;
            studioSaveBtn.classList.remove("opacity-50", "cursor-not-allowed");
            studioAddBtn.classList.remove("opacity-50", "cursor-not-allowed");
        }
    }
}
