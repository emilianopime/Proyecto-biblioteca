import tkinter as tk
from tkinter import messagebox
import threading
import time
import requests
import socket
import json
import os
import sys

# ==========================================
# GESTIÓN DE LA CONFIGURACIÓN
# ==========================================
def get_base_dir():
    """Carpeta donde vive el programa.

    Al correr como .exe compilado, el directorio de trabajo depende de cómo se
    haya lanzado (un acceso directo del inicio de Windows puede dejarlo en
    System32). Buscar el config.json ahí haría que el cliente ignorara la
    configuración y se conectara a la URL por defecto. Por eso se resuelve
    siempre contra la ubicación real del ejecutable.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(get_base_dir(), "config.json")
DEFAULT_SERVER_URL = "http://192.168.1.68:8000"
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Intenta conectar a una IP externa para descubrir qué interfaz de red se usa
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

def load_server_url():
    """Lee la URL del servidor desde un archivo JSON. Si no existe, lo crea."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Retorna la URL del archivo, o la default si la clave no existe
                return config.get("server_url", DEFAULT_SERVER_URL)
        except Exception as e:
            print(f"Error leyendo {CONFIG_FILE}: {e}")
            return DEFAULT_SERVER_URL
    else:
        # Crea el archivo de configuración base si no se encuentra
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump({"server_url": DEFAULT_SERVER_URL}, f, indent=4)
        except Exception as e:
            print(f"Error creando {CONFIG_FILE}: {e}")
        return DEFAULT_SERVER_URL

# ==========================================
# CONFIGURACIÓN DEL CLIENTE
# ==========================================
SERVER_URL = load_server_url()      # <-- Ahora se carga desde el archivo
COMPUTER_ID = socket.gethostname()  # Usa el nombre real de la PC como ID
COMPUTER_NAME = f"Lab_{COMPUTER_ID}"


class KioskApp:
    def __init__(self, root):
        self.root = root
        self.current_matricula = None
        self.current_user = None  # Almacenará el nombre del alumno activo por default en none
        self.is_locked = True

        # 1. Configuración Modo Kiosco Pantalla completa sin bordes
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)  # Mantiene la ventana siempre arriba
        self.root.configure(bg='#2d3748')

        # Evitar que se cierre con Alt+F4
        self.root.protocol("WM_DELETE_WINDOW", self.disable_event)
        # 2. Construir la Interfaz de Usuario
        self.build_ui()

        # 3. Iniciar el hilo del latido
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def build_ui(self):
        # Contenedor central
        frame = tk.Frame(self.root, bg='white', padx=40, pady=40)
        frame.place(relx=0.5, rely=0.5, anchor='center')

        tk.Label(frame, text="💻 Laboratorio UACH", font=("Segoe UI", 24, "bold"), bg='white', fg='#2b6cb0').pack(
            pady=(0, 20))
        tk.Label(frame, text="Ingresa tu matrícula para desbloquear el equipo:", font=("Segoe UI", 12),
                 bg='white').pack(pady=(0, 10))

        self.entry_matricula = tk.Entry(frame, font=("Segoe UI", 16), justify='center')
        self.entry_matricula.pack(pady=10, fill='x')
        self.entry_matricula.bind('<Return>', lambda event: self.verificar_login())  # Permitir 'Enter'
        self.entry_matricula.focus()

        self.btn_login = tk.Button(frame, text="Desbloquear PC", font=("Segoe UI", 14, "bold"), bg='#48bb78',
                                   fg='white', command=self.verificar_login)
        self.btn_login.pack(pady=20, fill='x')

        self.lbl_mensaje = tk.Label(frame, text="", font=("Segoe UI", 12), bg='white')
        self.lbl_mensaje.pack()

    def disable_event(self):
        # Evita que el usuario cierre la ventana con la 'X' o Alt+F4
        pass

    # ==========================================
    # LÓGICA DE VERIFICACIÓN (Conexión al Servidor)
    # ==========================================
    def verificar_login(self):
        matricula = self.entry_matricula.get().strip()
        if not matricula:
            self.lbl_mensaje.config(text="Ingresa una matrícula válida.", fg="red")
            return
        self.lbl_mensaje.config(text="Verificando...", fg="blue")
        self.btn_login.config(state=tk.DISABLED)
        # Usamos un hilo corto para la petición y no congelar la UI
        threading.Thread(target=self._hacer_peticion_login, args=(matricula,), daemon=True).start()

    def _hacer_peticion_login(self, matricula):
        try:
            # 1. Agregamos los datos de la computadora al payload
            payload = {
                "cardnumber": matricula,
                "computer_id": COMPUTER_ID,
                "computer_name": COMPUTER_NAME
            }

            # 2. Enviamos el payload completo en lugar de solo la matrícula
            response = requests.post(f"{SERVER_URL}/api/verify_student", json=payload, timeout=5)
            data = response.json()

            if response.status_code == 200 and data.get('status') == 'success':
                self.current_user = data['student']['name']
                self.current_matricula = matricula
                self.root.after(0, self._desbloquear_exitoso)
            else:
                msg = data.get('message', 'Acceso denegado')
                self.root.after(0, lambda: self._mostrar_error(msg))
        except Exception as e:
            self.root.after(0, lambda: self._mostrar_error("Error de conexión con el servidor."))

    def _mostrar_error(self, mensaje):
        self.lbl_mensaje.config(text=mensaje, fg="red")
        self.btn_login.config(state=tk.NORMAL)
        self.entry_matricula.delete(0, tk.END)

    def _desbloquear_exitoso(self):
        self.is_locked = False
        self.lbl_mensaje.config(text=f"Bienvenido(a)", fg="green")

        # Ocultar la ventana principal para liberar el escritorio
        self.root.after(1500, self.root.withdraw)

    # ==========================================
    # HILO DE MONITOREO
    # ==========================================
    def heartbeat_loop(self):
        while True:
            # Información del sistema
            info_sistema = {
                "platform": "Windows",
                "locked": self.is_locked,
                "cardnumber": self.current_matricula if not self.is_locked else None,
                "current_user": self.current_user if not self.is_locked else "BLOQUEADA"
            }

            data = {
                "id": COMPUTER_ID,
                "name": COMPUTER_NAME,
                "ip": LOCAL_IP,
                "info": info_sistema

            }

            try:
                requests.post(f"{SERVER_URL}/api/heartbeat", json=data, timeout=3)
            except requests.exceptions.RequestException:
                pass  # Si el servidor cae, el cliente sigue intentando en silencio

            time.sleep(10)  # Enviar latido cada 10 segundos


if __name__ == "__main__":
    root = tk.Tk()
    app = KioskApp(root)
    root.mainloop()