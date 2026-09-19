"""
Pruebas de la interfaz del dashboard con un navegador real (Chrome headless
via Playwright). Levantan la app Flask en un hilo, sin base de datos, y
simulan las respuestas de /api/* desde el navegador.

Se saltan si Playwright o Google Chrome no estan disponibles.
"""
import json
import os
import socket
import threading

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

for var in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_PORT"):
    os.environ.pop(var, None)
os.environ["DASHBOARD_USER"] = "prueba"
os.environ["DASHBOARD_PASSWORD"] = "prueba-secreta"

import main  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


def pc(nombre, estado="online", locked=True, usuario=None, matricula=None, hora="2026-09-18 13:05:22"):
    return {
        "id": nombre, "name": nombre, "ip": "192.168.10.11", "status": estado,
        "last_heartbeat": hora,
        "info": {"locked": locked, "current_user": usuario if usuario else ("BLOQUEADA" if locked else None),
                 "cardnumber": matricula},
    }


SEIS_EQUIPOS = [
    pc("LAB-PC-06", estado="offline", hora="2026-09-18 13:03:10"),
    pc("LAB-PC-01", locked=False, usuario="Ana Torres Vega", matricula=10203),
    pc("LAB-PC-02"),
    pc("LAB-PC-03", locked=False, usuario="Luis Mora Rangel", matricula=10204),
    pc("LAB-PC-04"),
    pc("LAB-PC-05"),
]

STATS = {
    "total_alumnos": 94448, "logins_hoy": 3, "logins_semana": 3, "logins_mes": 3, "logins_semestre": 3,
    "recientes": [{"pc": "LAB-PC-01", "matricula": 10203, "nombre": "Ana Torres Vega",
                   "carrera": "Licenciatura En Estomatologia", "hora": "18/09/2026 13:03", "evento": "LOGIN"}],
    "top_pcs": [{"pc": "LAB-PC-01", "total": 3}],
    "dist_carreras": [{"carrera": "Licenciatura En Administracion De Empresas", "total": 6778}],
    "top_carreras_uso": [{"carrera": "Invitado", "total": 3}],
}
LOGS = {"logs": STATS["recientes"], "current_page": 1, "total_pages": 46, "total": 909}
PADRON = {"total": 94448, "cargado_en": "2026-09-18 14:20", "archivo": "padron_2026B.csv",
          "anterior": {"total": 12431, "cargado_en": "2026-08-12 09:05", "archivo": "padron_2026A.csv"}}
PADRON_SIN_ANTERIOR = {"total": 94448, "cargado_en": None, "archivo": None, "anterior": None}


@pytest.fixture(scope="module")
def servidor():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    srv = make_server("127.0.0.1", puerto, main.app)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cliente = main.app.test_client()
    with cliente.session_transaction() as sesion:
        sesion["authenticated"] = True
        sesion["username"] = "prueba"
    cookie = cliente.get_cookie("session").value
    yield {"url": f"http://127.0.0.1:{puerto}", "cookie": cookie, "puerto": puerto}
    srv.shutdown()


@pytest.fixture(scope="module")
def navegador():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:  # pragma: no cover
            pytest.skip(f"Chrome no disponible: {e}")
        yield b
        b.close()


def abrir(navegador, servidor, equipos=SEIS_EQUIPOS, ancho=1440, alto=900, con_sesion=True, upload=None, padron=PADRON, esquema="dark"):
    """Abre el dashboard con respuestas de API simuladas y devuelve (page, peticiones)."""
    ctx = navegador.new_context(viewport={"width": ancho, "height": alto}, locale="es-MX", color_scheme=esquema)
    if con_sesion:
        ctx.add_cookies([{"name": "session", "value": servidor["cookie"], "domain": "127.0.0.1", "path": "/"}])
    page = ctx.new_page()
    peticiones = []

    def responder(route):
        url = route.request.url
        peticiones.append((route.request.method, url.split(servidor["url"])[-1]))
        if "/api/computers" in url:
            lista = equipos() if callable(equipos) else equipos
            cuerpo = {"computers": lista, "total": len(lista),
                      "online": sum(1 for c in lista if c["status"] == "online"),
                      "offline": sum(1 for c in lista if c["status"] == "offline")}
            return route.fulfill(json=cuerpo)
        if "/api/padron/restaurar" in url:
            nuevo_estado = {**padron["anterior"], "anterior": {k: padron[k] for k in ("total", "cargado_en", "archivo")}}
            return route.fulfill(json=nuevo_estado)
        if "/api/padron" in url:
            return route.fulfill(json=padron)
        if "/api/stats" in url:
            return route.fulfill(json=STATS)
        if "/api/logs" in url:
            return route.fulfill(json=LOGS)
        if "/api/upload" in url:
            if upload == "red":
                return route.abort("connectionfailed")
            if upload == "error":
                return route.fulfill(status=400, json={"error": "No encontre la columna de matricula en el archivo. Columnas que trae: a, b"})
            return route.fulfill(json={"message": "Exito: se cargaron 94447 alumnos"})
        return route.continue_()

    page.route("**/api/**", responder)
    page.goto(servidor["url"] + "/")
    page.wait_for_selector(".computer-card, .empty-msg", timeout=5000)
    return page, peticiones


