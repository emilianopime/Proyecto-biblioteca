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
        cur.execute("DROP TABLE IF EXISTS alumnos;")
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
