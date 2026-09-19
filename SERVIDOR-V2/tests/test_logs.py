"""
Prueba de /api/logs contra un Postgres real. Se salta sin TEST_DB_DSN.
"""
import os

import psycopg2
import pytest

DSN = os.getenv("TEST_DB_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DB_DSN no definida")


@pytest.fixture(scope="module")
def app():
    partes = dict(p.split("=", 1) for p in DSN.split())
    os.environ.update({
        "DB_HOST": partes["host"], "DB_PORT": partes["port"],
        "DB_USER": partes["user"], "DB_PASSWORD": partes["password"], "DB_NAME": partes["dbname"],
    })
    import main
    # La app pudo haberse importado antes sin base de datos; fijar la conexion aqui.
    main.DB_CONFIG = {"host": partes["host"], "port": partes["port"], "user": partes["user"],
                      "password": partes["password"], "database": partes["dbname"]}
    main.app.config["TESTING"] = True
    return main.app


@pytest.fixture
def cliente(app):
    with psycopg2.connect(DSN) as conexion, conexion.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS bitacora_uso; DROP TABLE IF EXISTS alumnos;")
        cur.execute("CREATE TABLE alumnos (cardnumber BIGINT PRIMARY KEY, surname TEXT, firstname TEXT, sort1 TEXT);")
        cur.execute("CREATE TABLE bitacora_uso (id SERIAL PRIMARY KEY, computer_id TEXT, matricula BIGINT, evento TEXT, timestamp TIMESTAMP DEFAULT NOW());")
        cur.execute("INSERT INTO alumnos VALUES (1, 'Perez', 'Juan', 'Derecho'), (777, 'Lopez', 'Ana', 'Medicina');")
        cur.executemany("INSERT INTO bitacora_uso (computer_id, matricula, evento) VALUES (%s, 1, %s);",
                        [(f"PC-{i:02d}", "LOGIN") for i in range(23)])
        # Eventos con fecha conocida para filtrar (UTC; Chihuahua es UTC-6)
        cur.executemany("INSERT INTO bitacora_uso (computer_id, matricula, evento, timestamp) VALUES (%s, %s, %s, %s);", [
            ("PC-99", 777, "LOGIN",  "2026-08-10 15:00:00"),
            ("PC-99", 777, "LOGOUT", "2026-08-10 16:00:00"),
            ("PC-98", 777, "LOGIN",  "2026-08-12 15:00:00"),
        ])
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["authenticated"] = True
        yield c


def test_logs_reporta_el_total_de_registros(cliente):
    d = cliente.get("/api/logs?page=1").get_json()

    assert d["total"] == 26
    assert d["total_pages"] == 2
    assert len(d["logs"]) == 20


def test_logs_filtra_por_texto_en_equipo_matricula_o_nombre(cliente):
    assert cliente.get("/api/logs?q=PC-99").get_json()["total"] == 2
    assert cliente.get("/api/logs?q=ana").get_json()["total"] == 3          # nombre, sin distinguir mayusculas
    assert cliente.get("/api/logs?q=lopez").get_json()["total"] == 3
    assert cliente.get("/api/logs?q=777").get_json()["total"] == 3          # matricula exacta
    assert cliente.get("/api/logs?q=77").get_json()["total"] == 0           # no hay coincidencia parcial de matricula


def test_logs_filtra_por_evento_y_por_fechas(cliente):
    assert cliente.get("/api/logs?evento=salida").get_json()["total"] == 1
    assert cliente.get("/api/logs?evento=entrada&q=PC-9").get_json()["total"] == 2
    d = cliente.get("/api/logs?desde=2026-08-11&hasta=2026-08-31").get_json()
    assert d["total"] == 1 and d["logs"][0]["pc"] == "PC-98"


def test_logs_con_fecha_invalida_devuelve_400(cliente):
    r = cliente.get("/api/logs?desde=ayer")
    assert r.status_code == 400


def test_exportar_respeta_los_mismos_filtros(cliente):
    r = cliente.get("/api/logs/export?q=PC-99&evento=entrada")
    lineas = r.get_data(as_text=True).strip().splitlines()
    assert r.status_code == 200
    assert lineas[0].startswith("PC,Matricula")
    assert len(lineas) == 2 and "PC-99" in lineas[1]
    assert "bitacora" in r.headers["Content-Disposition"]
