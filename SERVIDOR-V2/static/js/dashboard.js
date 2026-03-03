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

/* ── Sidebar & vistas ───────────────────────────────── */
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
}

var statsInterval = null;

function setView(name) {
    document.querySelectorAll('.view').forEach(function(v) { v.classList.remove('active'); });
    document.querySelectorAll('.nav-item').forEach(function(i) { i.classList.remove('active'); });
    document.getElementById('view-' + name).classList.add('active');
    var navEl = document.getElementById('nav-' + name);
    if (navEl) navEl.classList.add('active');

    if (name === 'stats') {
        loadStats();
        if (!statsInterval) { statsInterval = setInterval(loadStats, 30000); }
    } else {
        if (statsInterval) { clearInterval(statsInterval); statsInterval = null; }
    }
}

/* ── Estadísticas ───────────────────────────────────── */
function loadStats() {
    fetch('/api/stats')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.error) return;

            document.getElementById('st-total-alumnos').textContent = d.total_alumnos.toLocaleString('es-MX');
            document.getElementById('st-logins-hoy').textContent     = d.logins_hoy;
            document.getElementById('st-logins-semana').textContent  = d.logins_semana;
            document.getElementById('st-logins-mes').textContent     = d.logins_mes;

            /* Actividad reciente */
            var recEl = document.getElementById('st-recientes');
            if (!d.recientes.length) {
                recEl.innerHTML = '<div class="empty-msg">Sin actividad registrada aún.</div>';
            } else {
                var encabezado =
                    '<table class="st-table"><thead><tr>' +
                    '<th>PC</th><th>Matrícula</th><th>Alumno</th><th>Carrera</th>' +
                    '<th>Hora inicio</th><th>Hora salida</th>' +
                    '</tr></thead><tbody>';

                var filas = d.recientes.map(function(r) {
                    var salidaTd = r.hora_salida !== null
                        ? '<td class="ts">' + r.hora_salida + '</td>'
                        : '<td><span class="badge-en-uso">En uso</span></td>';

                    return '<tr>' +
                        '<td class="mono">' + r.pc        + '</td>' +
                        '<td class="mono">' + r.matricula + '</td>' +
                        '<td>'             + r.nombre     + '</td>' +
                        '<td>'             + r.carrera    + '</td>' +
                        '<td class="ts">'  + r.hora_inicio+ '</td>' +
                        salidaTd +
                        '</tr>';
                }).join('');

                recEl.innerHTML = encabezado + filas + '</tbody></table>';
            }

            /* Top PCs */
            var pcsEl = document.getElementById('st-top-pcs');
            if (!d.top_pcs.length) {
                pcsEl.innerHTML = '<div class="empty-msg">Sin datos de uso aún.</div>';
            } else {
                var maxPc = d.top_pcs[0].total;
                pcsEl.innerHTML = d.top_pcs.map(function(p) {
                    var pct = Math.round((p.total / maxPc) * 100);
                    return '<div class="bar-row"><span class="bar-label">' + p.pc + '</span>' +
                        '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:#22d3ee"></div></div>' +
                        '<span class="bar-count">' + p.total + '</span></div>';
                }).join('');
            }

            /* Distribución carreras padrón */
            var carEl = document.getElementById('st-dist-carreras');
            if (!d.dist_carreras.length) {
                carEl.innerHTML = '<div class="empty-msg">Sin datos.</div>';
            } else {
                var maxCar = d.dist_carreras[0].total;
                carEl.innerHTML = d.dist_carreras.map(function(c) {
                    var pct = Math.round((c.total / maxCar) * 100);
                    return '<div class="bar-row"><span class="bar-label">' + c.carrera + '</span>' +
                        '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:#6366f1"></div></div>' +
                        '<span class="bar-count">' + c.total.toLocaleString('es-MX') + '</span></div>';
                }).join('');
            }

            /* Top carreras por uso real */
            var usoEl = document.getElementById('st-top-carreras-uso');
            if (!d.top_carreras_uso.length) {
                usoEl.innerHTML = '<div class="empty-msg">Sin datos de uso aún.</div>';
            } else {
                var maxUso = d.top_carreras_uso[0].total;
                usoEl.innerHTML = d.top_carreras_uso.map(function(c) {
                    var pct = Math.round((c.total / maxUso) * 100);
                    return '<div class="bar-row"><span class="bar-label">' + c.carrera + '</span>' +
                        '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:#10b981"></div></div>' +
                        '<span class="bar-count">' + c.total.toLocaleString('es-MX') + '</span></div>';
                }).join('');
            }
        })
        .catch(function(e) { console.error('Error cargando estadísticas:', e); });
}
