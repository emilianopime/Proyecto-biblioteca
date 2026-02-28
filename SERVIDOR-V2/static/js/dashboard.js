// ==========================================
// 1. LÓGICA DE CARGA CSV
// ==========================================
const zone = document.getElementById('drop-zone');
const fileInput = document.getElementById('fileInput');
const msg = document.getElementById('upload-msg');

if(zone) {
    zone.onclick = () => fileInput.click();
    zone.ondragover = (e) => { e.preventDefault(); zone.classList.add('hover'); };
    zone.ondragleave = () => zone.classList.remove('hover');
    zone.ondrop = (e) => {
        e.preventDefault();
        zone.classList.remove('hover');
        enviarCsv(e.dataTransfer.files[0]);
    };
    fileInput.onchange = () => enviarCsv(fileInput.files[0]);
}

function enviarCsv(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('table_name', document.getElementById('tableName').value || 'alumnos');

    msg.innerText = "Procesando en base de datos...";
    fetch('/api/upload', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(data => {
        msg.innerText = data.message || data.error;
        msg.style.color = data.error ? "red" : "green";
    });
}

// ==========================================
// 2. LÓGICA DE MONITOREO (COMPUTADORAS)
// ==========================================
async function loadComputers() {
    try {
        const response = await fetch('/api/computers');
        const data = await response.json();

        const totalEl = document.getElementById('total-computers');
        if(totalEl) {
            totalEl.textContent = data.total;
            document.getElementById('online-computers').textContent = data.online;
            document.getElementById('offline-computers').textContent = data.offline;

            const container = document.getElementById('computers-container');

            container.innerHTML = data.computers.map(pc => `
                <div class="computer-card ${pc.status}">

                    <div class="card-header">
                        <h3>${pc.name}</h3>
                        <span class="status-badge ${pc.status}">${pc.status === 'online' ? 'EN LÍNEA' : 'OFFLINE'}</span>
                    </div>

                    <div class="info-row"><span>IP Red Local:</span> <strong>${pc.ip}</strong></div>
                    <div class="info-row"><span>Último Latido:</span> <strong>${pc.last_heartbeat.split(' ')[1]}</strong></div>
                    ${pc.info.cpu_percent ? `<div class="info-row"><span>Uso CPU:</span> <strong>${pc.info.cpu_percent}%</strong></div>` : ''}

                    ${pc.info.locked ? `
                        <div class="user-status locked">
                            <span class="icon">🔒</span>
                            <span class="locked-text">Pantalla Bloqueada<br><small style="color:#e53e3e; font-weight:normal;">Equipo Disponible</small></span>
                        </div>
                    ` : (pc.info.current_user ? `
                        <div class="user-status active">
                            <span class="icon">👤</span>
                            <div class="user-details">
                                <span class="user-name">${pc.info.current_user}</span>
                                <span class="user-mat">Matrícula: ${pc.info.cardnumber || 'No registrada'}</span>
                            </div>
                        </div>
                    ` : `
                        <div class="user-status">
                            <span class="icon">❓</span>
                            <span>Estado desconocido</span>
                        </div>
                    `)}

                    <button class="btn-delete" onclick="deleteComputer('${pc.id}')">🗑️ Quitar del Monitor</button>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error("Error cargando los datos:", error);
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

// ==========================================
// 3. NAVEGACIÓN Y VISTAS (SIDEBAR)
// ==========================================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if(sidebar) sidebar.classList.toggle('collapsed');
}

let statsInterval = null;

function setView(name) {
    document.querySelectorAll('.view').forEach(function(v) { v.classList.remove('active'); });
    document.querySelectorAll('.nav-item').forEach(function(i) { i.classList.remove('active'); });

    const targetView = document.getElementById('view-' + name);
    if(targetView) targetView.classList.add('active');

    const navEl = document.getElementById('nav-' + name);
    if (navEl && !navEl.classList.contains('disabled')) { navEl.classList.add('active'); }

    if (name === 'stats') {
        loadStats();
        if (!statsInterval) { statsInterval = setInterval(loadStats, 30000); }
    } else {
        if (statsInterval) { clearInterval(statsInterval); statsInterval = null; }
    }
}

// ==========================================
// 4. LÓGICA DE ESTADÍSTICAS
// ==========================================
function loadStats() {
    fetch('/api/stats')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.error) { console.error('Stats error:', d.error); return; }

            document.getElementById('st-total-alumnos').textContent = d.total_alumnos.toLocaleString('es-MX');
            document.getElementById('st-logins-hoy').textContent    = d.logins_hoy;
            document.getElementById('st-logins-semana').textContent = d.logins_semana;
            document.getElementById('st-logins-mes').textContent    = d.logins_mes;

            /* Actividad reciente - ACTUALIZADA CON COLUMNA MATRICULA */
            const recEl = document.getElementById('st-recientes');
            if (!d.recientes.length) {
                recEl.innerHTML = '<div class="empty-msg">Sin actividad registrada aún.</div>';
            } else {
                recEl.innerHTML = '<table class="st-table"><thead><tr><th>PC</th><th>Alumno</th><th>Matrícula</th><th>Evento</th><th>Fecha</th></tr></thead><tbody>' +
                    d.recientes.map(function(r) {
                        const badge = r.evento === 'LOGIN'
                            ? '<span class="badge-login">LOGIN</span>'
                            : '<span class="badge-logout">LOGOUT</span>';
                        return '<tr><td>' + r.pc + '</td><td>' + r.nombre + '</td><td>' + r.matricula + '</td><td>' + badge + '</td><td>' + r.timestamp + '</td></tr>';
                    }).join('') + '</tbody></table>';
            }

            /* Top PCs */
            const pcsEl = document.getElementById('st-top-pcs');
            if (!d.top_pcs.length) {
                pcsEl.innerHTML = '<div class="empty-msg">Sin datos de uso aún.</div>';
            } else {
                const maxPc = d.top_pcs[0].total;
                pcsEl.innerHTML = d.top_pcs.map(function(p) {
                    const pct = Math.round((p.total / maxPc) * 100);
                    return '<div class="bar-row"><span class="bar-label">' + p.pc + '</span>' +
                        '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
                        '<span class="bar-count">' + p.total + '</span></div>';
                }).join('');
            }

            /* Distribución carreras padrón */
            const carEl = document.getElementById('st-dist-carreras');
            if (!d.dist_carreras.length) {
                carEl.innerHTML = '<div class="empty-msg">Sin datos.</div>';
            } else {
                const maxCar = d.dist_carreras[0].total;
                carEl.innerHTML = d.dist_carreras.map(function(c) {
                    const pct = Math.round((c.total / maxCar) * 100);
                    return '<div class="bar-row"><span class="bar-label">' + c.carrera + '</span>' +
                        '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
                        '<span class="bar-count">' + c.total.toLocaleString('es-MX') + '</span></div>';
                }).join('');
            }
        })
        .catch(function(e) { console.error('Error cargando estadísticas:', e); });
}
