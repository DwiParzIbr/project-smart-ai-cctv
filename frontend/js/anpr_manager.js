// ANPR & License Plate Hub Manager

let currentAnprFilter = "";
let currentCategoryFilter = "";

async function initAnprModule() {
    await fetchAnprLogs();
    await fetchVehicleRegistry();
}

async function fetchAnprLogs() {
    try {
        let url = `/api/anpr/logs?limit=50`;
        if (currentAnprFilter) url += `&query=${encodeURIComponent(currentAnprFilter)}`;
        if (currentCategoryFilter) url += `&category=${encodeURIComponent(currentCategoryFilter)}`;

        const res = await fetch(url);
        const logs = await res.json();
        const tbody = document.getElementById("anprLogsTableBody");
        if (!tbody) return;

        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-slate-500">Tidak ada log plat nomor ditemukan.</td></tr>`;
            return;
        }

        tbody.innerHTML = logs.map(l => {
            let statusBadge = "";
            if (l.access_status === "BLACKLIST") {
                statusBadge = `<span class="px-2.5 py-1 rounded-md text-xs font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse">BLACKLIST</span>`;
            } else if (l.access_status === "WHITELIST") {
                statusBadge = `<span class="px-2.5 py-1 rounded-md text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">WHITELIST</span>`;
            } else if (l.access_status === "VIP") {
                statusBadge = `<span class="px-2.5 py-1 rounded-md text-xs font-bold bg-purple-500/20 text-purple-400 border border-purple-500/40">VIP</span>`;
            } else {
                statusBadge = `<span class="px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-500/20 text-slate-400 border border-slate-500/30">UNREGISTERED</span>`;
            }

            const plateCropUrl = l.crop_image_path ? `/storage/plates/${l.crop_image_path.split('/').pop()}` : null;
            const plateImgHtml = plateCropUrl
                ? `<img src="${plateCropUrl}" onclick="showImageModal('${plateCropUrl}')" class="h-8 max-w-[110px] object-contain rounded border border-slate-700 cursor-pointer hover:scale-125 transition shadow bg-black" alt="Plat">`
                : `<span class="text-slate-600 text-xs">-</span>`;

            return `
                <tr class="border-b border-slate-700/45 hover:bg-slate-800/40 transition">
                    <td class="py-3 px-3 text-xs text-slate-400">${l.timestamp || "-"}</td>
                    <td class="py-3 px-3">${plateImgHtml}</td>
                    <td class="py-3 px-3">
                        <span class="font-mono text-base font-bold text-amber-400 tracking-wider">${l.normalized_plate}</span>
                        <div class="text-[11px] text-slate-500 font-mono">Raw: ${l.plate_number}</div>
                    </td>
                    <td class="py-3 px-3">${statusBadge}</td>
                    <td class="py-3 px-3 text-xs font-semibold text-slate-300">${l.confidence_score}%</td>
                </tr>
            `;
        }).join("");
    } catch (e) {
        console.error("Error fetching ANPR logs:", e);
    }
}

async function fetchVehicleRegistry() {
    try {
        const res = await fetch("/api/anpr/registry");
        const items = await res.json();
        const tbody = document.getElementById("registryTableBody");
        if (!tbody) return;

        if (items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-slate-500">Belum ada plat terdaftar di sistem.</td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(item => {
            const isBlacklist = item.category === "BLACKLIST";
            const badgeClass = isBlacklist
                ? "bg-rose-500/20 text-rose-400 border-rose-500/40"
                : (item.category === "VIP" ? "bg-purple-500/20 text-purple-400 border-purple-500/40" : "bg-emerald-500/20 text-emerald-400 border-emerald-500/40");

            return `
                <tr class="border-b border-slate-700/40 hover:bg-slate-800/40">
                    <td class="py-2.5 px-3 font-mono font-bold text-slate-200">${item.plate_number}</td>
                    <td class="py-2.5 px-3">
                        <span class="px-2 py-0.5 rounded text-xs font-bold border ${badgeClass}">${item.category}</span>
                    </td>
                    <td class="py-2.5 px-3 text-xs text-slate-300">${item.owner_name || "-"}</td>
                    <td class="py-2.5 px-3 text-xs text-slate-400">${item.notes || "-"}</td>
                    <td class="py-2.5 px-3 text-right">
                        <button onclick="deleteRegistryItem('${item.id}')" class="text-xs text-rose-400 hover:text-rose-300 px-2 py-1 bg-rose-500/10 rounded hover:bg-rose-500/20">Hapus</button>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (e) {
        console.error("Error loading registry:", e);
    }
}

async function submitNewVehicleRegistry(e) {
    e.preventDefault();
    const plate = document.getElementById("regPlateInput").value.trim();
    const cat = document.getElementById("regCategorySelect").value;
    const owner = document.getElementById("regOwnerInput").value.trim();
    const notes = document.getElementById("regNotesInput").value.trim();

    if (!plate) return;

    try {
        const res = await fetch("/api/anpr/registry", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plate_number: plate,
                category: cat,
                owner_name: owner,
                notes: notes
            })
        });

        if (res.ok) {
            closeModal("addVehicleModal");
            document.getElementById("addVehicleForm").reset();
            await fetchVehicleRegistry();
            await fetchAnprLogs();
        }
    } catch (err) {
        console.error("Failed to add vehicle:", err);
    }
}

async function deleteRegistryItem(id) {
    if (!confirm("Hapus plat nomor ini dari daftar?")) return;
    try {
        await fetch(`/api/anpr/registry/${id}`, { method: "DELETE" });
        await fetchVehicleRegistry();
    } catch (e) {
        console.error("Delete registry failed:", e);
    }
}

function onSearchPlateInput(val) {
    currentAnprFilter = val;
    fetchAnprLogs();
}

function onFilterCategoryChange(val) {
    currentCategoryFilter = val;
    fetchAnprLogs();
}
