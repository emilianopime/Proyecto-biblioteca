"""
Prueba del endpoint /api/upload de punta a punta contra un Postgres real.
Se salta si no esta definida TEST_DB_DSN (ver test_cargar_padron.py).
"""
import io
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
        "DB_USER": partes["user"], "DB_PASSWORD": partes["password"],
        "DB_NAME": partes["dbname"], "INVITADO_CARDNUMBER": "",
    })
    import main
    main.app.config["TESTING"] = True
    return main.app


@pytest.fixture
def cliente(app):
    with psycopg2.connect(DSN) as conexion, conexion.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS alumnos;")
        cur.execute(
            "CREATE TABLE alumnos (cardnumber BIGINT PRIMARY KEY, "
            "surname TEXT, firstname TEXT, sort1 TEXT);"
        )
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["authenticated"] = True
        yield c


def subir(cliente, texto):
    datos = {"file": (io.BytesIO(texto.encode("utf-8")), "padron.csv")}
    return cliente.post("/api/upload", data=datos, content_type="multipart/form-data")


def test_csv_con_columnas_nuevas_se_carga_y_reporta_cuantos(cliente):
    r = subir(cliente, "Carnet,Apellido(s),Nombre(s),Carrera\n1,PEREZ,JUAN,DERECHO\n2,LOPEZ,ANA,\n")

    assert r.status_code == 200
    assert "2 alumnos" in r.get_json()["message"]
    with psycopg2.connect(DSN) as conexion, conexion.cursor() as cur:
        cur.execute("SELECT cardnumber, surname, firstname, sort1 FROM alumnos ORDER BY 1;")
        assert cur.fetchall() == [(1, "Perez", "Juan", "Derecho"), (2, "Lopez", "Ana", "Sin Profesion")]


def test_csv_sin_matricula_devuelve_400_con_mensaje_claro(cliente):
    r = subir(cliente, "Apellido(s),Nombre(s)\nPEREZ,JUAN\n")

    assert r.status_code == 400
    assert "matricula" in r.get_json()["error"]


def test_sin_archivo_devuelve_400(cliente):
    r = cliente.post("/api/upload", data={}, content_type="multipart/form-data")

    assert r.status_code == 400