def texto_tarjeta(page, nombre):
    return page.locator(f".computer-card[data-id='{nombre}']").inner_text()


# ---------------------------------------------------------------------------
# Estado de los equipos
# ---------------------------------------------------------------------------

def test_equipo_sin_conexion_no_se_anuncia_como_disponible(navegador, servidor):
    page, _ = abrir(navegador, servidor)

    t = texto_tarjeta(page, "LAB-PC-06")
    assert "Sin conexión" in t
    assert "disponible" not in t.lower()
    assert "bloqueada" not in t.lower()


def test_equipo_libre_se_llama_libre_y_equipo_ocupado_muestra_alumno(navegador, servidor):
    page, _ = abrir(navegador, servidor)

    assert "Libre" in texto_tarjeta(page, "LAB-PC-02")
    assert "Ana Torres Vega" in texto_tarjeta(page, "LAB-PC-01")
    assert "En uso" in texto_tarjeta(page, "LAB-PC-01")


def test_contadores_responden_libres_en_uso_y_sin_conexion(navegador, servidor):
    page, _ = abrir(navegador, servidor)

    assert page.locator("#libres-computers").inner_text() == "3"
    assert page.locator("#en-uso-computers").inner_text() == "2"
    assert page.locator("#sin-conexion-computers").inner_text() == "1"


def test_tarjetas_ordenadas_libres_primero_luego_en_uso_luego_sin_conexion(navegador, servidor):
    page, _ = abrir(navegador, servidor)

    nombres = page.locator(".computer-card").evaluate_all("els => els.map(e => e.dataset.id)")
    assert nombres == ["LAB-PC-02", "LAB-PC-04", "LAB-PC-05", "LAB-PC-01", "LAB-PC-03", "LAB-PC-06"]


def test_sin_equipos_muestra_mensaje_que_explica_que_hacer(navegador, servidor):
    page, _ = abrir(navegador, servidor, equipos=[])

    assert "kiosko" in page.locator("#computers-container").inner_text().lower()


def test_no_hay_jerga_de_red_en_la_vista_de_equipos(navegador, servidor):
    page, _ = abrir(navegador, servidor)

    texto = page.locator("#view-equipos").inner_text().lower()
    for palabra in ("nodo", "latido", "offline", "ip red local"):
        assert palabra not in texto, palabra


# ---------------------------------------------------------------------------
# Accesibilidad: teclado, foco, contraste, tamano de texto
# ---------------------------------------------------------------------------

def test_sidebar_navegable_por_teclado(navegador, servidor):
    page, _ = abrir(navegador, servidor)

    assert page.locator("button.nav-item").count() >= 4
    boton = page.locator("button.nav-item[data-view='stats']")
    boton.focus()
    page.keyboard.press("Enter")
    assert page.locator("#view-stats").is_visible()
    assert boton.get_attribute("aria-current") == "page"


