// Analytics Charts with Chart.js

let hourlyChartInstance = null;
let compositionChartInstance = null;

async function initAnalyticsCharts() {
    await fetchAnalyticsSummary();
    await fetchHourlyChartData();
    await fetchRecentActivities();
}

async function fetchAnalyticsSummary() {
    try {
        const res = await fetch("/api/analytics/summary");
        const data = await res.json();

        // Update cards
        const elTotal = document.getElementById("statTotalCount");
        const elIn = document.getElementById("statInCount");
        const elOut = document.getElementById("statOutCount");

        if (elTotal) elTotal.innerText = data.today_total.toLocaleString();
        if (elIn) elIn.innerText = data.today_in.toLocaleString();
        if (elOut) elOut.innerText = data.today_out.toLocaleString();

        // Render or update composition donut chart
        renderCompositionChart(data.class_breakdown);
    } catch (e) {
        console.error("Error fetching summary:", e);
    }
}

async function fetchHourlyChartData() {
    try {
        const res = await fetch("/api/analytics/hourly");
        const data = await res.json();
        renderHourlyChart(data.labels, data.incoming, data.outgoing);
    } catch (e) {
        console.error("Error fetching hourly data:", e);
    }
}

function renderHourlyChart(labels, incomingData, outgoingData) {
    const canvas = document.getElementById("hourlyFlowCanvas");
    if (!canvas) return;

    if (hourlyChartInstance) {
        hourlyChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    hourlyChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Masuk (IN)',
                    data: incomingData,
                    backgroundColor: 'rgba(16, 185, 129, 0.75)',
                    borderColor: '#10b981',
                    borderWidth: 1,
                    borderRadius: 4
                },
                {
                    label: 'Keluar (OUT)',
                    data: outgoingData,
                    backgroundColor: 'rgba(245, 158, 11, 0.75)',
                    borderColor: '#f59e0b',
                    borderWidth: 1,
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8', font: { family: 'Inter', size: 12 } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(51, 65, 85, 0.3)' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(51, 65, 85, 0.3)' },
                    ticks: { color: '#94a3b8', stepSize: 1 }
                }
            }
        }
    });
}

function renderCompositionChart(breakdown) {
    const canvas = document.getElementById("compositionCanvas");
    if (!canvas) return;

    if (compositionChartInstance) {
        compositionChartInstance.destroy();
    }

    const labels = ["Mobil", "Motor", "Orang", "Bus", "Truk", "Sepeda"];
    const values = [
        breakdown.car || 0,
        breakdown.motorcycle || 0,
        breakdown.person || 0,
        breakdown.bus || 0,
        breakdown.truck || 0,
        breakdown.bicycle || 0
    ];

    // Check if empty
    const totalVal = values.reduce((a, b) => a + b, 0);
    const displayValues = totalVal === 0 ? [1, 1, 1, 1, 1, 1] : values;

    const ctx = canvas.getContext("2d");
    compositionChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: displayValues,
                backgroundColor: [
                    '#38bdf8', // Mobil (Sky)
                    '#a855f7', // Motor (Purple)
                    '#22c55e', // Orang (Green)
                    '#f59e0b', // Bus (Amber)
                    '#ef4444', // Truk (Red)
                    '#eab308'  // Sepeda (Yellow)
                ],
                borderWidth: 2,
                borderColor: '#0f172a'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8', boxWidth: 12, padding: 14 }
                }
            },
            cutout: '65%'
        }
    });
}

async function fetchRecentActivities() {
    try {
        const res = await fetch("/api/analytics/recent?limit=10");
        const events = await res.json();
        const tbody = document.getElementById("recentEventsTableBody");
        if (!tbody) return;

        if (events.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-slate-500">Belum ada aktivitas terekam.</td></tr>`;
            return;
        }

        tbody.innerHTML = events.map(ev => {
            const isDirIn = ev.direction === "IN";
            const dirBadge = isDirIn 
                ? `<span class="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">➔ MASUK</span>`
                : `<span class="px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30">⬅ KELUAR</span>`;

            const snapUrl = ev.snapshot_path ? `/storage/snapshots/${ev.snapshot_path.split('/').pop()}` : null;
            const snapHtml = snapUrl 
                ? `<img src="${snapUrl}" onclick="showImageModal('${snapUrl}')" class="w-10 h-7 object-cover rounded cursor-pointer border border-slate-700 hover:scale-110 transition shadow" alt="Snap">`
                : `<span class="text-slate-600 text-xs">-</span>`;

            return `
                <tr class="border-b border-slate-700/40 hover:bg-slate-800/50">
                    <td class="py-2.5 px-3 text-xs text-slate-400">${ev.timestamp || "-"}</td>
                    <td class="py-2.5 px-3 font-medium text-slate-200 capitalize">${ev.object_class} (#${ev.track_id})</td>
                    <td class="py-2.5 px-3">${dirBadge}</td>
                    <td class="py-2.5 px-3">${snapHtml}</td>
                </tr>
            `;
        }).join("");
    } catch (e) {
        console.error("Error loading recent events:", e);
    }
}
