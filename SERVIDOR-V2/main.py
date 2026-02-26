"""
main.py — Servidor principal del sistema de monitoreo de laboratorio UACH

Responsabilidades:
  - Inicializar la aplicacion Flask y registrar el modulo de autenticacion.
  - Exponer rutas del dashboard (protegidas con login_required).
  - Exponer rutas de la API para los nodos kiosko (sin autenticacion de sesion,
    ya que son llamadas programaticamente desde las PCs del laboratorio).
  - Mantener en memoria el estado en tiempo real de los equipos conectados.
  - Detectar cuando una PC se desconecta con sesion activa y registrar el logout.

Rutas del dashboard (requieren sesion activa):
  GET  /                         — Panel principal.
  POST /api/upload               — Carga el padron de alumnos desde un CSV.
  GET  /api/computers            — Lista el estado de todos los equipos.
  DEL  /api/computer/<id>        — Elimina un equipo del monitor.
  GET  /api/stats                — Devuelve estadisticas de uso del laboratorio.

Rutas de la API kiosko (abiertas, llamadas desde los nodos):
  POST /api/heartbeat            — Registra que un equipo sigue encendido.
  POST /api/verify_student       — Verifica una matricula y registra el login.

Rutas de autenticacion (manejadas por auth.py):
  GET/POST /login                — Formulario de inicio de sesion.
  GET      /logout               — Cierre de sesion.
"""

import os
import io
import threading
import time
from datetime import datetime

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, session

from auth import auth_bp, login_required

# ---------------------------------------------------------------------------
# Configuracion inicial
# ---------------------------------------------------------------------------

# Carga las variables definidas en el archivo .env
load_dotenv()

app = Flask(__name__)

# La clave secreta firma las cookies de sesion.
# Si no existe en .env, usa un valor de desarrollo (inseguro en produccion).
app.secret_key = os.getenv("SECRET_KEY", "dev-key-insegura-cambiar-en-produccion")

# Registrar el Blueprint de autenticacion (rutas /login y /logout)
app.register_blueprint(auth_bp)

# ---------------------------------------------------------------------------
# Configuracion de la base de datos
# Los valores se leen desde .env para no exponer credenciales en el codigo.
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "basedatosuach"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "port":     os.getenv("DB_PORT", "5432"),
}

# ---------------------------------------------------------------------------
# Estado en memoria de los equipos conectados
# ---------------------------------------------------------------------------

# Diccionario {computer_id: objeto Computer} con el estado de cada nodo.
computers = {}

# Segundos maximos sin recibir heartbeat antes de marcar un equipo como offline.
TIMEOUT = 15


# ---------------------------------------------------------------------------
# Clase Computer
# ---------------------------------------------------------------------------

class Computer:
    """
    Representa un equipo del laboratorio conectado al servidor.

    Atributos:
        id (str)             : Identificador unico del equipo (hostname).
        name (str)           : Nombre legible del equipo (ej. Lab_PC01).
        ip (str)             : Direccion IP en la red local.
        info (dict)          : Informacion adicional enviada por el kiosko
                               (locked, current_user, cardnumber, etc.).
        last_heartbeat (datetime): Timestamp del ultimo heartbeat recibido.
        status (str)         : 'online' u 'offline'.
    """

    def __init__(self, computer_id, name, ip, info):
        self.id             = computer_id
        self.name           = name
        self.ip             = ip
        self.info           = info
        self.last_heartbeat = datetime.now()
        self.status         = "online"

    def update_heartbeat(self, info=None):
        """Actualiza el timestamp del ultimo heartbeat y el estado del equipo."""
        self.last_heartbeat = datetime.now()
        self.status         = "online"
        if info:
            self.info.update(info)

    def check_status(self):
        """
        Compara el tiempo transcurrido desde el ultimo heartbeat con TIMEOUT.
        Actualiza y retorna el estado actual ('online' u 'offline').
        """
        segundos_desde_ultimo = (datetime.now() - self.last_heartbeat).total_seconds()
        self.status = "online" if segundos_desde_ultimo <= TIMEOUT else "offline"
        return self.status

    def to_dict(self):
        """Serializa el equipo a un diccionario para enviar como JSON."""
        return {
            "id":             self.id,
            "name":           self.name,
            "ip":             self.ip,
            "status":         self.status,
            "last_heartbeat": self.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S"),
            "info":           self.info,
        }


