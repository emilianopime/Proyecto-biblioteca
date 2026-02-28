import os
from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    redirect,
    url_for,
)

# Blueprint que agrupa todas las rutas de autenticacion.
# Se registra en main.py con app.register_blueprint(auth_bp).
auth_bp = Blueprint("auth", __name__)

def login_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
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

    session.clear()
    return redirect(url_for("auth.login"))
