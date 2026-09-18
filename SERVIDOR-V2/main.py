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
import csv
import os
import io
import threading
import time
from datetime import datetime, timedelta
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, session, Response
from auth import auth_bp, login_required
load_dotenv()
import logging

# ---------------------------------------------------------------------------
# Silenciar logs molestos de polling en la consola
# ---------------------------------------------------------------------------
class NoPollingFilter(logging.Filter):
    def filter(self, record):
        # Ignorar las peticiones que contengan estas rutas en su mensaje
        mensaje = record.getMessage()
        if '/api/computers' in mensaje or '/api/heartbeat' in mensaje:
            return False
        return True

# Aplicamos el filtro al logger interno de Flask (Werkzeug)
logging.getLogger("werkzeug").addFilter(NoPollingFilter())


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
    "host":     os.getenv("DB_HOST"),
    "database": os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port":     os.getenv("DB_PORT"),
}

computers = {}

TIMEOUT = 15


# ---------------------------------------------------------------------------
# Clase Computer
# ---------------------------------------------------------------------------

class Computer:

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
# ---------------------------------------------------------------------------
# Persistencia de computadoras en PostgreSQL
# ---------------------------------------------------------------------------
def crear_tabla_computadoras():
    """Crea la tabla computadoras en PostgreSQL si no existe."""
    try:
        conn   = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS computadoras (
                id             TEXT PRIMARY KEY,
                name           TEXT,
                ip             TEXT,
                last_heartbeat TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Advertencia: no se pudo crear la tabla computadoras: {e}")



def cargar_computadoras_conocidas():
    """
    Carga las computadoras conocidas desde la DB al iniciar.
    Fuerza el estado a OFFLINE ignorando la hora de la DB para evitar
    falsos positivos por diferencias de zona horaria (UTC vs Local).
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, ip FROM computadoras")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        for row in rows:
            c_id, name, ip = row

            # Inicializamos con info vacía
            comp = Computer(c_id, name, ip, {})

            # TRUCO: Le restamos 5 minutos a la hora actual de Python.
            # Así, el hilo de monitoreo verá que pasó el TIMEOUT de 15s e iniciará OFFLINE.
            comp.last_heartbeat = datetime.now() - timedelta(minutes=5)
            comp.status = "offline"

            computers[c_id] = comp

        if rows:
            print(f"Computadoras cargadas desde DB (modo offline): {len(rows)}")
    except Exception as e:
        print(f"Advertencia: no se pudo cargar computadoras desde DB: {e}")

# Iniciar el hilo de monitoreo como daemon para que se detenga al cerrar el servidor
crear_tabla_computadoras()
cargar_computadoras_conocidas()
threading.Thread(target=check_computers_status, daemon=True).start()

# ---------------------------------------------------------------------------
# Logica de negocio: procesamiento del CSV de alumnos
# ---------------------------------------------------------------------------

def procesar_csv(archivo, tabla):
    df = pd.read_csv(archivo, encoding="latin-1", dtype=str)

    # Convertir matricula a numero entero, descartar filas invalidas
    df["cardnumber"] = pd.to_numeric(df["cardnumber"], errors="coerce").fillna(0).astype("int64")
    df = df.drop_duplicates(subset=["cardnumber"], keep="first")

    # El campo 'surname' a veces viene como "Apellido, Nombre" en un solo campo
    df["surname"] = df["surname"].astype(str)
    mask = df["surname"].str.contains(",", na=False)

    # Manejo de separaciones por coma o espacio
    df.loc[mask, ["surname", "firstname"]] = df.loc[mask, "surname"].str.split(",", n=1, expand=True).values
    df.loc[~mask, ["surname", "firstname"]] = df.loc[~mask, "surname"].str.rsplit(" ", n=1, expand=True).values

    # Normalizar capitalización: "GARCIA LOPEZ" → "Garcia Lopez"
    df["surname"] = df["surname"].astype(str).str.strip().str.title()
    df["firstname"] = df["firstname"].astype(str).str.strip().str.title()
    df["sort1"] = df["sort1"].fillna("Sin Profesion").astype(str).str.strip().str.title()
    # Seleccionar las columnas finales
    df = df[["cardnumber", "surname", "firstname", "sort1"]]
    datos_invitado = pd.DataFrame([{
        "cardnumber": 10203,
        "surname": "Invitado",  # Puedes personalizar el apellido
        "firstname": "Especial",  # Puedes personalizar el nombre
        "sort1": "Invitado"  # O usar "Sin Profesion"
    }])
    df = pd.concat([df, datos_invitado], ignore_index=True)
# -------------------------------------------------------------------
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    # Crear la tabla si no existe y limpiarla antes de cargar
    cursor.execute(
        f'CREATE TABLE IF NOT EXISTS "{tabla}" '
        f'(cardnumber BIGINT PRIMARY KEY, surname TEXT, firstname TEXT, sort1 TEXT);'
    )
    cursor.execute(f'TRUNCATE TABLE "{tabla}";')

    # Cargar con COPY desde un buffer en memoria
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
    if computer_id in computers:
        del computers[computer_id]
        try:
            conn   = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM computadoras WHERE id = %s", (computer_id,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Advertencia: no se pudo eliminar computadora de DB: {e}")
        return jsonify({"status": "success"})
    return jsonify({"error": "No encontrado"}), 404

@app.route("/api/stats")
@login_required
def get_stats():
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

        cursor.execute(
            "SELECT COUNT(*) FROM bitacora_uso "
            "WHERE evento = 'LOGIN' AND timestamp >= NOW() - INTERVAL '6 months'"
        )
        logins_semestre = cursor.fetchone()[0]

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

        # Empareja cada LOGIN con su siguiente LOGOUT/LOGOUT_APAGADO en la misma
        # computadora para el mismo alumno, usando LATERAL para eficiencia.
        # Si no existe cierre de sesión, hora_salida queda NULL (sesión activa).
        # Actividad reciente como un log de eventos real
        # MODIFICADO: Actividad reciente como un log de eventos real
        # y corrección de zona horaria a Chihuahua
        cursor.execute("""
                    SELECT
                        b.computer_id,
                        b.matricula,
                        a.firstname,
                        a.surname,
                        a.sort1,
                        b.timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua' AS hora,
                        b.evento
                    FROM bitacora_uso b
                    LEFT JOIN alumnos a ON b.matricula = a.cardnumber
                    ORDER BY b.timestamp DESC
                    LIMIT 15
                """)

        recientes = []
        for r in cursor.fetchall():
            recientes.append({
                "pc": r[0],
                "matricula": r[1],
                "nombre": f"{r[2] or ''} {r[3] or ''}".strip() or "Desconocido",
                "carrera": r[4] or "—",
                "hora": r[5].strftime("%d/%m/%Y %H:%M") if r[5] else "",
                "evento": r[6]
            })

        cursor.close()
        conn.close()

        return jsonify({
            "total_alumnos": total_alumnos,
            "logins_hoy": logins_hoy,
            "logins_semana": logins_semana,
            "logins_mes": logins_mes,
            "logins_semestre": logins_semestre,  # <-- Asegúrate de tener la consulta de esto más arriba
            "top_carreras_uso": top_carreras_uso,
            "top_pcs": top_pcs,
            "dist_carreras": dist_carreras,
            "recientes": recientes,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logs")
@login_required
def get_logs():
    """Devuelve el historial completo paginado (20 por página)"""
    page  = int(request.args.get("page", 1))
    limit = 20
    offset = (page - 1) * limit

    try:
        conn   = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # 1. Obtener el total de páginas
        cursor.execute("SELECT COUNT(*) FROM bitacora_uso")
        total_records = cursor.fetchone()[0]
        total_pages   = (total_records + limit - 1) // limit

        # 2. Obtener los 20 registros de esta página específica
        cursor.execute("""
            SELECT
                b.computer_id,
                b.matricula,
                a.firstname,
                a.surname,
                a.sort1,
                b.timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua' AS hora,
                b.evento
            FROM bitacora_uso b
            LEFT JOIN alumnos a ON b.matricula = a.cardnumber
            ORDER BY b.timestamp DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        logs = []
        for r in cursor.fetchall():
            logs.append({
                "pc":        r[0],
                "matricula": r[1],
                "nombre":    f"{r[2] or ''} {r[3] or ''}".strip() or "Desconocido",
                "carrera":   r[4] or "—",
                "hora":      r[5].strftime("%d/%m/%Y %H:%M:%S") if r[5] else "",
                "evento":    r[6]
            })

        cursor.close()
        conn.close()

        return jsonify({
            "logs":         logs,
            "current_page": page,
            "total_pages":  total_pages if total_pages > 0 else 1
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/logs/export', methods=['GET'])
@login_required
def export_logs_csv():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Consulta corregida: usando a.sort1 y la zona horaria correcta de Chihuahua
        query = """
            SELECT 
                b.computer_id, 
                b.matricula, 
                COALESCE(a.firstname || ' ' || a.surname, 'Desconocido') AS nombre,
                COALESCE(a.sort1, 'N/A') AS carrera,
                TO_CHAR(b.timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Chihuahua', 'YYYY-MM-DD HH24:MI:SS') AS hora,
                b.evento
            FROM bitacora_uso b
            LEFT JOIN alumnos a ON b.matricula = a.cardnumber
            ORDER BY b.timestamp DESC;
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        # Generar el archivo CSV en memoria
        si = io.StringIO()
        cw = csv.writer(si)

        # Escribir los encabezados
        cw.writerow(['PC', 'Matricula', 'Nombre', 'Carrera', 'Hora', 'Evento'])

        # Escribir los datos
        cw.writerows(rows)

        output = si.getvalue()

        # Retornar como un archivo descargable
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=bitacora_laboratorio.csv"}
        )

    except Exception as e:
        print(f"Error fatal al exportar CSV: {e}")  # Para que lo veas en la terminal
        return jsonify({"error": str(e)}), 500

# ===========================================================================
# RUTAS DE LA API KIOSKO (abiertas — llamadas desde los nodos del laboratorio)
# ===========================================================================

@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
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

    # Persistir en DB: Usamos la hora exacta de Python (computers[c_id].last_heartbeat)
    # en lugar de dejar que Postgres invente la suya con NOW()
    try:
        conn   = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO computadoras (id, name, ip, last_heartbeat)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
                SET name           = EXCLUDED.name,
                    ip             = EXCLUDED.ip,
                    last_heartbeat = EXCLUDED.last_heartbeat
        """, (c_id, computers[c_id].name, computers[c_id].ip, computers[c_id].last_heartbeat))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Advertencia: no se pudo persistir heartbeat en DB: {e}")

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
    app.run(host="0.0.0.0", port=8000, debug=False)