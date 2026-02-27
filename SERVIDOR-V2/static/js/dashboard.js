/* ── SVG icons ──────────────────────────────────────────── */
const ICON_LOCK = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`;
const ICON_USER = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
const ICON_HELP = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r=".5" fill="currentColor"/></svg>`;
const ICON_TRASH = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`;

/* ── CSV upload ─────────────────────────────────────────── */
const zone      = document.getElementById('drop-zone');
const fileInput = document.getElementById('fileInput');
const msg       = document.getElementById('upload-msg');

zone.onclick    = () => fileInput.click();
zone.ondragover = (e) => { e.preventDefault(); zone.classList.add('hover'); };
zone.ondragleave = () => zone.classList.remove('hover');
zone.ondrop = (e) => {
    e.preventDefault();
    zone.classList.remove('hover');
    enviarCsv(e.dataTransfer.files[0]);
};
fileInput.onchange = () => enviarCsv(fileInput.files[0]);

function enviarCsv(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('table_name', document.getElementById('tableName').value || 'alumnos');

    msg.textContent  = 'Procesando en base de datos...';
    msg.style.color  = '';

    fetch('/api/upload', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            msg.textContent = data.message || data.error;
            msg.style.color = data.error ? '#f43f5e' : '#10b981';
        });
}

/* ── Computer monitoring ────────────────────────────────── */
async function loadComputers() {
    try {
        const response = await fetch('/api/computers');
        const data     = await response.json();

        document.getElementById('total-computers').textContent   = data.total;
        document.getElementById('online-computers').textContent  = data.online;
        document.getElementById('offline-computers').textContent = data.offline;

        const container = document.getElementById('computers-container');

        container.innerHTML = data.computers.map(pc => {
            const statusDot = `<span class="status-dot"></span>`;
            const statusLabel = pc.status === 'online' ? 'En línea' : 'Offline';

            let userBlock;
            if (pc.info.locked) {
                userBlock = `
                    <div class="user-status locked">
                        <span class="status-icon">${ICON_LOCK}</span>
                        <span class="locked-text">Pantalla bloqueada<small>Equipo disponible</small></span>
                    </div>`;
            } else if (pc.info.current_user) {
                userBlock = `
                    <div class="user-status active">
                        <span class="status-icon">${ICON_USER}</span>
                        <div class="user-details">
                            <span class="user-name">${pc.info.current_user}</span>
                            <span class="user-mat">Matrícula: ${pc.info.cardnumber || 'No registrada'}</span>
                        </div>
                    </div>`;
            } else {
                userBlock = `
                    <div class="user-status">
                        <span class="status-icon" style="color:var(--text-3)">${ICON_HELP}</span>
                        <span style="color:var(--text-3);font-size:.85em;">Estado desconocido</span>
                    </div>`;
            }

            return `
                <div class="computer-card ${pc.status}">
                    <div class="card-header">
                        <h3>${pc.name}</h3>
                        <span class="status-badge ${pc.status}">${statusDot}${statusLabel}</span>
                    </div>
                    <div class="info-row"><span>IP Red Local</span><strong>${pc.ip}</strong></div>
                    <div class="info-row"><span>Último latido</span><strong>${pc.last_heartbeat.split(' ')[1]}</strong></div>
                    ${pc.info.cpu_percent ? `<div class="info-row"><span>Uso CPU</span><strong>${pc.info.cpu_percent}%</strong></div>` : ''}
                    ${userBlock}
                    <button class="btn-delete" onclick="deleteComputer('${pc.id}')">${ICON_TRASH} Quitar del monitor</button>
                </div>`;
        }).join('');

    } catch (error) {
        console.error('Error cargando los datos:', error);
    }
}

async function deleteComputer(id) {
    if (confirm('¿Eliminar esta PC del monitor? Volverá a aparecer si sigue encendida.')) {
        await fetch(`/api/computer/${id}`, { method: 'DELETE' });
        loadComputers();
    }
}

setInterval(loadComputers, 5000);
loadComputers();
