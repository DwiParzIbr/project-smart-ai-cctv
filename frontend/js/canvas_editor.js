// Interactive Virtual Counting Line Canvas Studio (Refined Modern UI/UX)

let canvas = null;
let ctx = null;
let activeCameraId = null;
let activeLines = [];
let studioMode = 'SELECT'; // 'SELECT' or 'DRAW'
let selectedLineId = null;
let hoveredLineId = null;
let isCleanBackground = true;

let isDrawing = false;
let currentLine = null; // {x1, y1, x2, y2}
let draggingTarget = null; // { line, type: 'p1' | 'p2' | 'mid', startX, startY, origX1, origY1, origX2, origY2 }

function initCanvasStudio() {
    canvas = document.getElementById("lineCanvas");
    if (!canvas) return;
    ctx = canvas.getContext("2d");

    // Event listeners
    canvas.addEventListener("mousedown", onMouseDown);
    canvas.addEventListener("mousemove", onMouseMove);
    canvas.addEventListener("mouseup", onMouseUp);
    canvas.addEventListener("mouseleave", onMouseLeave);

    loadStudioCameras();
    setStudioMode('SELECT');
}

async function loadStudioCameras() {
    try {
        const res = await fetch("/api/cameras");
        const cameras = await res.json();
        const sel = document.getElementById("studioCameraSelect");
        if (!sel) return;

        sel.innerHTML = "";
        cameras.forEach(cam => {
            const opt = document.createElement("option");
            opt.value = cam.id;
            opt.textContent = `${cam.name} (${cam.status})`;
            sel.appendChild(opt);
        });

        if (cameras.length > 0) {
            selectStudioCamera(cameras[0].id);
        }
    } catch (e) {
        console.error("Error loading cameras for studio:", e);
    }
}

function selectStudioCamera(camId) {
    activeCameraId = camId;
    selectedLineId = null;
    updateSelectedLineControls();

    const bgImg = document.getElementById("studioBackgroundStream");
    if (bgImg) {
        // By default use clean raw video (overlay=false) to avoid duplicate graphics
        bgImg.src = isCleanBackground ? `/api/cameras/${camId}/stream?overlay=false` : `/api/cameras/${camId}/stream`;
    }
    loadLinesForCamera(camId);
}

function toggleStudioBackgroundMode() {
    isCleanBackground = !isCleanBackground;
    const btn = document.getElementById("studioBgModeBtn");
    if (btn) {
        btn.innerHTML = isCleanBackground ? "📷 Video Bersih: ON" : "👁️ Deteksi AI: ON";
        btn.className = isCleanBackground 
            ? "px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold transition flex items-center gap-1.5"
            : "px-3 py-2 bg-sky-600/30 hover:bg-sky-600/50 text-sky-300 border border-sky-500/40 rounded-xl text-xs font-semibold transition flex items-center gap-1.5";
    }

    const bgImg = document.getElementById("studioBackgroundStream");
    if (bgImg && activeCameraId) {
        bgImg.src = isCleanBackground ? `/api/cameras/${activeCameraId}/stream?overlay=false` : `/api/cameras/${activeCameraId}/stream`;
    }
}

async function loadLinesForCamera(camId) {
    try {
        const res = await fetch(`/api/lines?camera_id=${camId}`);
        activeLines = await res.json();
        
        // Auto select first line if available and none selected
        if (!selectedLineId && activeLines.length > 0) {
            selectedLineId = activeLines[0].id;
        } else if (activeLines.length === 0) {
            selectedLineId = null;
        }

        updateSelectedLineControls();
        renderCanvas();
        updateLinesListTable();
    } catch (e) {
        console.error("Error loading lines:", e);
    }
}

