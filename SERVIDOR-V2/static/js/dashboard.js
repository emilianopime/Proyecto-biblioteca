// --- Lógica de Carga CSV ---
const zone = document.getElementById('drop-zone');
const fileInput = document.getElementById('fileInput');
const msg = document.getElementById('upload-msg');

zone.onclick = () => fileInput.click();
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

    msg.innerText = "Procesando en base de datos...";
    fetch('/api/upload', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(data => {
        msg.innerText = data.message || data.error;
        msg.style.color = data.error ? "red" : "green";
    });
}

// --- Lógica de Monitoreo ---
async function loadComputers() {
    try {
        const response = await fetch('/api/computers');
        const data = await response.json();

        document.getElementById('total-computers').textContent = data.total;
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

// Iniciar actualizaciones
setInterval(loadComputers, 5000);
loadComputers();