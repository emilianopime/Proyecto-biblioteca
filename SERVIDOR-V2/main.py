import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from datetime import datetime
import threading
import time
import pandas as pd
import psycopg2
import io

# Importamos el blueprint y el decorador del archivo de tu compañero (auth.py)
from auth import auth_bp, login_required

# Cargar las variables del archivo .env
load_dotenv()

app = Flask(__name__)

# Configuración de la llave secreta para las sesiones
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')

# Registrar las rutas de autenticación de tu compañero
app.register_blueprint(auth_bp)

# Configuración única de DB extrayendo datos del .env
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": os.getenv("DB_PORT")
}

computers = {}  # diccionario de computadoras
TIMEOUT = 15  # Tiempo permitido entre conexion y conexion


# --- Lógica de Negocio: Computadoras ---
class Computer:
    def __init__(self, computer_id, name, ip, info):
        self.id = computer_id
        self.name = name
        self.ip = ip
        self.info = info
        self.last_heartbeat = datetime.now()
        self.status = "online"

    def update_heartbeat(self, info=None):
        self.last_heartbeat = datetime.now()
        self.status = "online"
        if info: self.info.update(info)

    def check_status(self):
        time_diff = (datetime.now() - self.last_heartbeat).total_seconds()
        self.status = "online" if time_diff <= TIMEOUT else "offline"
        return self.status

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'ip': self.ip,
            'status': self.status,
            'last_heartbeat': self.last_heartbeat.strftime('%Y-%m-%d %H:%M:%S'),
            'info': self.info
        }


def check_computers_status():
    while True:
        for computer_id in list(computers.keys()):
            comp = computers[computer_id]
            estado_anterior = comp.status
            estado_actual = comp.check_status()
            if estado_anterior == "online" and estado_actual == "offline":
                usuario = comp.info.get('current_user')
                matricula = comp.info.get('cardnumber')
                if usuario and usuario != "BLOQUEADA" and matricula:
                    try:
                        conn = psycopg2.connect(**DB_CONFIG)
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO bitacora_uso (computer_id, matricula, evento, fecha_hora) VALUES (%s, %s, 'LOGOUT_APAGADO', NOW() AT TIME ZONE 'America/Chihuahua')",
                            (computer_id, matricula)
                        )
                        conn.commit()
                        cursor.close()
                        conn.close()
                        print(f"Log automático: Logout registrado para la PC {computer_id} (Se apagó/desconectó)")
                        comp.info['current_user'] = "BLOQUEADA"
                        comp.info['locked'] = True
                        comp.info['cardnumber'] = None
                    except Exception as e:
                        print(f"Error registrando logout automático: {e}")
        time.sleep(5)


threading.Thread(target=check_computers_status, daemon=True).start()

# --- Lógica de Negocio: CSV ---
import pandas as pd
import io
import psycopg2