// Mode Switcher: SELECT vs DRAW
function setStudioMode(mode) {
    studioMode = mode;
    const selectBtn = document.getElementById("modeSelectBtn");
    const drawBtn = document.getElementById("modeDrawBtn");
    const indicator = document.getElementById("studioModeIndicator");
    const hintText = document.getElementById("studioHintText");

    if (mode === 'SELECT') {
        if (selectBtn) {
            selectBtn.className = "px-3 py-1.5 rounded-xl text-xs font-bold border transition flex items-center gap-1.5 bg-sky-500/20 text-sky-400 border-sky-500/50";
        }
        if (drawBtn) {
            drawBtn.className = "px-3 py-1.5 rounded-xl text-xs font-bold border transition flex items-center gap-1.5 bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700 hover:text-white";
        }
        if (indicator) {
            indicator.innerText = "MODE: PILIH & GESER";
            indicator.className = "px-2 py-0.5 rounded bg-sky-500/20 text-sky-400 border border-sky-500/30 font-bold text-[11px]";
        }
        if (hintText) {
            hintText.innerText = "Klik pada garis untuk memilih. Geser titik P1, P2, atau titik tengah (✛) untuk memindahkan garis.";
        }
        if (canvas) canvas.style.cursor = "default";
    } else {
        if (drawBtn) {
            drawBtn.className = "px-3 py-1.5 rounded-xl text-xs font-bold border transition flex items-center gap-1.5 bg-sky-500/20 text-sky-400 border-sky-500/50";
        }
        if (selectBtn) {
            selectBtn.className = "px-3 py-1.5 rounded-xl text-xs font-bold border transition flex items-center gap-1.5 bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700 hover:text-white";
        }
        if (indicator) {
            indicator.innerText = "MODE: GAMBAR GARIS BARU";
            indicator.className = "px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold text-[11px]";
        }
        if (hintText) {
            hintText.innerText = "Klik dan seret (drag) pada video untuk menarik garis virtual baru.";
        }
        if (canvas) canvas.style.cursor = "crosshair";
    }

    renderCanvas();
}

function updateSelectedLineControls() {
    const controls = document.getElementById("selectedLineControls");
    const titleEl = document.getElementById("selectedLineTitle");
    const dirBidir = document.getElementById("dirBidirBtn");
    const dirIn = document.getElementById("dirInBtn");
    const dirOut = document.getElementById("dirOutBtn");

    const selectedLine = activeLines.find(l => l.id === selectedLineId);

    if (!selectedLine || !controls) {
        if (controls) {
            controls.classList.add("opacity-50", "pointer-events-none");
        }
        if (titleEl) titleEl.innerText = "Garis Terpilih: Tidak ada";
        return;
    }

    controls.classList.remove("opacity-50", "pointer-events-none");
    if (titleEl) {
        titleEl.innerHTML = `<span class="text-white font-bold">${selectedLine.line_name}</span>`;
    }

    const dir = selectedLine.direction_arrow || "BIDIRECTIONAL";
    const activeBtnClass = "px-2.5 py-1 rounded-lg bg-sky-500 text-white font-bold transition shadow";
    const inactiveBtnClass = "px-2.5 py-1 rounded-lg text-slate-400 hover:text-white font-medium transition";

    if (dirBidir) dirBidir.className = dir === "BIDIRECTIONAL" ? activeBtnClass : inactiveBtnClass;
    if (dirIn) dirIn.className = dir === "IN_ONLY" ? activeBtnClass : inactiveBtnClass;
    if (dirOut) dirOut.className = dir === "OUT_ONLY" ? activeBtnClass : inactiveBtnClass;
}

// Direction Controller Actions
async function setSelectedLineDirection(dir) {
    const line = activeLines.find(l => l.id === selectedLineId);
    if (!line) return;

    line.direction_arrow = dir;
    await saveUpdatedLineCoords(line);
    updateSelectedLineControls();
    renderCanvas();
}

