"""
Prueba de integracion contra un Postgres real.
Se salta si no esta definida TEST_DB_DSN, por ejemplo:
  TEST_DB_DSN="host=localhost port=55432 user=postgres password=test dbname=postgres"
"""
import os

import pandas as pd
import psycopg2
import pytest

from padron import cargar_padron

DSN = os.getenv("TEST_DB_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DB_DSN no definida")


@pytest.fixture
def conn():
    conexion = psycopg2.connect(DSN)
    with conexion.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS alumnos, alumnos_anterior, padron_meta;")
        cur.execute(
            "CREATE TABLE alumnos (cardnumber BIGINT PRIMARY KEY, "
            "surname TEXT, firstname TEXT, sort1 TEXT);"
        )
        cur.execute("INSERT INTO alumnos VALUES (999, 'Viejo', 'Registro', 'Nada');")
    conexion.commit()
    yield conexion
    conexion.close()


def filas(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT cardnumber, surname, firstname, sort1 FROM alumnos ORDER BY cardnumber;")
        return cur.fetchall()


def test_reemplaza_el_padron_completo(conn):
    df = pd.DataFrame([
        {"cardnumber": 1, "surname": "Perez", "firstname": "Juan", "sort1": "Derecho"},
        {"cardnumber": 2, "surname": "Lopez, Ruiz", "firstname": "Ana \"La\" Maria", "sort1": "Sin Profesion"},
    ])

    total = cargar_padron(df, conn)

    assert total == 2
    assert filas(conn) == [
        (1, "Perez", "Juan", "Derecho"),
        (2, "Lopez, Ruiz", 'Ana "La" Maria', "Sin Profesion"),
    ]


def test_si_la_carga_falla_el_padron_anterior_sigue_intacto(conn):
    df = pd.DataFrame([
        {"cardnumber": 1, "surname": "Perez", "firstname": "Juan", "sort1": "Derecho"},
        {"cardnumber": 1, "surname": "Dup", "firstname": "Dup", "sort1": "Dup"},
    ])

    with pytest.raises(psycopg2.Error):
        cargar_padron(df, conn)

    assert filas(conn) == [(999, "Viejo", "Registro", "Nada")]


# ---------------------------------------------------------------------------
# Padron anterior y restauracion
# ---------------------------------------------------------------------------

from padron import estado_padron, restaurar_padron, SinPadronAnterior  # noqa: E402

PRIMERO = pd.DataFrame([{"cardnumber": 1, "surname": "Perez", "firstname": "Juan", "sort1": "Derecho"}])
SEGUNDO = pd.DataFrame([{"cardnumber": 2, "surname": "Lopez", "firstname": "Ana", "sort1": "Medicina"},
                        {"cardnumber": 3, "surname": "Ruiz", "firstname": "Luis", "sort1": "Medicina"}])


def test_cargar_guarda_el_padron_anterior_y_su_procedencia(conn):
    cargar_padron(PRIMERO, conn, archivo="padron_2026A.csv")
    cargar_padron(SEGUNDO, conn, archivo="padron_2026B.csv")

    e = estado_padron(conn)
    assert e["total"] == 2 and e["archivo"] == "padron_2026B.csv" and e["cargado_en"]
    assert e["anterior"]["total"] == 1 and e["anterior"]["archivo"] == "padron_2026A.csv"
    assert filas(conn) == [(2, "Lopez", "Ana", "Medicina"), (3, "Ruiz", "Luis", "Medicina")]


def test_restaurar_vuelve_al_padron_anterior_y_conserva_el_reemplazado(conn):
    cargar_padron(PRIMERO, conn, archivo="padron_2026A.csv")
    cargar_padron(SEGUNDO, conn, archivo="padron_2026B.csv")

    e = restaurar_padron(conn)

    assert filas(conn) == [(1, "Perez", "Juan", "Derecho")]
    assert e["total"] == 1 and e["archivo"] == "padron_2026A.csv"
    assert e["anterior"]["total"] == 2 and e["anterior"]["archivo"] == "padron_2026B.csv"


def test_sin_padron_anterior_no_se_puede_restaurar(conn):
    assert estado_padron(conn)["anterior"] is None
    with pytest.raises(SinPadronAnterior):
        restaurar_padron(conn)


def test_estado_del_padron_antes_de_cualquier_carga_cuenta_lo_que_hay(conn):
    e = estado_padron(conn)
    assert e["total"] == 1          # la fila 999 del fixture
    assert e["archivo"] is None and e["anterior"] is None