def procesar_csv(archivo, tabla):
    df = pd.read_csv(archivo, encoding="latin-1", dtype=str)

    # Limpiar y convertir la matrícula
    df["cardnumber"] = pd.to_numeric(df["cardnumber"], errors="coerce").fillna(0).astype('int64')
    df = df.drop_duplicates(subset=["cardnumber"], keep="first")

    # 1. Capitalizar la carrera/profesión (sort1)
    df["sort1"] = df["sort1"].fillna("Sin Profesión").astype(str).str.strip().str.title()

    # Separar los apellidos y nombres
    df["surname"] = df["surname"].astype(str)
    mask = df["surname"].str.contains(",", na=False)
    df.loc[mask, ["surname", "firstname"]] = df.loc[mask, "surname"].str.split(",", n=1, expand=True).values
    df.loc[~mask, ["surname", "firstname"]] = df.loc[~mask, "surname"].str.rsplit(" ", n=1, expand=True).values
    df["surname"] = df["surname"].astype(str).str.strip().str.title()
    df["firstname"] = df["firstname"].astype(str).str.strip().str.title()

    # Ordenar las columnas para la base de datos
    df = df[["cardnumber", "surname", "firstname", "sort1"]]

    # ==========================================
    # AGREGAR USUARIO INVITADO
    # ==========================================
    # Creamos un DataFrame con el registro del invitado
    invitado_df = pd.DataFrame([{
        "cardnumber": 10203,  # Se guarda como 10203 debido al int64/BIGINT
        "surname": "Invitado",
        "firstname": "Usuario",
        "sort1": "Invitado"
    }])

    # Lo concatenamos al final del DataFrame principal
    df = pd.concat([df, invitado_df], ignore_index=True)
    # ==========================================

    # Conexión y guardado en PostgreSQL
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # CUIDADO AQUÍ: Si hay riesgo de inyección SQL con la variable "tabla",
    cursor.execute(
        f'CREATE TABLE IF NOT EXISTS "{tabla}" (cardnumber BIGINT PRIMARY KEY, surname TEXT, firstname TEXT, sort1 TEXT);')
    cursor.execute(f'TRUNCATE TABLE "{tabla}";')

    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False)
    buffer.seek(0)

    cursor.copy_expert(f'COPY "{tabla}" FROM STDIN WITH (FORMAT CSV)', buffer)

    conn.commit()
    cursor.close()
    conn.close()

#######################################################################################################################
# --- Rutas ---
@app.route('/')
@login_required  # ¡Aquí está la magia! Esta línea protege tu dashboard.
def index():
    return render_template('dashboard.html')
###############################################-ruta-carga####################################################
@app.route('/api/upload', methods=['POST'])
@login_required  # Si quieres que solo el admin suba archivos
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No hay archivo en la petición"}), 400

    file = request.files['file']
    table_name = "alumnos"  # Definimos el nombre de la tabla

    if file and file.filename != '':
        try:
            # Procesamos el archivo directamente desde la memoria
            procesar_csv(file, table_name)
            return jsonify({"message": f"Éxito: Datos cargados en '{table_name}'"})
        except Exception as e:
            # Si algo falla en pandas o la DB, aquí atrapamos el error
            print(f"Error al procesar CSV: {e}")
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Archivo no válido"}), 400
###################################################-ruta-latido###########################################
@app.route('/api/heartbeat', methods=['POST'])
###################################################-ruta-latido###########################################
@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    c_id = data.get('id')
    nombre_pc = data.get('name', 'Desconocida')
    ip_pc = data.get('ip', request.remote_addr)

    # Si la PC no está en la memoria temporal (el servidor se acaba de reiniciar)
    if c_id not in computers:
        # 1. La agregamos al diccionario en memoria para que el dashboard sea rápido
        computers[c_id] = Computer(c_id, nombre_pc, ip_pc, data.get('info', {}))

        # 2. La guardamos/actualizamos en la base de datos de forma segura
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()

            # Aquí está la magia: INSERT ... ON CONFLICT
            query = """
                INSERT INTO computadoras (id, nombre, ip_ultima, fecha_registro) 
                VALUES (%s, %s, %s, NOW() AT TIME ZONE 'America/Chihuahua')
                ON CONFLICT (id) 
                DO UPDATE SET ip_ultima = EXCLUDED.ip_ultima, nombre = EXCLUDED.nombre;
            """
            cursor.execute(query, (c_id, nombre_pc, ip_pc))
            conn.commit()

            cursor.close()
            conn.close()
            print(f"PC Registrada/Actualizada en DB: {nombre_pc}")
        except Exception as e:
            print(f"Error al guardar computadora en DB: {e}")

    # Si ya estaba en memoria, solo actualizamos su latido (muy rápido, sin tocar la DB)
    else:
        computers[c_id].update_heartbeat(data.get('info'))

    return jsonify({'status': 'success'})
##################################################-ruta-computadoras-####################################################
@app.route('/api/computers')
@login_required
def get_computers():
    c_list = [c.to_dict() for c in computers.values()]
    return jsonify({
        'computers': c_list,
        'total': len(c_list),
        'online': sum(1 for c in c_list if c['status'] == 'online'),
        'offline': sum(1 for c in c_list if c['status'] == 'offline')
    })