async function flipSelectedLineDirection() {
    const line = activeLines.find(l => l.id === selectedLineId);
    if (!line) return;

    // Flip P1 and P2
    const tempX = line.x1;
    const tempY = line.y1;
    line.x1 = line.x2;
    line.y1 = line.y2;
    line.x2 = tempX;
    line.y2 = tempY;

    await saveUpdatedLineCoords(line);
    renderCanvas();
    updateLinesListTable();
}

async function renameSelectedLinePrompt() {
    const line = activeLines.find(l => l.id === selectedLineId);
    if (!line) return;

    const newName = prompt("Ubah nama garis penghitung:", line.line_name);
    if (!newName || newName.trim() === "") return;

    line.line_name = newName.trim();
    await saveUpdatedLineCoords(line);
    updateSelectedLineControls();
    renderCanvas();
    updateLinesListTable();
}

async function deleteCurrentSelectedLine() {
    if (!selectedLineId) return;
    deleteSelectedLine(selectedLineId);
}

// Distance helper from point to line segment
function distToSegment(px, py, x1, y1, x2, y2) {
    const l2 = (x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1);
    if (l2 === 0) return Math.hypot(px - x1, py - y1);
    let t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * (x2 - x1)), py - (y1 + t * (y2 - y1)));
}

function findHitTarget(x, y) {
    const w = canvas.width;
    const h = canvas.height;

    // 1. Check selected line handles first (Priority)
    const selected = activeLines.find(l => l.id === selectedLineId);
    if (selected) {
        const sx1 = selected.x1 * w;
        const sy1 = selected.y1 * h;
        const sx2 = selected.x2 * w;
        const sy2 = selected.y2 * h;
        const smx = (sx1 + sx2) / 2;
        const smy = (sy1 + sy2) / 2;

        if (Math.hypot(sx1 - x, sy1 - y) <= 16) return { line: selected, handle: 'p1' };
        if (Math.hypot(sx2 - x, sy2 - y) <= 16) return { line: selected, handle: 'p2' };
        if (Math.hypot(smx - x, smy - y) <= 18) return { line: selected, handle: 'mid' };
    }

    // 2. Check all lines handles
    for (let l of activeLines) {
        const lx1 = l.x1 * w;
        const ly1 = l.y1 * h;
        const lx2 = l.x2 * w;
        const ly2 = l.y2 * h;
        const lmx = (lx1 + lx2) / 2;
        const lmy = (ly1 + ly2) / 2;

        if (Math.hypot(lx1 - x, ly1 - y) <= 16) return { line: l, handle: 'p1' };
        if (Math.hypot(lx2 - x, ly2 - y) <= 16) return { line: l, handle: 'p2' };
        if (Math.hypot(lmx - x, lmy - y) <= 18) return { line: l, handle: 'mid' };
    }

    // 3. Check proximity to line segment
    for (let l of activeLines) {
        const d = distToSegment(x, y, l.x1 * w, l.y1 * h, l.x2 * w, l.y2 * h);
        if (d <= 14) {
            return { line: l, handle: 'line' };
        }
    }

    return null;
}

function getCanvasCoords(e) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY
    };
}

function onMouseDown(e) {
    const { x, y } = getCanvasCoords(e);
    const normX = Math.max(0, Math.min(1, x / canvas.width));
    const normY = Math.max(0, Math.min(1, y / canvas.height));

    if (studioMode === 'DRAW') {
        isDrawing = true;
        currentLine = { x1: normX, y1: normY, x2: normX, y2: normY };
        renderCanvas();
        return;
    }

    // SELECT mode
    const hit = findHitTarget(x, y);
    if (hit) {
        selectedLineId = hit.line.id;
        updateSelectedLineControls();

        if (hit.handle === 'p1' || hit.handle === 'p2') {
            draggingTarget = { line: hit.line, type: hit.handle };
        } else {
            // Drag whole line from midpoint or segment
            draggingTarget = {
                line: hit.line,
                type: 'mid',
                startX: normX,
                startY: normY,
                origX1: hit.line.x1,
                origY1: hit.line.y1,
                origX2: hit.line.x2,
                origY2: hit.line.y2
            };
        }
    } else {
        selectedLineId = null;
        updateSelectedLineControls();
    }

    renderCanvas();
}

