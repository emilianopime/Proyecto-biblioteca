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
                <span class="card-user-name" title="${escapar(info.current_user)}">${escapar(info.current_user)}</span>
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
            <h3 class="card-name" title="${escapar(pc.name)}">${escapar(pc.name)}</h3>
            <span class="status-badge ${estado}"><span class="status-dot" aria-hidden="true"></span>${et}</span>
        </div>
        <div class="card-body">${cuerpoTarjeta(pc, estado)}</div>
        <details class="card-details">
            <summary>Detalles del equipo</summary>
            <div class="card-meta"><span>Dirección en la red</span><strong>${escapar(pc.ip)}</strong></div>
            <div class="card-meta"><span>Última señal</span><strong>${escapar(cuandoDe(pc.last_heartbeat).replace(/^las /, ''))}</strong></div>
            <button type="button" class="btn-link" onclick="deleteComputer('${escapar(pc.id)}', '${escapar(pc.name)}')">Quitar de esta lista</button>
        </details>`;
}

let ultimaActualizacion = null;
let servidorCaidoDesde = null;
let filtroEstado = null;
let filtroTexto = '';

function normalizar(texto) {
    return String(texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function aplicarFiltroEstado() {
    const info = document.getElementById('filtro-estado-info');
    const q = normalizar(filtroTexto.trim());
    for (const el of document.querySelectorAll('.computer-card')) {
        const porEstado = Boolean(filtroEstado) && !el.classList.contains(filtroEstado);
        const porTexto = q && !normalizar(el.dataset.busqueda).includes(q);
        el.hidden = porEstado || porTexto;
    }
    for (const b of document.querySelectorAll('button.qs-card, #unknown-computers')) {
        const activo = b.dataset.estado === filtroEstado;
        b.setAttribute('aria-pressed', String(activo));
        const pista = b.querySelector('.qs-hint');
        if (pista) pista.textContent = activo ? 'Pulsa para ver todos' : 'Pulsa para filtrar';
    }
    const nombres = { 'libre': 'solo libres', 'en-uso': 'solo en uso', 'sin-conexion': 'solo sin conexión', 'desconocido': 'solo sin información' };
    const partes = [];
    if (filtroEstado) partes.push(nombres[filtroEstado]);
    if (q) partes.push(`que coinciden con "${filtroTexto.trim()}"`);
    info.textContent = partes.length ? `· ${partes.join(', ')}` : '';
}

for (const b of document.querySelectorAll('button.qs-card, #unknown-computers')) {
    b.onclick = () => {
        filtroEstado = filtroEstado === b.dataset.estado ? null : b.dataset.estado;
        aplicarFiltroEstado();
    };
}
document.getElementById('equipos-q').oninput = (e) => { filtroTexto = e.target.value; aplicarFiltroEstado(); };

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
        const busqueda = `${pc.name} ${(pc.info && pc.info.current_user) || ''} ${(pc.info && pc.info.cardnumber) || ''}`;
        if (!el) {
            el = document.createElement('article');
            el.className = `computer-card ${estado}`;
            el.dataset.id = pc.id;
            el.dataset.busqueda = busqueda;
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
        el.dataset.busqueda = busqueda;
    }
    for (const [id, el] of existentes) if (!vistos.has(id)) el.remove();

    const ordenActual = [...contenedor.querySelectorAll('.computer-card')].map(e => e.dataset.id);
    const ordenNuevo = ordenados.map(o => o.pc.id);
    if (ordenActual.join('|') !== ordenNuevo.join('|')) {
        for (const id of ordenNuevo) contenedor.appendChild(existentes.get(id) || contenedor.querySelector(`.computer-card[data-id="${CSS.escape(id)}"]`));
    }
    aplicarFiltroEstado();
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

        const sinInfo = document.getElementById('unknown-computers');
        sinInfo.hidden = !conteo['desconocido'];
        sinInfo.textContent = conteo['desconocido'] ? `· ${conteo['desconocido']} sin información` : '';
        if (!conteo['desconocido'] && filtroEstado === 'desconocido') filtroEstado = null;

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

const dialogoQuitar = document.getElementById('dialogo-quitar');
let equipoAQuitar = null;

function deleteComputer(id, nombre) {
    equipoAQuitar = { id, nombre };
    document.getElementById('quitar-nombre').textContent = nombre;
    dialogoQuitar.showModal();
}
document.getElementById('quitar-cancelar').onclick = () => dialogoQuitar.close();
document.getElementById('quitar-confirmar').onclick = async () => {
    const { id, nombre } = equipoAQuitar || {};
    dialogoQuitar.close();
    if (!id) return;
    const status = document.getElementById('equipos-status');
    try {
        await leerJson(await fetch(`/api/computer/${encodeURIComponent(id)}`, { method: 'DELETE' }));
        status.className = 'equipos-status exito';
        status.textContent = `${nombre} ya no aparece en la lista. Si vuelve a mandar señal, reaparece sola.`;
    } catch (e) {
        if (e.message === 'Sesión expirada') return;
        status.className = 'equipos-status error';
        status.textContent = `No se pudo quitar ${nombre}: ${e.message}`;
    }
    clearTimeout(status._timer);
    status._timer = setTimeout(() => { status.textContent = ''; }, 8000);
    loadComputers();
};

setInterval(loadComputers, 5000);
setInterval(() => {
    if (ultimaActualizacion || servidorCaidoDesde) document.getElementById('refresh-info').textContent = textoActualizado();
}, 1000);
loadComputers();

/* ── Sidebar y vistas ───────────────────────────────── */
const esMovil = () => matchMedia('(max-width: 640px)').matches;

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (esMovil()) {
        const abierto = sidebar.classList.toggle('expanded');
        document.querySelector('.btn-toggle').setAttribute('aria-expanded', String(abierto));
        return;
    }
    const colapsado = sidebar.classList.toggle('collapsed');
    document.querySelector('.btn-toggle').setAttribute('aria-expanded', String(!colapsado));
    try { localStorage.setItem('sidebar-colapsado', colapsado ? '1' : '0'); } catch (e) { /* sin almacenamiento */ }
}
try {
    if (localStorage.getItem('sidebar-colapsado') === '1') toggleSidebar();
} catch (e) { /* sin almacenamiento */ }

let statsInterval = null;

function setView(nombre) {
    document.getElementById('sidebar').classList.remove('expanded');
    document.querySelector('.btn-toggle').setAttribute('aria-expanded', String(!document.getElementById('sidebar').classList.contains('collapsed') && !esMovil()));
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

/* Abre la vista de ayuda en la seccion pedida y lleva el foco al titulo. */
function irAyuda(idSeccion) {
    setView('ayuda');
    const titulo = document.getElementById(idSeccion);
    if (!titulo) return;
    titulo.setAttribute('tabindex', '-1');
    titulo.scrollIntoView({ block: 'start' });
    titulo.focus({ preventScroll: true });
}

/* ── Padron ─────────────────────────────────────────── */
const zone        = document.getElementById('drop-zone');
const fileInput   = document.getElementById('fileInput');
const msg         = document.getElementById('upload-msg');
const confirmBox  = document.getElementById('upload-confirm');
const confirmText = document.getElementById('upload-confirm-text');

let archivoPendiente = null;
let totalPadron = null;
let padronAnterior = null;

function fechaLegible(iso) {
    // "2026-09-18 14:20" -> "18/09/2026 a las 14:20"
    const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}:\d{2})/.exec(iso || '');
    return m ? `${m[3]}/${m[2]}/${m[1]} a las ${m[4]}` : '';
}

function pintarEstadoPadron(e) {
    totalPadron = e.total;
    padronAnterior = e.anterior;
    document.getElementById('padron-count').textContent = formatearNumero(e.total);
    document.getElementById('padron-origen').textContent = e.archivo
        ? `Cargado el ${fechaLegible(e.cargado_en)} desde ${e.archivo}.`
        : '';
    const bloque = document.getElementById('padron-anterior');
    bloque.hidden = !e.anterior;
    document.getElementById('restore-confirm').hidden = true;
    if (e.anterior) {
        document.getElementById('padron-anterior-texto').textContent =
            `Se conserva el padrón que había antes${e.anterior.archivo ? `, cargado el ${fechaLegible(e.anterior.cargado_en)} desde ${e.anterior.archivo}` : ''}. Si el archivo nuevo fue un error, puedes volver a él.`;
        document.getElementById('padron-restore').textContent =
            `Restaurar el padrón anterior (${formatearNumero(e.anterior.total)} alumnos)`;
    }
}

async function cargarConteoPadron() {
    try {
        pintarEstadoPadron(await leerJson(await fetch('/api/padron')));
    } catch (e) {
        document.getElementById('padron-count').textContent = '–';
    }
}

document.getElementById('padron-restore').onclick = () => {
    if (!padronAnterior) return;
    mostrarMensaje('', '');
    document.getElementById('restore-confirm-text').innerHTML =
        `Vas a volver al padrón anterior de <strong>${formatearNumero(padronAnterior.total)}</strong> alumnos y quitar el actual de <strong>${formatearNumero(totalPadron)}</strong>. El actual queda guardado, así que puedes deshacerlo con este mismo botón.`;
    const caja = document.getElementById('restore-confirm');
    caja.hidden = false;
    caja.focus();
};
document.getElementById('restore-cancel').onclick = () => {
    document.getElementById('restore-confirm').hidden = true;
    document.getElementById('padron-restore').focus();
};
document.getElementById('restore-confirm-btn').onclick = async () => {
    const boton = document.getElementById('restore-confirm-btn');
    boton.disabled = true;
    mostrarMensaje('procesando', 'Restaurando el padrón anterior...');
    try {
        const e = await leerJson(await fetch('/api/padron/restaurar', { method: 'POST' }));
        pintarEstadoPadron(e);
        mostrarMensaje('exito', `Padrón restaurado: ${formatearNumero(e.total)} alumnos.`,
            e.archivo ? `Es el que se había cargado desde ${e.archivo}.` : '');
    } catch (err) {
        if (err.message === 'Sesión expirada') return;
        mostrarMensaje('error', 'No se pudo restaurar el padrón.', `${err.message}. El padrón actual sigue intacto.`);
    } finally {
        boton.disabled = false;
    }
};

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

let cargaEnCurso = null;

async function enviarCsv(archivo) {
    confirmBox.hidden = true;
    zone.disabled = true;
    mostrarMensaje('procesando', `Cargando ${archivo.name}...`, 'Puede tardar unos segundos con archivos grandes. No cierres esta página.',
        '<button type="button" class="btn-secondary" id="upload-abort">Cancelar</button>');
    cargaEnCurso = new AbortController();
    document.getElementById('upload-abort').onclick = () => cargaEnCurso.abort();

    const formData = new FormData();
    formData.append('file', archivo);

    try {
        const datos = await leerJson(await fetch('/api/upload', { method: 'POST', body: formData, signal: cargaEnCurso.signal }));
        const cuantos = (datos.message || '').match(/\d+/);
        const n = cuantos ? formatearNumero(cuantos[0]) : null;
        const hora = new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', hour12: false });
        mostrarMensaje('exito', n ? `Padrón actualizado: ${n} alumnos.` : 'Padrón actualizado.', `Cargado desde ${archivo.name} a las ${hora}.`);
        archivoPendiente = null;
        fileInput.value = '';
        cargarConteoPadron();
    } catch (e) {
        if (e.message === 'Sesión expirada') return;
        if (e.name === 'AbortError') {
            mostrarMensaje('error', 'Carga cancelada.',
                'Si el servidor ya había terminado de procesar el archivo, el padrón pudo quedar reemplazado; revisa el conteo de arriba.');
            cargarConteoPadron();
            return;
        }
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
        cargaEnCurso = null;
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
        <caption class="visually-hidden">Entradas y salidas de alumnos en los equipos</caption>
        <thead><tr><th scope="col">Equipo</th><th scope="col">Matrícula</th><th scope="col">Alumno</th><th scope="col">Carrera</th><th scope="col">Fecha y hora</th><th scope="col">Evento</th></tr></thead>
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
        const hoy = new Date();
        document.getElementById('semestre-desde').textContent = hoy.getMonth() >= 7 ? '· desde el 1 de agosto' : '· desde el 1 de enero';
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

/* ── Generar reporte ────────────────────────────────── */
const reportePeriodo = document.getElementById('reporte-periodo');
const reporteFechas  = document.getElementById('reporte-fechas');
const reporteAviso   = document.getElementById('reporte-aviso');

function actualizarReporte() {
    const periodo = reportePeriodo.value;
    const esRango = periodo === 'rango';
    reporteFechas.hidden = !esRango;

    const params = new URLSearchParams({ periodo });
    let aviso = '';
    if (esRango) {
        const desde = document.getElementById('reporte-desde').value;
        const hasta = document.getElementById('reporte-hasta').value;
        if (!desde || !hasta) aviso = 'Elige las dos fechas del rango.';
        else if (desde > hasta) aviso = 'La fecha inicial no puede ser posterior a la final.';
        params.set('desde', desde);
        params.set('hasta', hasta);
    }
    reporteAviso.textContent = aviso;
    for (const [id, ruta] of [['reporte-ver', '/reporte'], ['reporte-pdf', '/reporte.pdf'], ['reporte-xlsx', '/reporte.xlsx']]) {
        const enlace = document.getElementById(id);
        enlace.href = `${ruta}?${params}`;
        enlace.setAttribute('aria-disabled', String(Boolean(aviso)));
        enlace.tabIndex = aviso ? -1 : 0;
    }
}

for (const [id, tipo] of [['reporte-pdf', 'el PDF'], ['reporte-xlsx', 'el Excel']]) {
    document.getElementById(id).addEventListener('click', (e) => {
        if (e.currentTarget.getAttribute('aria-disabled') === 'true') { e.preventDefault(); return; }
        const status = document.getElementById('reporte-status');
        status.textContent = `Preparando ${tipo}... se descargará solo en unos segundos.`;
        clearTimeout(status._timer);
        status._timer = setTimeout(() => { status.textContent = ''; }, 6000);
    });
}
reportePeriodo.onchange = actualizarReporte;
document.getElementById('reporte-desde').onchange = actualizarReporte;
document.getElementById('reporte-hasta').onchange = actualizarReporte;
actualizarReporte();

/* ── Bitacora ───────────────────────────────────────── */
function filtrosBitacora() {
    const f = {
        q: document.getElementById('logs-q').value.trim(),
        evento: document.getElementById('logs-evento').value,
        desde: document.getElementById('logs-desde').value,
        hasta: document.getElementById('logs-hasta').value,
    };
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(f)) if (v) params.set(k, v);
    return { params, activos: [...params.keys()].length > 0, valores: f };
}

function pintarDescargaBitacora(total, filtros) {
    const enlace = document.getElementById('logs-export');
    const info = document.getElementById('logs-export-info');
    if (total == null) return;
    const vacia = total === 0;
    enlace.setAttribute('aria-disabled', String(vacia));
    enlace.tabIndex = vacia ? -1 : 0;
    enlace.href = '/api/logs/export' + (filtros.activos ? `?${filtros.params}` : '');
    enlace.lastChild.textContent = filtros.activos ? ' Descargar estos registros' : ' Descargar bitácora completa';
    info.textContent = vacia
        ? (filtros.activos ? 'Ningún registro coincide, no hay nada que descargar' : 'La bitácora está vacía, no hay nada que descargar')
        : `${formatearNumero(total)} ${total === 1 ? 'registro' : 'registros'} en un archivo CSV para abrir en Excel`;
}

let debounceBitacora = null;
function filtrarBitacora() {
    clearTimeout(debounceBitacora);
    debounceBitacora = setTimeout(() => loadLogs(1), 300);
}
document.getElementById('logs-q').oninput = filtrarBitacora;
document.getElementById('logs-evento').onchange = () => loadLogs(1);
document.getElementById('logs-desde').onchange = () => loadLogs(1);
document.getElementById('logs-hasta').onchange = () => loadLogs(1);
document.getElementById('logs-clear').onclick = () => {
    for (const id of ['logs-q', 'logs-evento', 'logs-desde', 'logs-hasta']) document.getElementById(id).value = '';
    loadLogs(1);
    document.getElementById('logs-q').focus();
};

async function loadLogs(pagina) {
    const contenedor = document.getElementById('logs-container');
    const paginacion = document.getElementById('logs-pagination');
    const filtros = filtrosBitacora();
    document.getElementById('logs-clear').hidden = !filtros.activos;
    const aviso = document.getElementById('logs-aviso');
    if (filtros.valores.desde && filtros.valores.hasta && filtros.valores.desde > filtros.valores.hasta) {
        aviso.textContent = 'La fecha inicial no puede ser posterior a la final.';
        return;
    }
    aviso.textContent = '';
    filtros.params.set('page', pagina);
    try {
        const d = await leerJson(await fetch('/api/logs?' + filtros.params));
        pintarDescargaBitacora(d.total, filtros);
        if (!d.logs || !d.logs.length) {
            contenedor.innerHTML = filtros.activos
                ? `<div class="empty-msg">Ningún registro coincide${filtros.valores.q ? ` con "${escapar(filtros.valores.q)}"` : ''} en el periodo elegido.<br>
                   <button type="button" class="btn-secondary" onclick="document.getElementById('logs-clear').click()">Limpiar filtros</button></div>`
                : '<div class="empty-msg">La bitácora está vacía. Se llena sola con cada entrada y salida en los equipos.</div>';
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