###################################################################################################
@app.route('/api/computer/<computer_id>', methods=['DELETE'])
@login_required
def delete_computer(computer_id):
    if computer_id in computers:
        del computers[computer_id]
        return jsonify({'status': 'success'})
    return jsonify({'error': 'No encontrado'}), 404
################################################################################################
@app.route('/api/verify_student', methods=['POST'])
def verify_student():
    data = request.json
    matricula = data.get('cardnumber')
    computer_id = data.get('computer_id', 'Desconocida')
    tabla = "alumnos"

    if not matricula:
        return jsonify({'error': 'Matrícula requerida'}), 400

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = f'SELECT firstname, surname FROM "{tabla}" WHERE cardnumber = %s;'
        cursor.execute(query, (matricula,))
        alumno = cursor.fetchone()

        if alumno:
            try:
                query_log = "INSERT INTO bitacora_uso (computer_id, matricula, evento, fecha_hora) VALUES (%s, %s, 'LOGIN', NOW() AT TIME ZONE 'America/Chihuahua');"
                cursor.execute(query_log, (computer_id, matricula))
                conn.commit()
            except Exception as e_log:
                print(f"Error guardando log: {e_log}")
                conn.rollback()

        cursor.close()
        conn.close()

        if alumno:
            return jsonify({
                'status': 'success',
                'student': {'name': f"{alumno[0]} {alumno[1]}"}
            }), 200
        else:
            return jsonify({'status': 'error', 'message': 'Matrícula no registrada'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500
##############################################-ruta-estadisticas-####################################################
@app.route('/api/stats')
@login_required
def get_stats():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM alumnos")
        total_alumnos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM bitacora_uso WHERE evento='LOGIN' AND fecha_hora::date = CURRENT_DATE")
        logins_hoy = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM bitacora_uso WHERE evento='LOGIN' AND fecha_hora >= date_trunc('week', NOW())")
        logins_semana = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM bitacora_uso WHERE evento='LOGIN' AND fecha_hora >= date_trunc('month', NOW())")
        logins_mes = cursor.fetchone()[0]

        cursor.execute("""
            SELECT a.sort1, COUNT(*) as total
            FROM bitacora_uso b
            JOIN alumnos a ON b.matricula = a.cardnumber
            WHERE b.evento = 'LOGIN'
            GROUP BY a.sort1 ORDER BY total DESC LIMIT 10
        """)
        top_carreras_uso = [{'carrera': r[0], 'total': r[1]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT computer_id, COUNT(*) as total
            FROM bitacora_uso WHERE evento = 'LOGIN'
            GROUP BY computer_id ORDER BY total DESC LIMIT 10
        """)
        top_pcs = [{'pc': r[0], 'total': r[1]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT sort1, COUNT(*) as total FROM alumnos
            GROUP BY sort1 ORDER BY total DESC LIMIT 10
        """)
        dist_carreras = [{'carrera': r[0], 'total': r[1]} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT b.computer_id, a.firstname, a.surname, b.matricula, b.evento, b.fecha_hora
            FROM bitacora_uso b
            LEFT JOIN alumnos a ON b.matricula = a.cardnumber
            ORDER BY b.fecha_hora DESC LIMIT 15
        """)
        recientes = []
        for r in cursor.fetchall():
            recientes.append({
                'pc': r[0],
                'nombre': f"{r[1] or ''} {r[2] or ''}".strip() or 'Desconocido',
                'matricula': r[3],
                'evento': r[4],
                'timestamp': r[5].strftime('%d/%m/%Y %H:%M') if r[5] else ''
            })

        cursor.close()
        conn.close()

        return jsonify({
            'total_alumnos': total_alumnos,
            'logins_hoy': logins_hoy,
            'logins_semana': logins_semana,
            'logins_mes': logins_mes,
            'top_carreras_uso': top_carreras_uso,
            'top_pcs': top_pcs,
            'dist_carreras': dist_carreras,
            'recientes': recientes
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
##############################################/app-run/################################################################
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