function onMouseMove(e) {
    const { x, y } = getCanvasCoords(e);
    const normX = Math.max(0, Math.min(1, x / canvas.width));
    const normY = Math.max(0, Math.min(1, y / canvas.height));

    if (studioMode === 'DRAW' && isDrawing && currentLine) {
        currentLine.x2 = normX;
        currentLine.y2 = normY;
        renderCanvas();
        return;
    }

    if (studioMode === 'SELECT') {
        if (draggingTarget) {
            if (draggingTarget.type === 'p1') {
                draggingTarget.line.x1 = normX;
                draggingTarget.line.y1 = normY;
            } else if (draggingTarget.type === 'p2') {
                draggingTarget.line.x2 = normX;
                draggingTarget.line.y2 = normY;
            } else if (draggingTarget.type === 'mid') {
                const dx = normX - draggingTarget.startX;
                const dy = normY - draggingTarget.startY;
                draggingTarget.line.x1 = Math.max(0, Math.min(1, draggingTarget.origX1 + dx));
                draggingTarget.line.y1 = Math.max(0, Math.min(1, draggingTarget.origY1 + dy));
                draggingTarget.line.x2 = Math.max(0, Math.min(1, draggingTarget.origX2 + dx));
                draggingTarget.line.y2 = Math.max(0, Math.min(1, draggingTarget.origY2 + dy));
            }
            renderCanvas();
            return;
        }

        // Just hovering: change cursor and detect hovered line
        const hit = findHitTarget(x, y);
        if (hit) {
            hoveredLineId = hit.line.id;
            canvas.style.cursor = (hit.handle === 'p1' || hit.handle === 'p2' || hit.handle === 'mid') ? "grab" : "pointer";
        } else {
            hoveredLineId = null;
            canvas.style.cursor = "default";
        }
        renderCanvas();
    }
}

function onMouseUp(e) {
    if (studioMode === 'DRAW' && isDrawing && currentLine) {
        isDrawing = false;
        const dx = (currentLine.x2 - currentLine.x1) * canvas.width;
        const dy = (currentLine.y2 - currentLine.y1) * canvas.height;
        
        if (Math.hypot(dx, dy) > 30) {
            saveNewLine(currentLine);
        } else {
            currentLine = null;
            renderCanvas();
        }
        return;
    }

    if (draggingTarget) {
        saveUpdatedLineCoords(draggingTarget.line);
        draggingTarget = null;
    }
}

function onMouseLeave(e) {
    if (draggingTarget) {
        saveUpdatedLineCoords(draggingTarget.line);
        draggingTarget = null;
    }
    if (isDrawing) {
        isDrawing = false;
        currentLine = null;
    }
    hoveredLineId = null;
    renderCanvas();
}

async function saveNewLine(lineCoords) {
    const lineName = prompt("Beri nama garis penghitung ini:", `Garis ${activeLines.length + 1}`);
    if (!lineName || lineName.trim() === "") {
        currentLine = null;
        renderCanvas();
        return;
    }

    try {
        const res = await fetch("/api/lines", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                camera_id: activeCameraId,
                line_name: lineName.trim(),
                x1: lineCoords.x1,
                y1: lineCoords.y1,
                x2: lineCoords.x2,
                y2: lineCoords.y2,
                direction_arrow: "BIDIRECTIONAL"
            })
        });

        if (res.ok) {
            const data = await res.json();
            currentLine = null;
            selectedLineId = data.id;
            await loadLinesForCamera(activeCameraId);
            setStudioMode('SELECT'); // Return to select mode to prevent accidental lines
        }
    } catch (e) {
        console.error("Failed to save line:", e);
    }
}