# ---------------------------------------------------------------------------
# Hilo de monitoreo de equipos
# ---------------------------------------------------------------------------

def check_computers_status():
    """
    Hilo en segundo plano que revisa el estado de cada equipo cada 5 segundos.

    Si detecta que un equipo paso de 'online' a 'offline' mientras tenia
    una sesion de alumno activa, registra un LOGOUT_APAGADO en la base de datos
    para mantener la integridad de la bitacora.
    """
    while True:
        for computer_id in list(computers.keys()):
            comp            = computers[computer_id]
            estado_anterior = comp.status
            estado_actual   = comp.check_status()

            # Detectar transicion online -> offline con sesion activa
            if estado_anterior == "online" and estado_actual == "offline":
                usuario   = comp.info.get("current_user")
                matricula = comp.info.get("cardnumber")

                if usuario and usuario != "BLOQUEADA" and matricula:
                    try:
                        conn   = psycopg2.connect(**DB_CONFIG)
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO bitacora_uso (computer_id, matricula, evento) "
                            "VALUES (%s, %s, 'LOGOUT_APAGADO')",
                            (computer_id, matricula),
                        )
                        conn.commit()
                        cursor.close()
                        conn.close()
                        print(f"Log automatico: logout registrado para {computer_id} (desconectado con sesion activa)")

                        # Limpiar el estado para no repetir el registro en el proximo ciclo
                        comp.info["current_user"] = "BLOQUEADA"
                        comp.info["locked"]       = True
                        comp.info["cardnumber"]   = None

                    except Exception as e:
                        print(f"Error registrando logout automatico: {e}")

        time.sleep(5)


# Iniciar el hilo de monitoreo como daemon para que se detenga al cerrar el servidor
threading.Thread(target=check_computers_status, daemon=True).start()


# ---------------------------------------------------------------------------
# Logica de negocio: procesamiento del CSV de alumnos
# ---------------------------------------------------------------------------

def procesar_csv(archivo, tabla):
    """
    Lee el CSV del padron de alumnos, lo limpia con pandas y lo carga
    en la tabla indicada de PostgreSQL usando COPY (mas eficiente que INSERT).

    El archivo nunca se guarda en disco: se procesa completamente en memoria.

    Columnas esperadas en el CSV: cardnumber, surname, firstname, sort1.
    """
    df = pd.read_csv(archivo, encoding="latin-1", dtype=str)

    # Convertir matricula a numero entero, descartar filas invalidas
    df["cardnumber"] = pd.to_numeric(df["cardnumber"], errors="coerce").fillna(0).astype("int64")
    df = df.drop_duplicates(subset=["cardnumber"], keep="first")

    # Normalizar el campo de carrera/profesion
    df["sort1"] = df["sort1"].fillna("Sin Profesion").astype(str).str.strip()

    # El campo 'surname' a veces viene como "Apellido, Nombre" en un solo campo
    df["surname"] = df["surname"].astype(str)
    mask = df["surname"].str.contains(",", na=False)
    df.loc[mask,  ["surname", "firstname"]] = df.loc[mask,  "surname"].str.split(",", n=1, expand=True).values
    df.loc[~mask, ["surname", "firstname"]] = df.loc[~mask, "surname"].str.rsplit(" ", n=1, expand=True).values

    df = df[["cardnumber", "surname", "firstname", "sort1"]]

    conn   = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Crear la tabla si no existe y limpiarla antes de cargar
    cursor.execute(
        f'CREATE TABLE IF NOT EXISTS "{tabla}" '
        f'(cardnumber BIGINT PRIMARY KEY, surname TEXT, firstname TEXT, sort1 TEXT);'
    )
    cursor.execute(f'TRUNCATE TABLE "{tabla}";')

    # Cargar con COPY desde un buffer en memoria (mucho mas rapido que INSERT fila a fila)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    cursor.copy_expert(f'COPY "{tabla}" FROM STDIN WITH (FORMAT CSV)', buffer)

    conn.commit()
    cursor.close()
    conn.close()


