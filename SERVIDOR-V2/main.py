from flask import Flask, render_template, request, jsonify
from datetime import datetime
import threading
import time
import pandas as pd
import psycopg2
import io

app = Flask(__name__)

# Configuración única de DB
DB_CONFIG = {
    "host": "localhost", # aqui se deja como localhost
    "database": "basedatosuach", #poner el nombre de la base de datos
    "user": "postgres", # El usuario duenio de la base de datos
    "password": "contraseña", # poner el password para la base de datos
    "port": "5432" # especificar el puerto donde corre la base de datos
}

computers = {}  #diccionario de computadoras
TIMEOUT = 15  #Tiempo permitido entre conexion y conexion


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
        # Iteramos sobre las computadoras registradas
        for computer_id in list(computers.keys()):
            comp = computers[computer_id]
            estado_anterior = comp.status
            estado_actual = comp.check_status()
            # DETECCIÓN: Si estaba online y ahora está offline (Se apagó/desconectó)
            if estado_anterior == "online" and estado_actual == "offline":
                usuario = comp.info.get('current_user')
                matricula = comp.info.get('cardnumber')
                # Verificamos si había alguien usando la PC en ese momento
                if usuario and usuario != "BLOQUEADA" and matricula:
                    try:
                        # Registramos el LOGOUT en PostgreSQL
                        conn = psycopg2.connect(**DB_CONFIG)
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO bitacora_uso (computer_id, matricula, evento) VALUES (%s, %s, 'LOGOUT_APAGADO')",
                            (computer_id, matricula)
                        )
                        conn.commit()
                        cursor.close()
                        conn.close()
                        print(f"Log automático: Logout registrado para la PC {computer_id} (Se apagó/desconectó)")
                        # limpieza para no repetir el log en el siguiente ciclo
                        comp.info['current_user'] = "BLOQUEADA"
                        comp.info['locked'] = True
                        comp.info['cardnumber'] = None
                    except Exception as e:
                        print(f"Error registrando logout automático: {e}")
        time.sleep(5)  # Verifica cada 5 segundos


threading.Thread(target=check_computers_status, daemon=True).start()


# --- Lógica de Negocio: CSV ---
def procesar_csv(archivo, tabla):
    df = pd.read_csv(archivo, encoding="latin-1", dtype=str)
    df["cardnumber"] = pd.to_numeric(df["cardnumber"], errors="coerce").fillna(0).astype('int64')
    df = df.drop_duplicates(subset=["cardnumber"], keep="first")
    df["sort1"] = df["sort1"].fillna("Sin Profesión").astype(str).str.strip()

    # Procesamiento de nombres
    df["surname"] = df["surname"].astype(str)
    mask = df["surname"].str.contains(",", na=False)
    df.loc[mask, ["surname", "firstname"]] = df.loc[mask, "surname"].str.split(",", n=1, expand=True).values
    df.loc[~mask, ["surname", "firstname"]] = df.loc[~mask, "surname"].str.rsplit(" ", n=1, expand=True).values

    df = df[["cardnumber", "surname", "firstname", "sort1"]]

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
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
def index():
    return render_template('dashboard.html')
###############################################-ruta-carga####################################################
@app.route('/api/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    table_name = request.form.get('table_name', 'alumnos')
    try:
        procesar_csv(file, table_name)
        return jsonify({"message": f"Éxito: Datos cargados en '{table_name}'"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
###################################################-ruta-latido###########################################
@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    c_id = data.get('id')
    if c_id not in computers:
        computers[c_id] = Computer(c_id, data.get('name'), data.get('ip', request.remote_addr), data.get('info', {}))
    else:
        computers[c_id].update_heartbeat(data.get('info'))
    return jsonify({'status': 'success'})
##################################################-ruta-computadoras-####################################################
@app.route('/api/computers')
def get_computers(): #Esta funcion nos ayuda a contar cuantas hay prendidas, apagadas.
    c_list = [c.to_dict() for c in computers.values()]
    return jsonify({
        'computers': c_list,
        'total': len(c_list),
        'online': sum(1 for c in c_list if c['status'] == 'online'),
        'offline': sum(1 for c in c_list if c['status'] == 'offline')
    })
###################################################################################################
@app.route('/api/computer/<computer_id>', methods=['DELETE'])
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
    # Por defecto busca en la tabla 'alumnos'
    tabla = "alumnos"
    if not matricula:
        return jsonify({'error': 'Matrícula requerida'}), 400

    try:
        conn = psycopg2.connect(**DB_CONFIG)  # Usa la configuración de tu DB
        cursor = conn.cursor()
        # Consultamos si existe la matrícula en la tabla de alumnos
        query = f'SELECT firstname, surname FROM "{tabla}" WHERE cardnumber = %s;'
        cursor.execute(query, (matricula,))
        alumno = cursor.fetchone()
        if alumno:
            try:
                # Insertamos el evento LOGIN usando el mismo cursor
                query_log = "INSERT INTO bitacora_uso (computer_id, matricula, evento) VALUES (%s, %s, 'LOGIN');"
                cursor.execute(query_log, (computer_id, matricula))
                conn.commit()  # Guardamos los cambios en la base de datos
            except Exception as e_log:
                print(f"Error guardando log: {e_log}")
                conn.rollback()  # Evita que un error en el log tumbe la verificación
            # ------------------------------------------
        # Cerramos conexiones después de hacer todo
        cursor.close()
        conn.close()
        if alumno:
            # Si lo encuentra, devolvemos el nombre para el saludo en Tkinter
            return jsonify({
                'status': 'success',
                'student': {
                    'name': f"{alumno[0]} {alumno[1]}"
                }
            }), 200
        else:
            # Si no existe en la base de datos
            return jsonify({'status': 'error', 'message': 'Matrícula no registrada'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500
##############################################-ruta-estadisticas-####################################################
@app.route('/api/stats')
def get_stats():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM alumnos")
        total_alumnos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM bitacora_uso WHERE evento='LOGIN' AND timestamp::date = CURRENT_DATE")
        logins_hoy = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM bitacora_uso WHERE evento='LOGIN' AND timestamp >= date_trunc('week', NOW())")
        logins_semana = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM bitacora_uso WHERE evento='LOGIN' AND timestamp >= date_trunc('month', NOW())")
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
            SELECT b.computer_id, a.firstname, a.surname, b.matricula, b.evento, b.timestamp
            FROM bitacora_uso b
            LEFT JOIN alumnos a ON b.matricula = a.cardnumber
            ORDER BY b.timestamp DESC LIMIT 15
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