async function saveUpdatedLineCoords(line) {
    try {
        await fetch(`/api/lines/${line.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                x1: line.x1,
                y1: line.y1,
                x2: line.x2,
                y2: line.y2,
                line_name: line.line_name,
                direction_arrow: line.direction_arrow
            })
        });
        updateLinesListTable();
    } catch (e) {
        console.error("Failed to update line:", e);
    }
}

async function deleteSelectedLine(lineId) {
    if (!confirm("Hapus garis penghitung ini dari kamera?")) return;
    try {
        await fetch(`/api/lines/${lineId}`, { method: "DELETE" });
        if (selectedLineId === lineId) {
            selectedLineId = null;
        }
        await loadLinesForCamera(activeCameraId);
    } catch (e) {
        console.error("Failed to delete line:", e);
    }
}

// ==========================================
// CANVA RENDERING (CLEAN PROFESSIONAL LOOK)
// ==========================================

function renderCanvas() {
    if (!ctx || !canvas) return;
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // 1. Render all non-selected lines first (subtle background tripwires)
    activeLines.forEach(line => {
        if (line.id !== selectedLineId) {
            drawSubtleLine(line, w, h, line.id === hoveredLineId);
        }
    });

    // 2. Render currently selected line with full interactive handles & direction indicators
    const selectedLine = activeLines.find(l => l.id === selectedLineId);
    if (selectedLine) {
        drawSelectedInteractiveLine(selectedLine, w, h);
    }

    // 3. Render in-progress drawing line
    if (currentLine) {
        drawNewDrawingLine(currentLine, w, h);
    }
}

// Draws a sleek, non-distracting tripwire for inactive lines
function drawSubtleLine(line, w, h, isHovered) {
    const x1 = line.x1 * w;
    const y1 = line.y1 * h;
    const x2 = line.x2 * w;
    const y2 = line.y2 * h;
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;

    ctx.save();

    // Dark under-stroke for high contrast against any road surface
    ctx.strokeStyle = "rgba(15, 23, 42, 0.85)";
    ctx.lineWidth = isHovered ? 6 : 4;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // Main line (Sleek light cyan)
    ctx.strokeStyle = isHovered ? "#38bdf8" : "rgba(56, 189, 248, 0.75)";
    ctx.lineWidth = isHovered ? 3 : 2;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // Subtle endpoint dots
    ctx.fillStyle = isHovered ? "#38bdf8" : "#0284c7";
    ctx.beginPath();
    ctx.arc(x1, y1, isHovered ? 6 : 4, 0, Math.PI * 2);
    ctx.arc(x2, y2, isHovered ? 6 : 4, 0, Math.PI * 2);
    ctx.fill();

    // Compact floating pill badge for line name
    const dirStr = line.direction_arrow === "BIDIRECTIONAL" ? "⇄" : (line.direction_arrow === "IN_ONLY" ? "➔" : "⬅");
    const badgeText = `${line.line_name} [${dirStr}]`;

    ctx.font = "bold 11px sans-serif";
    const textW = ctx.measureText(badgeText).width;
    const padX = 8;
    const badgeW = textW + padX * 2;
    const badgeH = 20;

    // Badge background
    ctx.fillStyle = isHovered ? "rgba(15, 23, 42, 0.95)" : "rgba(15, 23, 42, 0.75)";
    ctx.strokeStyle = isHovered ? "#38bdf8" : "rgba(56, 189, 248, 0.4)";
    ctx.lineWidth = 1;

    ctx.beginPath();
    ctx.roundRect(midX - badgeW / 2, midY - badgeH - 6, badgeW, badgeH, 6);
    ctx.fill();
    ctx.stroke();

    // Badge text
    ctx.fillStyle = isHovered ? "#ffffff" : "#94a3b8";
    ctx.textAlign = "center";
    ctx.fillText(badgeText, midX, midY - 10);

    ctx.restore();
}

// Draws the active selected line with handles, glow, and direction vector
function drawSelectedInteractiveLine(line, w, h) {
    const x1 = line.x1 * w;
    const y1 = line.y1 * h;
    const x2 = line.x2 * w;
    const y2 = line.y2 * h;
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;

    ctx.save();

    // 1. Neon Cyan Glow
    ctx.strokeStyle = "rgba(6, 182, 212, 0.25)";
    ctx.lineWidth = 12;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // Dark under-line
    ctx.strokeStyle = "#090d16";
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // Main Crisp Line
    ctx.strokeStyle = "#06b6d4";
    ctx.lineWidth = 3.5;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // 2. Normal Vector & Direction Arrows
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len = Math.hypot(dx, dy);

    if (len > 0) {
        const arrowDist = 36;
        const nx = (-dy / len) * arrowDist;
        const ny = (dx / len) * arrowDist;
        const dir = line.direction_arrow || "BIDIRECTIONAL";

        // MASUK (IN) Vector - Right side
        if (dir === "BIDIRECTIONAL" || dir === "IN_ONLY") {
            ctx.strokeStyle = "#10b981"; // Emerald
            ctx.fillStyle = "#10b981";
            ctx.lineWidth = 2.5;

            // Arrow line
            ctx.beginPath();
            ctx.moveTo(midX, midY);
            ctx.lineTo(midX + nx, midY + ny);
            ctx.stroke();

            // Arrow head tip
            ctx.beginPath();
            ctx.arc(midX + nx, midY + ny, 4, 0, Math.PI * 2);
            ctx.fill();

            // Pill badge "➔ MASUK"
            drawArrowPill(midX + nx * 1.25, midY + ny * 1.25, "➔ MASUK (IN)", "#10b981");
        }

        // KELUAR (OUT) Vector - Left side
        if (dir === "BIDIRECTIONAL" || dir === "OUT_ONLY") {
            ctx.strokeStyle = "#f59e0b"; // Amber
            ctx.fillStyle = "#f59e0b";
            ctx.lineWidth = 2.5;

            // Arrow line
            ctx.beginPath();
            ctx.moveTo(midX, midY);
            ctx.lineTo(midX - nx, midY - ny);
            ctx.stroke();

            // Arrow head tip
            ctx.beginPath();
            ctx.arc(midX - nx, midY - ny, 4, 0, Math.PI * 2);
            ctx.fill();

            // Pill badge "⬅ KELUAR"
            drawArrowPill(midX - nx * 1.25, midY - ny * 1.25, "⬅ KELUAR (OUT)", "#f59e0b");
        }
    }

    // 3. Midpoint Move Handle (✛) to move entire line together
    ctx.fillStyle = "#0284c7";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(midX, midY, 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("✛", midX, midY);

    // 4. Endpoints Drag Handles (P1 and P2)
    drawHandlePoint(x1, y1, "P1");
    drawHandlePoint(x2, y2, "P2");

    // 5. Line Name & Header Badge
    const dirStr = line.direction_arrow === "BIDIRECTIONAL" ? "⇄ DUA ARAH" : (line.direction_arrow === "IN_ONLY" ? "➔ MASUK" : "⬅ KELUAR");
    const labelText = `📍 ${line.line_name} [${dirStr}]`;
    
    ctx.font = "bold 12px sans-serif";
    const tw = ctx.measureText(labelText).width;
    const badgeW = tw + 18;
    const badgeH = 24;

    ctx.fillStyle = "rgba(15, 23, 42, 0.95)";
    ctx.strokeStyle = "#06b6d4";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(midX - badgeW / 2, midY - badgeH - 18, badgeW, badgeH, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#38bdf8";
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(labelText, midX, midY - 22);

    ctx.restore();
}

// Draws a sleek handle circle with outer ring and text tag
function drawHandlePoint(x, y, label) {
    ctx.save();

    // Outer dark circle
    ctx.fillStyle = "#0f172a";
    ctx.strokeStyle = "#06b6d4";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(x, y, 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Inner white dot
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();

    // Tag badge
    ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
    ctx.strokeStyle = "#06b6d4";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(x - 12, y - 24, 24, 15, 4);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#38bdf8";
    ctx.font = "bold 9px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(label, x, y - 13);

    ctx.restore();
}

function drawArrowPill(x, y, text, color) {
    ctx.save();
    ctx.font = "bold 10px sans-serif";
    const tw = ctx.measureText(text).width;
    const pw = tw + 12;
    const ph = 18;

    ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(x - pw / 2, y - ph / 2, pw, ph, 5);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, x, y);
    ctx.restore();
}

// In-progress new line drawing
function drawNewDrawingLine(line, w, h) {
    const x1 = line.x1 * w;
    const y1 = line.y1 * h;
    const x2 = line.x2 * w;
    const y2 = line.y2 * h;

    ctx.save();

    ctx.strokeStyle = "#10b981"; // Emerald
    ctx.lineWidth = 3;
    ctx.setLineDash([8, 6]);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    ctx.fillStyle = "#10b981";
    ctx.beginPath();
    ctx.arc(x1, y1, 6, 0, Math.PI * 2);
    ctx.arc(x2, y2, 6, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
}

// Updates table below canvas
function updateLinesListTable() {
    const listBody = document.getElementById("linesListTableBody");
    const badge = document.getElementById("linesCountBadge");

    if (badge) badge.innerText = `${activeLines.length} Garis`;
    if (!listBody) return;

    if (activeLines.length === 0) {
        listBody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center py-6 text-slate-500 text-xs">
                    Belum ada garis penghitung pada kamera ini. Klik tombol <strong>"+ Gambar Garis Baru"</strong> di atas.
                </td>
            </tr>
        `;
        return;
    }

    listBody.innerHTML = activeLines.map(l => {
        const isSelected = l.id === selectedLineId;
        const dirBadge = l.direction_arrow === "BIDIRECTIONAL" 
            ? '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-sky-500/20 text-sky-400 border border-sky-500/30">⇄ Dua Arah (IN/OUT)</span>'
            : (l.direction_arrow === "IN_ONLY" 
                ? '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">➔ Masuk Saja</span>'
                : '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30">⬅ Keluar Saja</span>');

        return `
        <tr class="border-b border-slate-700/50 hover:bg-slate-800/40 cursor-pointer transition ${isSelected ? 'bg-slate-800/80 border-sky-500/50' : ''}" onclick="selectLineFromTable('${l.id}')">
            <td class="py-3 px-3">
                <div class="font-bold text-sm text-slate-200 flex items-center gap-2">
                    ${isSelected ? '<span class="w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>' : ''}
                    ${l.line_name}
                </div>
            </td>
            <td class="py-3 px-3 text-xs font-mono text-slate-400">
                P1: (${(l.x1 * 100).toFixed(0)}%, ${(l.y1 * 100).toFixed(0)}%) ➔ P2: (${(l.x2 * 100).toFixed(0)}%, ${(l.y2 * 100).toFixed(0)}%)
            </td>
            <td class="py-3 px-3">
                ${dirBadge}
            </td>
            <td class="py-3 px-3 text-right whitespace-nowrap" onclick="event.stopPropagation()">
                <button onclick="flipLineById('${l.id}')" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-amber-400 border border-slate-700 rounded-lg text-xs font-semibold mr-1.5 transition" title="Balik Arah Masuk/Keluar">
                    🔄 Balik
                </button>
                <button onclick="deleteSelectedLine('${l.id}')" class="px-2 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 rounded-lg text-xs font-semibold transition">
                    🗑️ Hapus
                </button>
            </td>
        </tr>
        `;
    }).join("");
}

function selectLineFromTable(lineId) {
    selectedLineId = lineId;
    updateSelectedLineControls();
    renderCanvas();
    updateLinesListTable();
}

async function flipLineById(lineId) {
    selectedLineId = lineId;
    await flipSelectedLineDirection();
}