# ===========================================================================
# RUTAS DEL DASHBOARD (protegidas — requieren sesion activa)
# ===========================================================================

@app.route("/")
@login_required
def index():
    """Renderiza el panel principal del dashboard."""
    return render_template("dashboard.html", username=session.get("username"))


@app.route("/api/upload", methods=["POST"])
@login_required
def upload():
    """
    Recibe un archivo CSV y lo carga en la tabla de alumnos.
    El archivo se procesa en memoria; nunca se escribe en disco.
    """
    file       = request.files.get("file")
    table_name = request.form.get("table_name", "alumnos")
    try:
        procesar_csv(file, table_name)
        return jsonify({"message": f"Exito: datos cargados en '{table_name}'"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/computers")
@login_required
def get_computers():
    """
    Devuelve la lista de todos los equipos registrados con su estado actual.
    Incluye conteos de equipos online y offline para las tarjetas del dashboard.
    """
    c_list = [c.to_dict() for c in computers.values()]
    return jsonify({
        "computers": c_list,
        "total":     len(c_list),
        "online":    sum(1 for c in c_list if c["status"] == "online"),
        "offline":   sum(1 for c in c_list if c["status"] == "offline"),
    })


@app.route("/api/computer/<computer_id>", methods=["DELETE"])
@login_required
def delete_computer(computer_id):
    """
    Elimina un equipo del monitor en memoria.
    Si el equipo sigue encendido, volvera a aparecer en el proximo heartbeat.
    """
    if computer_id in computers:
        del computers[computer_id]
        return jsonify({"status": "success"})
    return jsonify({"error": "No encontrado"}), 404


@app.route("/api/stats")
@login_required
def get_stats():
    """
    Devuelve estadisticas de uso del laboratorio para la vista de estadisticas.

    Datos incluidos:
      - total_alumnos    : Total de alumnos en el padron.
      - logins_hoy       : Accesos registrados el dia de hoy.
      - logins_semana    : Accesos en la semana actual.
      - logins_mes       : Accesos en el mes actual.
      - top_pcs          : Top 10 equipos con mas usos.
      - top_carreras_uso : Top 10 carreras cuyos alumnos mas usan el laboratorio.
      - dist_carreras    : Distribucion del padron completo por carrera (top 10).
      - recientes        : Ultimas 15 entradas de la bitacora con nombre del alumno.
    """
    try:
        conn   = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM alumnos")
        total_alumnos = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM bitacora_uso "
            "WHERE evento = 'LOGIN' AND timestamp::date = CURRENT_DATE"
        )
        logins_hoy = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM bitacora_uso "
            "WHERE evento = 'LOGIN' AND timestamp >= date_trunc('week', NOW())"
        )
        logins_semana = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM bitacora_uso "
            "WHERE evento = 'LOGIN' AND timestamp >= date_trunc('month', NOW())"
        )
        logins_mes = cursor.fetchone()[0]

        cursor.execute("""
            SELECT a.sort1, COUNT(*) AS total
            FROM bitacora_uso b
            JOIN alumnos a ON b.matricula = a.cardnumber
            WHERE b.evento = 'LOGIN'
            GROUP BY a.sort1
            ORDER BY total DESC
            LIMIT 10
        """)
        top_carreras_uso = [{"carrera": r[0], "total": r[1]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT computer_id, COUNT(*) AS total
            FROM bitacora_uso
            WHERE evento = 'LOGIN'
            GROUP BY computer_id
            ORDER BY total DESC
            LIMIT 10
        """)
        top_pcs = [{"pc": r[0], "total": r[1]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT sort1, COUNT(*) AS total
            FROM alumnos
            GROUP BY sort1
            ORDER BY total DESC
            LIMIT 10
        """)
        dist_carreras = [{"carrera": r[0], "total": r[1]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT b.computer_id, a.firstname, a.surname, b.matricula, b.evento, b.timestamp
            FROM bitacora_uso b
            LEFT JOIN alumnos a ON b.matricula = a.cardnumber
            ORDER BY b.timestamp DESC
            LIMIT 15
        """)
        recientes = []
        for r in cursor.fetchall():
            recientes.append({
                "pc":        r[0],
                "nombre":    f"{r[1] or ''} {r[2] or ''}".strip() or "Desconocido",
                "matricula": r[3],
                "evento":    r[4],
                "timestamp": r[5].strftime("%d/%m/%Y %H:%M") if r[5] else "",
            })

        cursor.close()
        conn.close()

        return jsonify({
            "total_alumnos":    total_alumnos,
            "logins_hoy":       logins_hoy,
            "logins_semana":    logins_semana,
            "logins_mes":       logins_mes,
            "top_carreras_uso": top_carreras_uso,
            "top_pcs":          top_pcs,
            "dist_carreras":    dist_carreras,
            "recientes":        recientes,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===========================================================================
# RUTAS DE LA API KIOSKO (abiertas — llamadas desde los nodos del laboratorio)
# ===========================================================================

@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    """
    Recibe el latido periodico de un equipo del laboratorio.

    El kiosko envia su ID, nombre, IP e informacion del estado actual
    (bloqueado/desbloqueado, usuario activo). Si el equipo no estaba
    registrado, se agrega al diccionario. Si ya existia, se actualiza
    su heartbeat y su informacion.

    Esta ruta no requiere autenticacion porque la llaman los nodos
    directamente, no un navegador con sesion.
    """
    data  = request.json
    c_id  = data.get("id")

    if c_id not in computers:
        computers[c_id] = Computer(
            c_id,
            data.get("name"),
            data.get("ip", request.remote_addr),
            data.get("info", {}),
        )
    else:
        computers[c_id].update_heartbeat(data.get("info"))

    return jsonify({"status": "success"})


@app.route("/api/verify_student", methods=["POST"])
def verify_student():
    """
    Verifica si una matricula existe en el padron de alumnos.

    Si la matricula es valida, registra un evento LOGIN en la bitacora
    y devuelve el nombre del alumno para el saludo en el kiosko.
    Si no existe, devuelve un error 404.

    Esta ruta no requiere autenticacion porque la llaman los nodos
    directamente desde la app kiosko de Tkinter.
    """
    data        = request.json
    matricula   = data.get("cardnumber")
    computer_id = data.get("computer_id", "Desconocida")
    tabla       = "alumnos"

    if not matricula:
        return jsonify({"error": "Matricula requerida"}), 400

    try:
        conn   = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute(
            f'SELECT firstname, surname FROM "{tabla}" WHERE cardnumber = %s;',
            (matricula,),
        )
        alumno = cursor.fetchone()

        if alumno:
            try:
                cursor.execute(
                    "INSERT INTO bitacora_uso (computer_id, matricula, evento) "
                    "VALUES (%s, %s, 'LOGIN');",
                    (computer_id, matricula),
                )
                conn.commit()
            except Exception as e_log:
                print(f"Error guardando log de login: {e_log}")
                conn.rollback()

        cursor.close()
        conn.close()

        if alumno:
            return jsonify({
                "status":  "success",
                "student": {"name": f"{alumno[0]} {alumno[1]}"},
            }), 200
        else:
            return jsonify({"status": "error", "message": "Matricula no registrada"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
