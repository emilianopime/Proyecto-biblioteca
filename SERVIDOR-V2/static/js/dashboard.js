/* Control de Laboratorio (UACH) - logica del dashboard
   Vistas: equipos, padron, estadisticas y bitacora. Todo el HTML dinamico
   pasa por escapar() para que un nombre raro no rompa la pagina. */

/* ── Utilidades ─────────────────────────────────────── */
function escapar(texto) {
    return String(texto ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function formatearNumero(n) {
    return Number(n ?? 0).toLocaleString('es-MX');
}

function irAlLogin() {
    window.location.href = '/login';
}

/* Devuelve el JSON de una respuesta o lanza un error legible. Si la sesion
   expiro, manda al login. */
async function leerJson(respuesta) {
    if (respuesta.status === 401 || respuesta.redirected) {
        irAlLogin();
        throw new Error('Sesión expirada');
    }
    let datos;
    try {
        datos = await respuesta.json();
    } catch (e) {
        throw new Error('El servidor respondió algo que no se pudo leer');
    }
    if (!respuesta.ok) {
        throw new Error(datos.error || `Error ${respuesta.status} del servidor`);
    }
    return datos;
}

const ICONS = {
    lock:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    user:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    off:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>',
    help:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r=".5" fill="currentColor"/></svg>',
};

/* ── Equipos ────────────────────────────────────────── */

/* Un equipo tiene un solo estado, decidido en este orden:
   sin conexion (no manda senal) > libre (kiosko bloqueado) > en uso. */
const ESTADOS = {
    'libre':        { orden: 0, etiqueta: 'Libre' },
    'en-uso':       { orden: 1, etiqueta: 'En uso' },
    'sin-conexion': { orden: 2, etiqueta: 'Sin conexión' },
    'desconocido':  { orden: 3, etiqueta: 'Sin información' },
};

function estadoDe(pc) {
    const info = pc.info || {};
    if (pc.status !== 'online') return 'sin-conexion';
    if (info.locked) return 'libre';
    if (info.current_user) return 'en-uso';
    return 'desconocido';
}

function horaDe(marca) {
    // "2026-09-18 13:05:22" -> "13:05:22"
    return (marca || '').split(' ')[1] || marca || '';
}

/* "2026-09-18 13:05:22" -> "las 13:05" si es hoy, "ayer a las 13:05", o "el 15/09 a las 13:05". */
function cuandoDe(marca) {
    const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(marca || '');
    if (!m) return `las ${horaDe(marca)}`;
    const [, anio, mes, dia, hh, mm] = m;
    const hoy = new Date(); const ayer = new Date(); ayer.setDate(hoy.getDate() - 1);
    const esFecha = (d) => d.getFullYear() === +anio && d.getMonth() + 1 === +mes && d.getDate() === +dia;
    if (esFecha(hoy))  return `las ${hh}:${mm}`;
    if (esFecha(ayer)) return `ayer a las ${hh}:${mm}`;
    return `el ${dia}/${mes} a las ${hh}:${mm}`;
}

function cuerpoTarjeta(pc, estado) {
    const info = pc.info || {};
    if (estado === 'en-uso') {
        return `<span class="status-icon">${ICONS.user}</span>
            <div class="card-user">
                <span class="card-user-name">${escapar(info.current_user)}</span>
                <span class="card-user-meta">Matrícula ${escapar(info.cardnumber || 'sin registrar')}</span>
            </div>`;
    }
    if (estado === 'libre') {
        return `<span class="status-icon">${ICONS.lock}</span>
            <span class="card-state-text"><strong>Libre.</strong> El kiosko espera una matrícula.</span>`;
    }
    if (estado === 'sin-conexion') {
        return `<span class="status-icon">${ICONS.off}</span>
            <span class="card-state-text"><strong>No responde</strong> desde ${escapar(cuandoDe(pc.last_heartbeat))}. Puede estar apagada o sin red.</span>`;
    }
    return `<span class="status-icon">${ICONS.help}</span>
        <span class="card-state-text">El kiosko está conectado pero no reportó su estado.</span>`;
}

function htmlTarjeta(pc, estado) {
    const et = ESTADOS[estado].etiqueta;
    return `
        <div class="card-header">
            <h3 class="card-name">${escapar(pc.name)}</h3>
            <span class="status-badge ${estado}"><span class="status-dot" aria-hidden="true"></span>${et}</span>
        </div>
        <div class="card-body">${cuerpoTarjeta(pc, estado)}</div>
        <details class="card-details">
            <summary>Detalles del equipo</summary>
            <div class="card-meta"><span>Dirección en la red</span><strong>${escapar(pc.ip)}</strong></div>
            <div class="card-meta"><span>Última señal</span><strong>${escapar(cuandoDe(pc.last_heartbeat).replace(/^las /, ''))}</strong></div>
            ${info_cpu(pc)}
            <button type="button" class="btn-link" onclick="deleteComputer('${escapar(pc.id)}', '${escapar(pc.name)}')">Quitar del monitor</button>
        </details>`;
}

function info_cpu(pc) {
    const cpu = pc.info && pc.info.cpu_percent;
    return cpu ? `<div class="card-meta"><span>Uso de CPU</span><strong>${escapar(cpu)}%</strong></div>` : '';
}

let ultimaActualizacion = null;
let servidorCaidoDesde = null;

function hace(ms) {
    const s = Math.round(ms / 1000);
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.round(s / 60)} min`;
    return `${Math.round(s / 3600)} h`;
}

function textoActualizado() {
    if (servidorCaidoDesde) {
        const dato = ultimaActualizacion ? `, último dato hace ${hace(Date.now() - ultimaActualizacion)}` : '';
        return `sin respuesta del servidor desde hace ${hace(Date.now() - servidorCaidoDesde)}${dato}`;
    }
    if (!ultimaActualizacion) return 'cargando';
    const ms = Date.now() - ultimaActualizacion;
    return ms < 5000 ? 'actualizado ahora' : `actualizado hace ${hace(ms)}`;
}

function pintarAvisoServidor() {
    const aviso = document.getElementById('server-warning');
    const caido = Boolean(servidorCaidoDesde);
    aviso.hidden = !caido;
    document.getElementById('computers-container').classList.toggle('desactualizado', caido);
}

/* Actualiza el grid sin destruirlo: cada tarjeta se identifica por data-id,
   solo se reescribe si cambio algo, y el orden se toca solo si cambio. Asi el
   foco del teclado y el texto seleccionado sobreviven al refresco. */
function pintarEquipos(lista) {
    const contenedor = document.getElementById('computers-container');
    contenedor.setAttribute('aria-busy', 'false');

    if (!lista.length) {
        contenedor.innerHTML = `<div class="empty-msg">
            Ningún equipo ha reportado todavía. Cada máquina aparece aquí sola en cuanto su kiosko
            se conecta al servidor, sin que tengas que registrarla.
        </div>`;
        return;
    }
    contenedor.querySelector('.empty-msg')?.remove();

    const ordenados = lista
        .map(pc => ({ pc, estado: estadoDe(pc) }))
        .sort((a, b) => ESTADOS[a.estado].orden - ESTADOS[b.estado].orden
                     || String(a.pc.name).localeCompare(String(b.pc.name), 'es', { numeric: true }));

    const existentes = new Map([...contenedor.querySelectorAll('.computer-card')].map(el => [el.dataset.id, el]));
    const vistos = new Set();

    for (const { pc, estado } of ordenados) {
        vistos.add(pc.id);
        const html = htmlTarjeta(pc, estado);
        let el = existentes.get(pc.id);
        if (!el) {
            el = document.createElement('article');
            el.className = `computer-card ${estado}`;
            el.dataset.id = pc.id;
            el.dataset.firma = html;
            el.innerHTML = html;
            contenedor.appendChild(el);
            continue;
        }
        if (el.dataset.firma !== html) {
            const abierto = el.querySelector('details')?.open;
            el.className = `computer-card ${estado}`;
            el.innerHTML = html;
            if (abierto) el.querySelector('details').open = true;
        }
        el.dataset.firma = html;
    }
    for (const [id, el] of existentes) if (!vistos.has(id)) el.remove();

    const ordenActual = [...contenedor.querySelectorAll('.computer-card')].map(e => e.dataset.id);
    const ordenNuevo = ordenados.map(o => o.pc.id);
    if (ordenActual.join('|') !== ordenNuevo.join('|')) {
        for (const id of ordenNuevo) contenedor.appendChild(existentes.get(id) || contenedor.querySelector(`.computer-card[data-id="${CSS.escape(id)}"]`));
    }
}

async function loadComputers() {
    try {
        const datos = await leerJson(await fetch('/api/computers'));
        const lista = datos.computers || [];
        const conteo = { 'libre': 0, 'en-uso': 0, 'sin-conexion': 0, 'desconocido': 0 };
        for (const pc of lista) conteo[estadoDe(pc)]++;

        document.getElementById('libres-computers').textContent       = conteo['libre'];
        document.getElementById('en-uso-computers').textContent       = conteo['en-uso'];
        document.getElementById('sin-conexion-computers').textContent = conteo['sin-conexion'];
        document.getElementById('total-computers').textContent        = lista.length;

        document.getElementById('unknown-computers').textContent =
            conteo['desconocido'] ? ` · ${conteo['desconocido']} sin información` : '';

        pintarEquipos(lista);
        ultimaActualizacion = Date.now();
        servidorCaidoDesde = null;
    } catch (error) {
        if (error.message === 'Sesión expirada') return;
        servidorCaidoDesde = servidorCaidoDesde || Date.now();
        const contenedor = document.getElementById('computers-container');
        if (!contenedor.querySelector('.computer-card')) {
            contenedor.innerHTML = `<div class="empty-msg">No se pudo cargar la lista de equipos. Se volverá a intentar en unos segundos.</div>`;
        }
    }
    pintarAvisoServidor();
    document.getElementById('refresh-info').textContent = textoActualizado();
}

async function deleteComputer(id, nombre) {
    if (!confirm(`¿Quitar ${nombre} del monitor?\n\nSolo desaparece de esta lista. Si la máquina sigue encendida, volverá a aparecer sola.`)) return;
    try {
        await leerJson(await fetch(`/api/computer/${encodeURIComponent(id)}`, { method: 'DELETE' }));
    } catch (e) {
        alert(`No se pudo quitar ${nombre}: ${e.message}`);
    }
    loadComputers();
}

setInterval(loadComputers, 5000);
setInterval(() => {
    if (ultimaActualizacion || servidorCaidoDesde) document.getElementById('refresh-info').textContent = textoActualizado();
}, 1000);
loadComputers();

/* ── Sidebar y vistas ───────────────────────────────── */
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const colapsado = sidebar.classList.toggle('collapsed');
    document.querySelector('.btn-toggle').setAttribute('aria-expanded', String(!colapsado));
    try { localStorage.setItem('sidebar-colapsado', colapsado ? '1' : '0'); } catch (e) { /* sin almacenamiento */ }
}
try {
    if (localStorage.getItem('sidebar-colapsado') === '1') toggleSidebar();
} catch (e) { /* sin almacenamiento */ }

let statsInterval = null;

function setView(nombre) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(b => b.removeAttribute('aria-current'));
    document.getElementById('view-' + nombre).classList.add('active');
    document.getElementById('nav-' + nombre)?.setAttribute('aria-current', 'page');
    document.getElementById('contenido').scrollTop = 0;

    if (statsInterval) { clearInterval(statsInterval); statsInterval = null; }
    if (nombre === 'stats') {
        loadStats();
        statsInterval = setInterval(loadStats, 30000);
    } else if (nombre === 'logs') {
        loadLogs(1);
    } else if (nombre === 'padron') {
        cargarConteoPadron();
    }
}

/* ── Padron ─────────────────────────────────────────── */
const zone        = document.getElementById('drop-zone');
const fileInput   = document.getElementById('fileInput');
const msg         = document.getElementById('upload-msg');
const confirmBox  = document.getElementById('upload-confirm');
const confirmText = document.getElementById('upload-confirm-text');

let archivoPendiente = null;
let totalPadron = null;

async function cargarConteoPadron() {
    try {
        const d = await leerJson(await fetch('/api/stats'));
        totalPadron = d.total_alumnos;
        document.getElementById('padron-count').textContent = formatearNumero(totalPadron);
    } catch (e) {
        document.getElementById('padron-count').textContent = '–';
    }
}

zone.onclick = () => fileInput.click();
zone.ondragover = (e) => { e.preventDefault(); zone.classList.add('hover'); };
zone.ondragleave = () => zone.classList.remove('hover');
zone.ondrop = (e) => {
    e.preventDefault();
    zone.classList.remove('hover');
    if (e.dataTransfer.files[0]) proponerArchivo(e.dataTransfer.files[0]);
};
fileInput.onchange = () => { if (fileInput.files[0]) proponerArchivo(fileInput.files[0]); };

function tamanoLegible(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/* Cuenta las filas con datos del CSV (sin el encabezado) para mostrarlo en la confirmacion. */
function contarRegistros(archivo) {
    return new Promise(resolve => {
        const lector = new FileReader();
        lector.onload = () => {
            const lineas = String(lector.result).split(/\r?\n/).filter(l => l.trim());
            resolve(Math.max(0, lineas.length - 1));
        };
        lector.onerror = () => resolve(null);
        lector.readAsText(archivo);
    });
}

async function proponerArchivo(archivo) {
    mostrarMensaje('', '');
    confirmBox.hidden = true;
    if (!/\.csv$/i.test(archivo.name)) {
        mostrarMensaje('error', `${archivo.name} no es un archivo CSV.`,
            'Exporta el padrón desde el sistema de la biblioteca en formato CSV y vuelve a intentar.');
        return;
    }
    const registros = await contarRegistros(archivo);
    if (registros === 0) {
        mostrarMensaje('error', `${archivo.name} está vacío.`,
            'Solo trae el encabezado o nada. Revisa la exportación del sistema de la biblioteca.');
        return;
    }
    archivoPendiente = archivo;
    const actual = totalPadron == null ? 'el padrón actual' : `los <strong>${formatearNumero(totalPadron)}</strong> alumnos del padrón actual`;
    const trae = registros == null ? '' : ` Trae <strong>${formatearNumero(registros)} ${registros === 1 ? 'registro' : 'registros'}</strong>.`;
    confirmText.innerHTML = `Vas a reemplazar ${actual} por los de <strong>${escapar(archivo.name)}</strong>.${trae} Los alumnos que no vengan en el archivo dejarán de poder entrar a los equipos.`;
    confirmBox.hidden = false;
    confirmBox.focus();
}

document.getElementById('upload-cancel').onclick = () => {
    archivoPendiente = null;
    fileInput.value = '';
    confirmBox.hidden = true;
    zone.focus();
};

document.getElementById('upload-confirm-btn').onclick = () => {
    if (archivoPendiente) enviarCsv(archivoPendiente);
};

function mostrarMensaje(tipo, texto, detalle, extraHtml = '') {
    msg.className = tipo;
    if (!texto) { msg.innerHTML = ''; return; }
    const spinner = tipo === 'procesando' ? '<span class="spinner" aria-hidden="true"></span>' : '';
    const det = detalle ? `<span class="msg-detail">${escapar(detalle)}</span>` : '';
    msg.innerHTML = `${spinner}<span>${escapar(texto)}</span>${extraHtml}${det}`;
}

async function enviarCsv(archivo) {
    confirmBox.hidden = true;
    zone.disabled = true;
    mostrarMensaje('procesando', `Cargando ${archivo.name}...`, 'Puede tardar unos segundos con archivos grandes. No cierres esta página.');

    const formData = new FormData();
    formData.append('file', archivo);

    try {
        const datos = await leerJson(await fetch('/api/upload', { method: 'POST', body: formData }));
        const cuantos = (datos.message || '').match(/\d+/);
        const n = cuantos ? formatearNumero(cuantos[0]) : null;
        const hora = new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', hour12: false });
        mostrarMensaje('exito', n ? `Padrón actualizado: ${n} alumnos.` : 'Padrón actualizado.', `Cargado desde ${archivo.name} a las ${hora}.`);
        archivoPendiente = null;
        fileInput.value = '';
        cargarConteoPadron();
    } catch (e) {
        if (e.message === 'Sesión expirada') return;
        const esRed = e instanceof TypeError;
        if (esRed) {
            mostrarMensaje('error', 'No se pudo conectar con el servidor.',
                'Revisa la conexión con el servidor e intenta de nuevo. El padrón anterior sigue intacto.',
                `<button type="button" class="btn-secondary" id="upload-retry">Intentar de nuevo</button>`);
            document.getElementById('upload-retry').onclick = () => enviarCsv(archivo);
        } else {
            mostrarMensaje('error', 'No se cargó el padrón.',
                `${e.message}. El padrón anterior sigue intacto.`,
                `<button type="button" class="btn-secondary" id="upload-pick-other">Elegir otro archivo</button>`);
            document.getElementById('upload-pick-other').onclick = () => { fileInput.value = ''; fileInput.click(); };
        }
    } finally {
        zone.disabled = false;
    }
}

/* ── Estadisticas ───────────────────────────────────── */
function badgeEvento(evento) {
    if (evento === 'LOGIN') return '<span class="badge badge-entrada">Entrada</span>';
    if (String(evento).startsWith('LOGOUT')) {
        const detalle = evento === 'LOGOUT_APAGADO' ? ' (equipo apagado)' : '';
        return `<span class="badge badge-salida">Salida${detalle}</span>`;
    }
    return `<span class="badge badge-salida">${escapar(evento)}</span>`;
}

function tablaEventos(filas) {
    const cuerpo = filas.map(r => `<tr>
        <td class="mono">${escapar(r.pc)}</td>
        <td class="mono">${escapar(r.matricula)}</td>
        <td class="nombre" title="${escapar(r.nombre)}">${escapar(r.nombre)}</td>
        <td class="nombre" title="${escapar(r.carrera)}">${escapar(r.carrera)}</td>
        <td class="ts">${escapar(r.hora)}</td>
        <td>${badgeEvento(r.evento)}</td>
    </tr>`).join('');
    return `<div class="table-wrap"><table class="st-table">
        <thead><tr><th>Equipo</th><th>Matrícula</th><th>Alumno</th><th>Carrera</th><th>Fecha y hora</th><th>Evento</th></tr></thead>
        <tbody>${cuerpo}</tbody></table></div>`;
}

function barras(items, campo, clase) {
    const max = items[0].total || 1;
    return items.map(it => {
        const pct = Math.max(1, Math.round((it.total / max) * 100));
        return `<div class="bar-row">
            <span class="bar-label" title="${escapar(it[campo])}">${escapar(it[campo])}</span>
            <div class="bar-track"><div class="bar-fill ${clase}" style="width:${pct}%"></div></div>
            <span class="bar-count">${formatearNumero(it.total)}</span>
        </div>`;
    }).join('');
}

function pintarLista(id, items, vacio, render) {
    document.getElementById(id).innerHTML = items && items.length ? render(items) : `<div class="empty-msg">${vacio}</div>`;
}

async function loadStats() {
    try {
        const d = await leerJson(await fetch('/api/stats'));
        totalPadron = d.total_alumnos;
        for (const [id, valor] of [['st-logins-hoy', d.logins_hoy], ['st-logins-semana', d.logins_semana],
                                   ['st-logins-mes', d.logins_mes], ['st-logins-semestre', d.logins_semestre]]) {
            document.getElementById(id).textContent = formatearNumero(valor);
        }
        pintarLista('st-recientes', d.recientes, 'Todavía no hay entradas registradas.', tablaEventos);
        pintarLista('st-top-pcs', d.top_pcs, 'Todavía no hay uso registrado.', it => barras(it, 'pc', ''));
        pintarLista('st-dist-carreras', d.dist_carreras, 'No hay padrón cargado.', it => barras(it, 'carrera', 'padron'));
        pintarLista('st-top-carreras-uso', d.top_carreras_uso, 'Todavía no hay uso registrado.', it => barras(it, 'carrera', 'uso'));
    } catch (e) {
        if (e.message === 'Sesión expirada') return;
        console.warn('Estadísticas:', e.message);
        for (const id of ['st-logins-hoy', 'st-logins-semana', 'st-logins-mes', 'st-logins-semestre']) {
            document.getElementById(id).textContent = '–';
        }
        document.getElementById('st-recientes').innerHTML =
            `<div class="empty-msg">No se pudieron cargar las estadísticas. Se volverá a intentar en 30 segundos.<br>
             <button type="button" class="btn-secondary" onclick="loadStats()">Intentar ahora</button></div>`;
        for (const id of ['st-top-pcs', 'st-dist-carreras', 'st-top-carreras-uso']) {
            document.getElementById(id).innerHTML = '<div class="empty-msg">Sin datos por ahora.</div>';
        }
    }
}

/* ── Bitacora ───────────────────────────────────────── */
function pintarDescargaBitacora(total) {
    const enlace = document.getElementById('logs-export');
    const info = document.getElementById('logs-export-info');
    if (total == null) return;
    const vacia = total === 0;
    enlace.setAttribute('aria-disabled', String(vacia));
    enlace.tabIndex = vacia ? -1 : 0;
    info.textContent = vacia
        ? 'La bitácora está vacía, no hay nada que descargar'
        : `${formatearNumero(total)} ${total === 1 ? 'registro' : 'registros'} en un archivo CSV para abrir en Excel`;
}

async function loadLogs(pagina) {
    const contenedor = document.getElementById('logs-container');
    const paginacion = document.getElementById('logs-pagination');
    try {
        const d = await leerJson(await fetch('/api/logs?page=' + pagina));
        pintarDescargaBitacora(d.total);
        if (!d.logs || !d.logs.length) {
            contenedor.innerHTML = '<div class="empty-msg">La bitácora está vacía. Se llena sola con cada entrada y salida en los equipos.</div>';
            paginacion.innerHTML = '';
            return;
        }
        contenedor.innerHTML = tablaEventos(d.logs);
        const actual = d.current_page, total = d.total_pages;
        paginacion.innerHTML =
            `<button type="button" class="btn-secondary" ${actual <= 1 ? 'disabled' : ''} onclick="loadLogs(${actual - 1})">Anterior</button>` +
            `<span class="page-info">Página ${actual} de ${total}</span>` +
            `<button type="button" class="btn-secondary" ${actual >= total ? 'disabled' : ''} onclick="loadLogs(${actual + 1})">Siguiente</button>`;
    } catch (e) {
        if (e.message === 'Sesión expirada') return;
        console.warn('Bitácora:', e.message);
        contenedor.innerHTML = `<div class="empty-msg">No se pudo cargar la bitácora.<br>
            <button type="button" class="btn-secondary" onclick="loadLogs(${pagina})">Intentar de nuevo</button></div>`;
        paginacion.innerHTML = '';
    }
}
