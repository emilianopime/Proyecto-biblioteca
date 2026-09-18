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


def abrir(navegador, servidor, equipos=SEIS_EQUIPOS, ancho=1440, alto=900, con_sesion=True, upload=None):
    """Abre el dashboard con respuestas de API simuladas y devuelve (page, peticiones)."""
    ctx = navegador.new_context(viewport={"width": ancho, "height": alto}, locale="es-MX")
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