def test_refresco_de_equipos_conserva_el_foco(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    objetivo = page.locator(".computer-card[data-id='LAB-PC-02'] summary")
    objetivo.focus()

    page.evaluate("loadComputers()")
    page.wait_for_timeout(300)

    activo = page.evaluate("document.activeElement && document.activeElement.closest('.computer-card')?.dataset.id")
    assert activo == "LAB-PC-02"


def test_texto_visible_no_baja_de_12px(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    for vista in ("equipos", "stats", "logs", "padron"):
        page.evaluate(f"setView('{vista}')")
        page.wait_for_timeout(300)
        chicos = page.evaluate("""() => {
            const out = [];
            for (const el of document.querySelectorAll('body *')) {
                if (!el.offsetParent && el.tagName !== 'SUMMARY') continue;
                const propio = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
                if (!propio) continue;
                const px = parseFloat(getComputedStyle(el).fontSize);
                if (px < 12) out.push(el.tagName + '.' + el.className + ' ' + px.toFixed(1));
            }
            return out;
        }""")
        assert chicos == [], (vista, chicos)


def contraste(page, selector):
    return page.evaluate("""(sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const lum = (c) => {
            const [r, g, b] = c.match(/\\d+(\\.\\d+)?/g).map(Number);
            const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
        };
        const parse = (c) => { const v = c.match(/\\d+(\\.\\d+)?/g).map(Number); return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 }; };
        // Componer de abajo hacia arriba todos los fondos con alfa hasta el body
        const capas = []; let n = el;
        while (n) { const c = parse(getComputedStyle(n).backgroundColor); if (c.a > 0) capas.push(c); n = n.parentElement; }
        let fondo = { r: 0, g: 0, b: 0 };
        for (const c of capas.reverse()) fondo = { r: c.a * c.r + (1 - c.a) * fondo.r, g: c.a * c.g + (1 - c.a) * fondo.g, b: c.a * c.b + (1 - c.a) * fondo.b };
        const bg = `rgb(${fondo.r}, ${fondo.g}, ${fondo.b})`;
        const l1 = lum(getComputedStyle(el).color), l2 = lum(bg);
        return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    }""", selector)


@pytest.mark.parametrize("selector", [
    ".panel-title", ".qs-label", ".nav-section", ".brand-sub", ".page-header p",
    ".btn-logout", ".section-head h2", ".card-meta",
])
def test_texto_secundario_cumple_contraste_aa(navegador, servidor, selector):
    page, _ = abrir(navegador, servidor)
    ratio = contraste(page, selector)
    assert ratio is not None, f"no existe {selector}"
    assert ratio >= 4.5, f"{selector}: {ratio:.2f}:1"


def test_badges_de_estado_cumplen_contraste(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    for sel in (".computer-card[data-id='LAB-PC-02'] .status-badge",
                ".computer-card[data-id='LAB-PC-01'] .status-badge",
                ".computer-card[data-id='LAB-PC-06'] .status-badge"):
        assert contraste(page, sel) >= 4.5, sel


def test_la_pagina_tiene_un_solo_scroll(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    alto = page.evaluate("document.documentElement.scrollHeight")
    assert alto <= 900, f"el documento mide {alto}px en un viewport de 900px: hay doble scroll"


# ---------------------------------------------------------------------------
# Carga del padron
# ---------------------------------------------------------------------------

def ir_a_padron(page):
    page.evaluate("setView('padron')")
    page.wait_for_selector("#view-padron", state="visible")


def elegir_archivo(page):
    page.set_input_files("#fileInput", {"name": "padron_2026B.csv", "mimeType": "text/csv",
                                        "buffer": b"Carnet,Apellido(s),Nombre(s)\n1,PEREZ,JUAN\n"})


def test_elegir_archivo_pide_confirmacion_antes_de_enviar(navegador, servidor):
    page, peticiones = abrir(navegador, servidor)
    ir_a_padron(page)

    elegir_archivo(page)

    confirmacion = page.locator("#upload-confirm")
    assert confirmacion.is_visible()
    assert "padron_2026B.csv" in confirmacion.inner_text()
    assert "94,448" in confirmacion.inner_text()
    assert not any("/api/upload" in ruta for _, ruta in peticiones)


def test_cancelar_no_envia_nada(navegador, servidor):
    page, peticiones = abrir(navegador, servidor)
    ir_a_padron(page)
    elegir_archivo(page)

    page.click("#upload-cancel")

    assert not page.locator("#upload-confirm").is_visible()
    assert not any("/api/upload" in ruta for _, ruta in peticiones)


def test_confirmar_envia_y_muestra_exito_con_conteo(navegador, servidor):
    page, peticiones = abrir(navegador, servidor)
    ir_a_padron(page)
    elegir_archivo(page)

    page.click("#upload-confirm-btn")
    page.wait_for_selector("#upload-msg.exito")

    assert any("/api/upload" in ruta for _, ruta in peticiones)
    assert "94,447" in page.locator("#upload-msg").inner_text()


def test_error_de_red_explica_y_permite_reintentar(navegador, servidor):
    page, _ = abrir(navegador, servidor, upload="red")
    ir_a_padron(page)
    elegir_archivo(page)

    page.click("#upload-confirm-btn")
    page.wait_for_selector("#upload-msg.error")

    assert "conectar" in page.locator("#upload-msg").inner_text().lower()
    assert page.locator("#upload-retry").is_visible()


def test_error_del_servidor_muestra_el_motivo(navegador, servidor):
    page, _ = abrir(navegador, servidor, upload="error")
    ir_a_padron(page)
    elegir_archivo(page)

    page.click("#upload-confirm-btn")
    page.wait_for_selector("#upload-msg.error")

    assert "matricula" in page.locator("#upload-msg").inner_text().lower()


def test_el_input_solo_acepta_csv(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    assert ".csv" in page.get_attribute("#fileInput", "accept")


# ---------------------------------------------------------------------------
# Responsive
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vista", ["equipos", "stats", "logs", "padron"])
def test_sin_desbordamiento_horizontal_a_400px(navegador, servidor, vista):
    page, _ = abrir(navegador, servidor, ancho=400, alto=850)
    page.evaluate(f"setView('{vista}')")
    page.wait_for_timeout(400)

    desbordan = page.evaluate("""() => {
        const out = [];
        for (const el of document.querySelectorAll('body *')) {
            const r = el.getBoundingClientRect();
            if (r.width && r.right > innerWidth + 1 && !el.closest('.table-wrap')) out.push(el.tagName + '.' + el.className);
        }
        return out;
    }""")
    assert desbordan == [], desbordan


def test_topbar_no_se_encima_a_400px(navegador, servidor):
    page, _ = abrir(navegador, servidor, ancho=400, alto=850)
    marca = page.locator(".brand").bounding_box()
    salir = page.locator(".btn-logout").bounding_box()
    assert marca["x"] + marca["width"] <= salir["x"], "la marca se encima con el boton de salir"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_conserva_el_usuario_tras_un_error(navegador, servidor):
    ctx = navegador.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(servidor["url"] + "/login")
    page.fill("#username", "prueba")
    page.fill("#password", "incorrecta")
    page.click(".btn-login")
    page.wait_for_selector(".error-msg")

    assert page.input_value("#username") == "prueba"
    assert "contraseña" in page.locator(".error-msg").inner_text().lower()
    assert "Iniciar sesión" in page.locator(".btn-login").inner_text()


def test_login_usa_la_misma_familia_visual_que_el_dashboard(navegador, servidor):
    ctx = navegador.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(servidor["url"] + "/login")
    fuente = page.evaluate("getComputedStyle(document.body).fontFamily")
    assert "IBM Plex Sans" in fuente
    assert page.locator(".brand-mark svg").count() == 1, "el logo debe ser SVG, no emoji"
    assert contraste(page, ".field label") >= 4.5
    assert contraste(page, ".login-footer") >= 4.5


# ---------------------------------------------------------------------------
# Defectos encontrados en la segunda critica
# ---------------------------------------------------------------------------

def test_si_el_servidor_deja_de_responder_el_monitor_lo_dice_y_lo_sigue_diciendo(navegador, servidor):
    llamadas = {"n": 0}

    def equipos():
        llamadas["n"] += 1
        if llamadas["n"] > 1:
            raise RuntimeError("servidor caido")
        return SEIS_EQUIPOS

    ctx = navegador.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_cookies([{"name": "session", "value": servidor["cookie"], "domain": "127.0.0.1", "path": "/"}])
    page = ctx.new_page()

    def responder(route):
        if "/api/computers" in route.request.url:
            try:
                lista = equipos()
            except RuntimeError:
                return route.abort("connectionfailed")
            return route.fulfill(json={"computers": lista, "total": 6, "online": 5, "offline": 1})
        return route.continue_()

    page.route("**/api/**", responder)
    page.goto(servidor["url"] + "/")
    page.wait_for_selector(".computer-card")

    page.evaluate("loadComputers()")
    page.wait_for_timeout(2500)  # el ticker de 1 s ya corrio varias veces

    assert "sin respuesta del servidor" in page.locator("#refresh-info").inner_text()
    assert page.locator("#server-warning").is_visible()


def test_tras_un_archivo_rechazado_se_ofrece_elegir_otro_no_reintentar(navegador, servidor):
    page, _ = abrir(navegador, servidor, upload="error")
    ir_a_padron(page)
    elegir_archivo(page)
    page.click("#upload-confirm-btn")
    page.wait_for_selector("#upload-msg.error")

    assert page.locator("#upload-pick-other").is_visible()
    assert page.locator("#upload-retry").count() == 0


def test_equipo_sin_informacion_aparece_en_el_resumen(navegador, servidor):
    equipos = SEIS_EQUIPOS + [pc("LAB-PC-07", locked=False, usuario=None)]
    page, _ = abrir(navegador, servidor, equipos=equipos)

    assert "1 sin información" in page.locator(".section-meta").inner_text()


def test_equipo_apagado_desde_otro_dia_muestra_la_fecha(navegador, servidor):
    equipos = [pc("LAB-PC-06", estado="offline", hora="2026-09-17 21:12:00")]
    page, _ = abrir(navegador, servidor, equipos=equipos)

    texto = texto_tarjeta(page, "LAB-PC-06")
    assert "17/09" in texto or "ayer" in texto
    assert "21:12" in texto


def test_error_en_estadisticas_no_deja_paneles_cargando_ni_expone_la_excepcion(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.route("**/api/stats", lambda r: r.fulfill(status=500, json={"error": "sqlite3.OperationalError: database is locked"}))
    page.evaluate("setView('stats')")
    page.wait_for_timeout(500)

    texto = page.locator("#view-stats").inner_text()
    assert "Cargando" not in texto
    assert "OperationalError" not in texto
    assert "No se pudieron cargar" in texto


def test_nombres_largos_no_desbordan_en_movil(navegador, servidor):
    equipos = [pc("LAB-BIBLIOTECA-PLANTA-BAJA-ESCRITORIO-0000000042", locked=False,
                  usuario="María Fernanda de los Ángeles Rodríguez Villaseñor", matricula=10203)]
    page, _ = abrir(navegador, servidor, equipos=equipos, ancho=400, alto=850)

    desbordan = page.evaluate("""() => [...document.querySelectorAll('.computer-card, .computer-card *')]
        .filter(el => el.getBoundingClientRect().right > innerWidth + 1).map(el => el.className)""")
    assert desbordan == []


def test_menu_colapsado_conserva_nombres_accesibles(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.evaluate("toggleSidebar()")

    nombres = page.locator("button.nav-item").evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")
    assert all(nombres), nombres


@pytest.mark.parametrize("vista", ["padron", "stats", "logs"])
def test_cada_vista_tiene_encabezados_de_seccion(navegador, servidor, vista):
    page, _ = abrir(navegador, servidor)
    page.evaluate(f"setView('{vista}')")
    assert page.locator(f"#view-{vista} h2").count() >= 1


def test_la_confirmacion_no_enfoca_el_boton_destructivo(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    ir_a_padron(page)
    elegir_archivo(page)

    activo = page.evaluate("document.activeElement.id")
    assert activo != "upload-confirm-btn"
    assert "1 registro" in page.locator("#upload-confirm").inner_text()


def test_con_servidor_sano_no_se_muestra_el_aviso_de_sin_conexion(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.wait_for_timeout(300)

    assert not page.locator("#server-warning").is_visible()
    assert "actualizado" in page.locator("#refresh-info").inner_text()


def test_el_boton_de_descarga_dice_que_se_lleva_y_cuantos_registros(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.evaluate("setView('logs')")
    page.wait_for_selector("#logs-container table")

    boton = page.locator("#logs-export")
    assert "Descargar bitácora completa" in boton.inner_text()
    assert "909 registros" in page.locator("#logs-export-info").inner_text()
    assert boton.get_attribute("href") == "/api/logs/export"


def test_con_bitacora_vacia_no_hay_nada_que_descargar(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.route("**/api/logs*", lambda r: r.fulfill(json={"logs": [], "current_page": 1, "total_pages": 1, "total": 0}))
    page.evaluate("setView('logs')")
    page.wait_for_timeout(400)

    assert page.locator("#logs-export").get_attribute("aria-disabled") == "true"
    assert "nada que descargar" in page.locator("#logs-export-info").inner_text().lower()


# ---------------------------------------------------------------------------
# Generar reporte desde Estadisticas
# ---------------------------------------------------------------------------

def test_el_bloque_de_reporte_ofrece_periodo_y_tres_salidas(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.evaluate("setView('stats')")
    page.wait_for_selector("#reporte-form")

    page.select_option("#reporte-periodo", "mes-anterior")
    ver = page.locator("#reporte-ver").get_attribute("href")
    pdf = page.locator("#reporte-pdf").get_attribute("href")
    xlsx = page.locator("#reporte-xlsx").get_attribute("href")

    assert ver.startswith("/reporte?") and "periodo=mes-anterior" in ver
    assert pdf.startswith("/reporte.pdf?") and "periodo=mes-anterior" in pdf
    assert xlsx.startswith("/reporte.xlsx?") and "periodo=mes-anterior" in xlsx
    assert page.locator("#reporte-ver").get_attribute("target") == "_blank"


def test_el_rango_de_fechas_solo_aparece_al_elegir_rango_y_se_valida(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.evaluate("setView('stats')")
    page.wait_for_selector("#reporte-form")

    assert not page.locator("#reporte-fechas").is_visible()
    page.select_option("#reporte-periodo", "rango")
    assert page.locator("#reporte-fechas").is_visible()

    page.fill("#reporte-desde", "2026-09-10")
    page.fill("#reporte-hasta", "2026-09-01")
    page.dispatch_event("#reporte-hasta", "change")
    assert page.locator("#reporte-ver").get_attribute("aria-disabled") == "true"
    assert "posterior" in page.locator("#reporte-aviso").inner_text()

    page.fill("#reporte-hasta", "2026-09-18")
    page.dispatch_event("#reporte-hasta", "change")
    assert page.locator("#reporte-ver").get_attribute("aria-disabled") == "false"
    assert "desde=2026-09-10" in page.locator("#reporte-xlsx").get_attribute("href")
    assert "hasta=2026-09-18" in page.locator("#reporte-xlsx").get_attribute("href")


# ---------------------------------------------------------------------------
# Restaurar el padron anterior
# ---------------------------------------------------------------------------

def test_padron_muestra_de_donde_salio_y_ofrece_restaurar_el_anterior(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    ir_a_padron(page)
    page.wait_for_selector("#padron-restore")

    texto = page.locator("#view-padron").inner_text()
    assert "94,448" in texto and "padron_2026B.csv" in texto
    assert "12,431" in page.locator("#padron-restore").inner_text()


def test_sin_padron_anterior_no_se_ofrece_restaurar(navegador, servidor):
    page, _ = abrir(navegador, servidor, padron=PADRON_SIN_ANTERIOR)
    ir_a_padron(page)
    page.wait_for_selector("#padron-count:not(:has-text('–'))")

    assert not page.locator("#padron-restore").is_visible()


def test_restaurar_pide_confirmacion_y_luego_muestra_el_resultado(navegador, servidor):
    page, peticiones = abrir(navegador, servidor)
    ir_a_padron(page)
    page.wait_for_selector("#padron-restore")

    page.click("#padron-restore")
    confirmacion = page.locator("#restore-confirm")
    assert confirmacion.is_visible()
    assert "12,431" in confirmacion.inner_text() and "94,448" in confirmacion.inner_text()
    assert not any("restaurar" in ruta for _, ruta in peticiones)

    page.click("#restore-cancel")
    assert not confirmacion.is_visible()

    page.click("#padron-restore")
    page.click("#restore-confirm-btn")
    page.wait_for_selector("#upload-msg.exito")

    assert any(metodo == "POST" and "restaurar" in ruta for metodo, ruta in peticiones)
    assert "12,431" in page.locator("#upload-msg").inner_text()
    assert "94,448" in page.locator("#padron-restore").inner_text()


# ---------------------------------------------------------------------------
# Buscar y filtrar en la bitacora
# ---------------------------------------------------------------------------

def ir_a_bitacora(page):
    page.evaluate("setView('logs')")
    page.wait_for_selector("#logs-container table")


def test_buscar_en_bitacora_manda_el_texto_al_servidor_y_a_la_descarga(navegador, servidor):
    page, peticiones = abrir(navegador, servidor)
    ir_a_bitacora(page)

    page.fill("#logs-q", "LAB-PC-01")
    page.wait_for_timeout(600)   # espera al debounce

    assert any("/api/logs?" in ruta and "q=LAB-PC-01" in ruta for _, ruta in peticiones)
    assert "q=LAB-PC-01" in page.locator("#logs-export").get_attribute("href")
    assert "909 registros" in page.locator("#logs-export-info").inner_text()


def test_filtrar_por_evento_y_fechas_y_limpiar(navegador, servidor):
    page, peticiones = abrir(navegador, servidor)
    ir_a_bitacora(page)

    page.select_option("#logs-evento", "salida")
    page.fill("#logs-desde", "2026-09-01")
    page.fill("#logs-hasta", "2026-09-18")
    page.dispatch_event("#logs-hasta", "change")
    page.wait_for_timeout(600)

    ultima = [ruta for _, ruta in peticiones if "/api/logs?" in ruta][-1]
    assert "evento=salida" in ultima and "desde=2026-09-01" in ultima and "hasta=2026-09-18" in ultima
    assert "page=1" in ultima
    assert page.locator("#logs-clear").is_visible()

    page.click("#logs-clear")
    page.wait_for_timeout(600)
    ultima = [ruta for _, ruta in peticiones if "/api/logs?" in ruta][-1]
    assert "evento=" not in ultima and "desde=" not in ultima
    assert page.input_value("#logs-q") == ""
    assert not page.locator("#logs-clear").is_visible()


def test_sin_resultados_con_filtros_lo_dice_y_ofrece_limpiar(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    ir_a_bitacora(page)
    page.route("**/api/logs?*", lambda r: r.fulfill(json={"logs": [], "current_page": 1, "total_pages": 1, "total": 0}))

    page.fill("#logs-q", "nadie")
    page.wait_for_timeout(600)

    texto = page.locator("#logs-container").inner_text()
    assert "ningún registro" in texto.lower()
    assert "nadie" in texto
    assert page.locator("#logs-export").get_attribute("aria-disabled") == "true"


# ---------------------------------------------------------------------------
# Filtrar equipos por estado desde los contadores
# ---------------------------------------------------------------------------

def test_los_contadores_filtran_las_tarjetas_por_estado(navegador, servidor):
    page, _ = abrir(navegador, servidor)

    botones = page.locator("button.qs-card")
    assert botones.count() == 3
    page.click("button.qs-card.libre")

    visibles = page.locator(".computer-card:visible").evaluate_all("els => els.map(e => e.dataset.id)")
    assert visibles == ["LAB-PC-02", "LAB-PC-04", "LAB-PC-05"]
    assert page.locator("button.qs-card.libre").get_attribute("aria-pressed") == "true"
    assert "libres" in page.locator("#filtro-estado-info").inner_text().lower()

    page.click("button.qs-card.libre")   # volver a pulsar quita el filtro
    assert page.locator(".computer-card:visible").count() == 6
    assert page.locator("button.qs-card.libre").get_attribute("aria-pressed") == "false"


def test_el_filtro_por_estado_sobrevive_al_refresco(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.click("button.qs-card.sin-conexion")
    page.evaluate("loadComputers()")
    page.wait_for_timeout(300)

    assert page.locator(".computer-card:visible").evaluate_all("els => els.map(e => e.dataset.id)") == ["LAB-PC-06"]


# ---------------------------------------------------------------------------
# Dialogo propio para quitar un equipo y cancelar una carga en curso
# ---------------------------------------------------------------------------

def test_quitar_equipo_usa_un_dialogo_propio_y_no_el_del_navegador(navegador, servidor):
    page, peticiones = abrir(navegador, servidor)
    page.on("dialog", lambda d: pytest.fail("se abrio un dialogo nativo del navegador"))
    page.evaluate("document.querySelector('.computer-card[data-id=\\'LAB-PC-02\\'] details').open = true")

    page.click(".computer-card[data-id='LAB-PC-02'] .btn-link")

    dialogo = page.locator("dialog#dialogo-quitar")
    assert dialogo.evaluate("d => d.open")
    assert "LAB-PC-02" in dialogo.inner_text()
    assert not any(m == "DELETE" for m, _ in peticiones)

    page.click("#quitar-cancelar")
    assert not dialogo.evaluate("d => d.open")
    assert not any(m == "DELETE" for m, _ in peticiones)

    page.click(".computer-card[data-id='LAB-PC-02'] .btn-link")
    page.click("#quitar-confirmar")
    page.wait_for_timeout(300)
    assert any(m == "DELETE" and "LAB-PC-02" in ruta for m, ruta in peticiones)


def test_se_puede_cancelar_una_carga_en_curso(navegador, servidor):
    ctx = navegador.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_cookies([{"name": "session", "value": servidor["cookie"], "domain": "127.0.0.1", "path": "/"}])
    page = ctx.new_page()
    pendientes = []

    def responder(route):
        url = route.request.url
        if "/api/upload" in url:
            pendientes.append(route)   # nunca respondemos: la carga se queda en curso
            return
        if "/api/computers" in url:
            return route.fulfill(json={"computers": SEIS_EQUIPOS, "total": 6, "online": 5, "offline": 1})
        if "/api/padron" in url:
            return route.fulfill(json=PADRON)
        return route.continue_()

    page.route("**/api/**", responder)
    page.goto(servidor["url"] + "/")
    page.wait_for_selector(".computer-card")
    ir_a_padron(page)
    elegir_archivo(page)
    page.click("#upload-confirm-btn")
    page.wait_for_selector("#upload-msg.procesando")

    assert page.locator("#upload-abort").is_visible()
    page.click("#upload-abort")
    page.wait_for_timeout(300)

    assert "cancel" in page.locator("#upload-msg").inner_text().lower()
    assert not page.locator("#drop-zone").is_disabled()


# ---------------------------------------------------------------------------
# Ayuda
# ---------------------------------------------------------------------------

def test_hay_una_vista_de_ayuda_que_explica_estados_y_padron(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.click("button.nav-item[data-view='ayuda']")
    page.wait_for_selector("#view-ayuda", state="visible")

    texto = page.locator("#view-ayuda").inner_text().lower()
    for frase in ("libre", "en uso", "sin conexión", "sin información", "padrón", "csv", "quitar del monitor", "restaurar"):
        assert frase in texto, frase
    assert page.locator("#view-ayuda h2").count() >= 4


def test_cada_vista_enlaza_a_su_ayuda(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    for vista, ancla in (("equipos", "ayuda-equipos"), ("padron", "ayuda-padron"), ("stats", "ayuda-estadisticas"), ("logs", "ayuda-bitacora")):
        page.evaluate(f"setView('{vista}')")
        enlace = page.locator(f"#view-{vista} a.ayuda-enlace")
        assert enlace.count() == 1, vista
        enlace.click()
        assert page.locator("#view-ayuda").is_visible()
        assert page.evaluate(f"document.getElementById('{ancla}') !== null")


# ---------------------------------------------------------------------------
# Tema claro
# ---------------------------------------------------------------------------

def luminosidad_fondo(page, selector="body"):
    return page.evaluate(f"""() => {{
        const c = getComputedStyle(document.querySelector('{selector}')).backgroundColor.match(/\\d+/g).map(Number);
        return (c[0] + c[1] + c[2]) / 3;
    }}""")


def test_con_preferencia_del_sistema_clara_el_panel_es_claro(navegador, servidor):
    page, _ = abrir(navegador, servidor, esquema="light")
    assert luminosidad_fondo(page) > 200
    assert luminosidad_fondo(page, ".panel") > 200


def test_por_defecto_sigue_oscuro(navegador, servidor):
    page, _ = abrir(navegador, servidor, esquema="dark")
    assert luminosidad_fondo(page) < 60


def test_el_boton_de_tema_cambia_y_lo_recuerda(navegador, servidor):
    page, _ = abrir(navegador, servidor, esquema="dark")
    boton = page.locator("#theme-toggle")
    assert boton.count() == 1 and boton.get_attribute("aria-label")

    boton.click()
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    assert luminosidad_fondo(page) > 200

    page.reload()
    page.wait_for_selector(".computer-card")
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    assert luminosidad_fondo(page) > 200

    page.locator("#theme-toggle").click()
    assert luminosidad_fondo(page) < 60
    page.evaluate("localStorage.clear()")


@pytest.mark.parametrize("selector", [
    ".panel-title", ".qs-label", ".qs-hint", ".nav-section", ".brand-sub", ".page-header p", ".section-meta",
    ".btn-logout", ".nav-item[aria-current='page'] .nav-label", ".card-meta", ".card-state-text", ".ayuda-enlace",
    ".computer-card[data-id='LAB-PC-02'] .status-badge", ".computer-card[data-id='LAB-PC-01'] .status-badge",
    ".computer-card[data-id='LAB-PC-06'] .status-badge", ".computer-card[data-id='LAB-PC-01'] .card-user-meta",
])
def test_contraste_en_tema_claro(navegador, servidor, selector):
    page, _ = abrir(navegador, servidor, esquema="light")
    ratio = contraste(page, selector)
    assert ratio is not None, selector
    assert ratio >= 4.5, f"{selector}: {ratio:.2f}:1"


def test_contraste_en_tema_claro_en_estadisticas_y_padron(navegador, servidor):
    page, _ = abrir(navegador, servidor, esquema="light")
    page.evaluate("setView('stats')"); page.wait_for_selector("#st-recientes table")
    for sel in (".badge-entrada", ".st-table th", ".st-table td.ts", ".bar-count", "#reporte-ver", ".sm-label"):
        assert contraste(page, sel) >= 4.5, sel
    ir_a_padron(page); elegir_archivo(page)
    for sel in ("#upload-confirm-btn", "#upload-cancel", ".help-text", "#padron-restore"):
        assert contraste(page, sel) >= 4.5, sel


def test_login_en_tema_claro_es_claro_y_legible(navegador, servidor):
    ctx = navegador.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    page = ctx.new_page()
    page.goto(servidor["url"] + "/login")
    assert luminosidad_fondo(page) > 200
    for sel in (".field label", ".login-footer", ".brand-subtitle", ".btn-login", ".login-card h2"):
        assert contraste(page, sel) >= 4.5, sel


def test_el_dialogo_de_quitar_aparece_centrado(navegador, servidor):
    page, _ = abrir(navegador, servidor)
    page.evaluate("document.querySelector('.computer-card[data-id=\\'LAB-PC-02\\'] details').open = true")
    page.click(".computer-card[data-id='LAB-PC-02'] .btn-link")

    caja = page.locator("dialog#dialogo-quitar").bounding_box()
    centro_x = caja["x"] + caja["width"] / 2
    centro_y = caja["y"] + caja["height"] / 2
    assert abs(centro_x - 720) < 40, caja
    assert abs(centro_y - 450) < 60, caja
    page.click("#quitar-cancelar")
