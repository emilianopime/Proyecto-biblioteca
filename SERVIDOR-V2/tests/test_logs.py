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
        cur.execute("INSERT INTO alumnos VALUES (1, 'Perez', 'Juan', 'Derecho');")
        cur.executemany("INSERT INTO bitacora_uso (computer_id, matricula, evento) VALUES (%s, 1, %s);",
                        [(f"PC-{i:02d}", "LOGIN") for i in range(23)])
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["authenticated"] = True
        yield c


def test_logs_reporta_el_total_de_registros(cliente):
    d = cliente.get("/api/logs?page=1").get_json()

    assert d["total"] == 23
    assert d["total_pages"] == 2
    assert len(d["logs"]) == 20
