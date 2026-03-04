"""
auth.py — Modulo de autenticacion del dashboard

Responsabilidades:
  - Proveer el decorador `login_required` para proteger rutas del dashboard.
  - Manejar el inicio y cierre de sesion del administrador.

Rutas registradas (Blueprint 'auth'):
  GET  /login   — Muestra el formulario de inicio de sesion.
  POST /login   — Valida las credenciales y crea la sesion.
  GET  /logout  — Destruye la sesion y redirige al login.

Las credenciales se leen desde variables de entorno definidas en el archivo .env:
  DASHBOARD_USER     — Nombre de usuario del administrador.
  DASHBOARD_PASSWORD — Contrasena del administrador.
"""

import os
from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    redirect,
    url_for,
    jsonify
)

# Blueprint que agrupa todas las rutas de autenticacion.
# Se registra en main.py con app.register_blueprint(auth_bp).
auth_bp = Blueprint("auth", __name__)


# ---------------------------------------------------------------------------
# Decorador de proteccion de rutas
# ---------------------------------------------------------------------------

def login_required(f):
    """
    Decorador para rutas del dashboard que requieren sesion activa.

    Si el usuario no ha iniciado sesion, lo redirige a /login.
    Uso:
        @app.route('/mi-ruta')
        @login_required
        def mi_vista():
            ...
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            # Si la petición es de Javascript (API), devolver error 401
            if request.path.startswith('/api/'):
                return jsonify({"error": "Sesión expirada"}), 401
            # Si es navegación normal, redirigir al login
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Rutas de autenticacion
# ---------------------------------------------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    GET  — Renderiza el formulario de inicio de sesion.
           Si ya hay sesion activa, redirige directamente al dashboard.
    POST — Valida usuario y contrasena contra las variables de entorno.
           Si son correctos, crea la sesion y redirige al dashboard.
           Si son incorrectos, muestra un mensaje de error.
    """
    # Si ya tiene sesion, no tiene sentido mostrar el login de nuevo
    if session.get("authenticated"):
        return redirect(url_for("index"))

    error = None

    if request.method == "POST":
        usuario_ingresado    = request.form.get("username", "").strip()
        contrasena_ingresada = request.form.get("password", "")

        usuario_correcto    = os.getenv("DASHBOARD_USER")
        contrasena_correcta = os.getenv("DASHBOARD_PASSWORD")

        if usuario_ingresado == usuario_correcto and contrasena_ingresada == contrasena_correcta:
            # Credenciales validas: guardar estado de sesion
            session["authenticated"] = True
            session["username"]      = usuario_ingresado
            return redirect(url_for("index"))

        error = "Usuario o contrasena incorrectos."

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    """
    Destruye la sesion del administrador y redirige al formulario de login.
    """
    session.clear()
    return redirect(url_for("auth.login"))
