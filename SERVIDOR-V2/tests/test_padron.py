import io

import pytest

from padron import PadronInvalido, agregar_invitado, leer_padron


ENCABEZADO_NUEVO = (
    'Carnet,Apellido(s),Nombre(s),"Fecha de Inscripción","Fecha de Vencimiento",'
    '"Correo Electrónico",Teléfono,Ciudad,Dirección,Biblioteca,'
    '"Categoría de Usuario",Carrera,Género'
)
FILA_NUEVA = (
    '399229,"CARDENAS MACHADO","AARON ALEJANDRO",2025-08-27,2025-12-19,'
    'a399339@gmail.mx,"614 1 42 25 17",CHIHUAHUA,"EDUARDO MARTINEZ 15311",'
    '"Biblioteca Central",Alumnos,"LICENCIATURA EN ESTOMATOLOGIA",Masculino'
)


def archivo(texto, encoding="utf-8"):
    return io.BytesIO(texto.encode(encoding))


def test_formato_nuevo_en_utf8_saca_solo_las_columnas_de_interes():
    df = leer_padron(archivo(f"{ENCABEZADO_NUEVO}\n{FILA_NUEVA}\n"))

    assert list(df.columns) == ["cardnumber", "surname", "firstname", "sort1"]
    assert df.iloc[0].tolist() == [
        399229,
        "Cardenas Machado",
        "Aaron Alejandro",
        "Licenciatura En Estomatologia",
    ]


def test_acepta_utf8_con_bom():
    df = leer_padron(archivo(f"﻿{ENCABEZADO_NUEVO}\n{FILA_NUEVA}\n"))

    assert df.iloc[0]["cardnumber"] == 399229


def test_acepta_latin1():
    df = leer_padron(archivo(f"{ENCABEZADO_NUEVO}\n{FILA_NUEVA}\n", encoding="latin-1"))

    assert df.iloc[0]["surname"] == "Cardenas Machado"


def test_acepta_punto_y_coma_como_separador():
    encabezado = "Carnet;Apellido(s);Nombre(s);Carrera"
    fila = "399229;CARDENAS MACHADO;AARON ALEJANDRO;LICENCIATURA EN ESTOMATOLOGIA"
    df = leer_padron(archivo(f"{encabezado}\n{fila}\n"))

    assert df.iloc[0].tolist() == [
        399229,
        "Cardenas Machado",
        "Aaron Alejandro",
        "Licenciatura En Estomatologia",
    ]


def test_falta_matricula_da_error_que_dice_que_columnas_traia():
    with pytest.raises(PadronInvalido) as exc:
        leer_padron(archivo("Apellido(s),Nombre(s),Carrera\nPEREZ,JUAN,DERECHO\n"))

    mensaje = str(exc.value)
    assert "matricula" in mensaje
    assert "Apellido(s), Nombre(s), Carrera" in mensaje


def test_falta_apellido_da_error():
    with pytest.raises(PadronInvalido) as exc:
        leer_padron(archivo("Carnet,Nombre(s),Carrera\n1,JUAN,DERECHO\n"))

    assert "apellido" in str(exc.value)


def test_formato_viejo_sigue_funcionando():
    df = leer_padron(archivo("cardnumber,surname,firstname,sort1\n1,PEREZ,JUAN,DERECHO\n"))

    assert df.iloc[0].tolist() == [1, "Perez", "Juan", "Derecho"]


def test_sin_columna_carrera_pone_sin_profesion():
    df = leer_padron(archivo("Carnet,Apellido(s),Nombre(s)\n1,PEREZ,JUAN\n"))

    assert df.iloc[0]["sort1"] == "Sin Profesion"


def test_carrera_vacia_pone_sin_profesion():
    df = leer_padron(archivo("Carnet,Apellido(s),Nombre(s),Carrera\n1,PEREZ,JUAN,\n"))

    assert df.iloc[0]["sort1"] == "Sin Profesion"


def test_sin_columna_nombre_parte_apellido_por_coma():
    df = leer_padron(archivo('cardnumber,surname\n1,"PEREZ LOPEZ, JUAN CARLOS"\n'))

    assert df.iloc[0]["surname"] == "Perez Lopez"
    assert df.iloc[0]["firstname"] == "Juan Carlos"


def test_sin_columna_nombre_y_sin_coma_deja_nombre_vacio():
    df = leer_padron(archivo("cardnumber,surname\n1,PEREZ\n"))

    assert df.iloc[0]["surname"] == "Perez"
    assert df.iloc[0]["firstname"] == ""


def test_descarta_filas_con_matricula_no_numerica():
    df = leer_padron(archivo("Carnet,Apellido(s),Nombre(s)\nabc,PEREZ,JUAN\n,LOPEZ,ANA\n2,RUIZ,LUIS\n"))

    assert df["cardnumber"].tolist() == [2]


def test_matriculas_duplicadas_se_queda_con_la_primera():
    df = leer_padron(archivo("Carnet,Apellido(s),Nombre(s)\n1,PEREZ,JUAN\n1,LOPEZ,ANA\n"))

    assert df["surname"].tolist() == ["Perez"]


def test_archivo_sin_filas_validas_da_error():
    with pytest.raises(PadronInvalido) as exc:
        leer_padron(archivo("Carnet,Apellido(s),Nombre(s)\n"))

    assert "ningun alumno" in str(exc.value)


def test_archivo_vacio_da_error():
    with pytest.raises(PadronInvalido):
        leer_padron(archivo(""))


def test_invitado_por_defecto_se_agrega_al_final(monkeypatch):
    for var in ("INVITADO_CARDNUMBER", "INVITADO_NOMBRE", "INVITADO_APELLIDO", "INVITADO_CARRERA"):
        monkeypatch.delenv(var, raising=False)
    df = leer_padron(archivo("Carnet,Apellido(s),Nombre(s)\n1,PEREZ,JUAN\n"))

    df = agregar_invitado(df)

    assert df.iloc[-1].tolist() == [10203, "Invitado", "Especial", "Invitado"]


def test_invitado_se_configura_por_entorno(monkeypatch):
    monkeypatch.setenv("INVITADO_CARDNUMBER", "77")
    monkeypatch.setenv("INVITADO_NOMBRE", "Visita")
    monkeypatch.setenv("INVITADO_APELLIDO", "Biblioteca")
    monkeypatch.setenv("INVITADO_CARRERA", "Externo")
    df = leer_padron(archivo("Carnet,Apellido(s),Nombre(s)\n1,PEREZ,JUAN\n"))

    df = agregar_invitado(df)

    assert df.iloc[-1].tolist() == [77, "Biblioteca", "Visita", "Externo"]


def test_invitado_vacio_no_agrega_nada(monkeypatch):
    monkeypatch.setenv("INVITADO_CARDNUMBER", "")
    df = leer_padron(archivo("Carnet,Apellido(s),Nombre(s)\n1,PEREZ,JUAN\n"))

    assert len(agregar_invitado(df)) == 1


def test_invitado_no_numerico_da_error(monkeypatch):
    monkeypatch.setenv("INVITADO_CARDNUMBER", "abc")
    df = leer_padron(archivo("Carnet,Apellido(s),Nombre(s)\n1,PEREZ,JUAN\n"))

    with pytest.raises(PadronInvalido) as exc:
        agregar_invitado(df)

    assert "INVITADO_CARDNUMBER" in str(exc.value)
