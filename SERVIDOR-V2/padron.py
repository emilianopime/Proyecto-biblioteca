"""
Lectura y validacion del padron de alumnos a partir del CSV que exporta
el sistema de la biblioteca.

El archivo trae muchas columnas y sus encabezados han cambiado con el
tiempo. Aqui se reconocen las columnas por alias, se validan las
obligatorias y se devuelve solo lo que la aplicacion usa: matricula,
apellido, nombre y carrera.
"""

import csv
import io
import os
import re
import unicodedata

import pandas as pd


class PadronInvalido(Exception):
    """El archivo no tiene la forma que espera el padron."""


COLUMNAS_FINALES = ["cardnumber", "surname", "firstname", "sort1"]
OBLIGATORIAS = {"cardnumber": "matricula", "surname": "apellido"}
SIN_PROFESION = "Sin Profesion"

# utf-8-sig quita el BOM si viene; latin-1 nunca falla, por eso va al final.
ENCODINGS = ["utf-8-sig", "latin-1"]
SEPARADORES = ",;\t|"

# Alias aceptados para cada campo, ya normalizados (ver normalizar_encabezado).
ALIAS = {
    "cardnumber": ["cardnumber", "carnet", "matricula"],
    "surname":    ["surname", "apellidos", "apellido"],
    "firstname":  ["firstname", "nombres", "nombre"],
    "sort1":      ["sort1", "carrera", "profesion"],
}


def normalizar_encabezado(texto):
    """'Apellido(s)' -> 'apellidos', 'Correo Electrónico' -> 'correo electronico'."""
    sin_acentos = unicodedata.normalize("NFKD", str(texto))
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    solo_letras = re.sub(r"[^a-z0-9 ]", "", sin_acentos.lower())
    return re.sub(r"\s+", " ", solo_letras).strip()


def mapear_columnas(columnas_archivo):
    """Devuelve {campo_final: nombre_en_archivo} para las columnas reconocidas."""
    normalizadas = {normalizar_encabezado(c): c for c in columnas_archivo}
    mapa = {}
    for campo, alias in ALIAS.items():
        for a in alias:
            if a in normalizadas:
                mapa[campo] = normalizadas[a]
                break
    return mapa


def decodificar(contenido):
    """Prueba cada encoding en orden y devuelve el texto del archivo."""
    for enc in ENCODINGS:
        try:
            return contenido.decode(enc)
        except UnicodeDecodeError:
            continue
    raise AssertionError("latin-1 acepta cualquier byte")  # pragma: no cover


def detectar_separador(texto):
    """Adivina el separador a partir de la primera linea; coma si no puede."""
    primera_linea = texto.split("\n", 1)[0]
    try:
        return csv.Sniffer().sniff(primera_linea, delimiters=SEPARADORES).delimiter
    except csv.Error:
        return ","


def validar_obligatorias(mapa, columnas_archivo):
    faltantes = [nombre for campo, nombre in OBLIGATORIAS.items() if campo not in mapa]
    if faltantes:
        raise PadronInvalido(
            f"No encontre la columna de {' ni de '.join(faltantes)} en el archivo. "
            f"Columnas que trae: {', '.join(str(c) for c in columnas_archivo)}"
        )


def leer_padron(archivo):
    """
    Lee el CSV del padron y devuelve un DataFrame con COLUMNAS_FINALES.

    Lanza PadronInvalido si el archivo esta vacio, le falta una columna
    obligatoria o no queda ninguna fila con matricula valida.
    """
    texto = decodificar(archivo.read())
    if not texto.strip():
        raise PadronInvalido("El archivo esta vacio")

    df = pd.read_csv(io.StringIO(texto), sep=detectar_separador(texto), dtype=str)
    mapa = mapear_columnas(df.columns)
    validar_obligatorias(mapa, df.columns)
    df = df.rename(columns={v: k for k, v in mapa.items()})

    df = limpiar_matriculas(df)
    df = completar_nombre(df)
    df = completar_carrera(df)
    for campo in ("surname", "firstname", "sort1"):
        df[campo] = df[campo].str.strip().str.title()

    return df[COLUMNAS_FINALES].reset_index(drop=True)


def limpiar_matriculas(df):
    """Descarta filas sin matricula numerica y deja una fila por matricula."""
    df["cardnumber"] = pd.to_numeric(df["cardnumber"], errors="coerce")
    df = df.dropna(subset=["cardnumber"])
    if df.empty:
        raise PadronInvalido("El archivo no trae ningun alumno con matricula valida")
    df["cardnumber"] = df["cardnumber"].astype("int64")
    return df.drop_duplicates(subset=["cardnumber"], keep="first")


def completar_nombre(df):
    """
    Si el archivo no trae columna de nombre, intenta sacarlo del apellido
    cuando viene como "Apellido, Nombre". Si no hay coma, queda vacio.
    """
    df["surname"] = df["surname"].fillna("")
    if "firstname" in df.columns:
        df["firstname"] = df["firstname"].fillna("")
        return df
    partes = df["surname"].str.split(",", n=1, expand=True).reindex(columns=[0, 1])
    df["surname"] = partes[0].fillna("")
    df["firstname"] = partes[1].fillna("")
    return df


def completar_carrera(df):
    if "sort1" not in df.columns:
        df["sort1"] = ""
    df["sort1"] = df["sort1"].fillna("").str.strip()
    df.loc[df["sort1"] == "", "sort1"] = SIN_PROFESION
    return df


def agregar_invitado(df):
    """
    Agrega la fila del usuario invitado, configurable por entorno.
    Si INVITADO_CARDNUMBER esta vacio no se agrega nadie.
    """
    matricula = os.getenv("INVITADO_CARDNUMBER", "10203").strip()
    if not matricula:
        return df
    if not matricula.isdigit():
        raise PadronInvalido(
            f"INVITADO_CARDNUMBER debe ser un numero, no '{matricula}'"
        )
    invitado = pd.DataFrame([{
        "cardnumber": int(matricula),
        "surname":    os.getenv("INVITADO_APELLIDO", "Invitado"),
        "firstname":  os.getenv("INVITADO_NOMBRE", "Especial"),
        "sort1":      os.getenv("INVITADO_CARRERA", "Invitado"),
    }])
    return pd.concat([df, invitado], ignore_index=True)


def cargar_padron(df, conn):
    """
    Reemplaza el contenido de la tabla alumnos con el DataFrame dado.
    TRUNCATE y COPY van en la misma transaccion: si el COPY falla, el
    padron anterior se conserva. Devuelve cuantas filas se cargaron.
    """
    buffer = io.StringIO()
    df[COLUMNAS_FINALES].to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE alumnos;")
            cur.copy_expert(
                "COPY alumnos (cardnumber, surname, firstname, sort1) "
                "FROM STDIN WITH (FORMAT CSV)",
                buffer,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(df)
