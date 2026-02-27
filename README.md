# Sistema de Monitoreo de Laboratorio — UACH

Aplicación web para monitorear en tiempo real el uso de las computadoras del laboratorio de la biblioteca. El administrador accede a un dashboard desde el navegador; cada PC del laboratorio corre un cliente kiosko en Python que bloquea el escritorio hasta que el alumno ingresa su matrícula.

---

## Arquitectura

```
┌──────────────────────────────────────────────────┐
│  PC del administrador                            │
│  Navegador → http://<IP_SERVIDOR>:8000           │
└─────────────────────┬────────────────────────────┘
                      │ HTTP (Flask)
┌─────────────────────▼────────────────────────────┐
│  Servidor  (SERVIDOR-V2/main.py)                 │
│  Flask · Python 3.12 · Puerto 8000               │
│  - Dashboard protegido con sesión                │
│  - API para los nodos kiosko                     │
└──────────┬───────────────────────┬───────────────┘
           │ psycopg2              │ HTTP (heartbeat / verify)
┌──────────▼──────────┐  ┌────────▼───────────────┐
│  PostgreSQL          │  │  PCs del laboratorio   │
│  (Docker)           │  │  cliente/client_kiosk.py│
│  Puerto 5432        │  │  Tkinter · modo kiosko  │
└─────────────────────┘  └────────────────────────┘
```

---

## Requisitos previos

- Python 3.12+
- Docker (para la base de datos)
- `pip`

---

## 1. Base de datos con Docker

Levanta un contenedor de PostgreSQL:

```bash
docker run -d \
  --name postgres-biblioteca \
  -e POSTGRES_DB=basedatosuach \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=tu_password \
  -p 5432:5432 \
  postgres:16
```

Para detenerlo y volverlo a arrancar en sesiones posteriores:

```bash
docker stop postgres-biblioteca
docker start postgres-biblioteca
```

### Crear la tabla de bitácora

La tabla `alumnos` se crea automáticamente al cargar el primer CSV desde el dashboard. La tabla `bitacora_uso` hay que crearla manualmente una sola vez:

```bash
docker exec -it postgres-biblioteca psql -U postgres -d basedatosuach
```

```sql
CREATE TABLE bitacora_uso (
    id          SERIAL PRIMARY KEY,
    computer_id TEXT,
    matricula   BIGINT,
    evento      TEXT,
    timestamp   TIMESTAMP DEFAULT NOW()
);
```

---

## 2. Configurar variables de entorno

Dentro de `SERVIDOR-V2/`, copia la plantilla y rellena los valores:

```bash
cp SERVIDOR-V2/.env.example SERVIDOR-V2/.env
```

Edita `SERVIDOR-V2/.env`:

```env
SECRET_KEY=<genera una con: python -c "import secrets; print(secrets.token_hex(32))">
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=tu_contraseña_segura
DB_HOST=localhost
DB_NAME=basedatosuach
DB_USER=postgres
DB_PASSWORD=tu_password
DB_PORT=5432
```

---

## 3. Instalar dependencias del servidor

El proyecto usa [uv](https://docs.astral.sh/uv/) para gestionar dependencias y entorno virtual.

```bash
cd SERVIDOR-V2
uv sync
```

---

## 4. Levantar el servidor

```bash
cd SERVIDOR-V2
uv run python main.py
```

El servidor queda disponible en `http://0.0.0.0:8000`.
Abre `http://localhost:8000` en el navegador e inicia sesión con las credenciales del `.env`.

---

## 5. Configurar y ejecutar el cliente kiosko

El cliente corre en **cada PC del laboratorio**. Antes de desplegarlo, edita la IP del servidor en `SERVIDOR-V2/cliente/client_kiosk.py`:

```python
SERVER_URL = "http://<IP_DEL_SERVIDOR>:8000"   # línea 11
```

Instala las dependencias del cliente (en cada nodo):

```bash
pip install requests
```

Ejecuta el cliente:

```bash
python client_kiosk.py
```

El cliente abre una ventana en modo kiosko a pantalla completa que:
- Bloquea el escritorio hasta que el alumno ingresa su matrícula.
- Envía un heartbeat al servidor cada 10 segundos.
- Registra automáticamente el LOGIN al verificar la matrícula.

---

## 6. Cargar el padrón de alumnos

Desde el dashboard (`http://localhost:8000`), ve a **Carga de alumnos** y arrastra el archivo CSV del padrón. El CSV debe tener las columnas:

| Columna      | Descripción                        |
|--------------|------------------------------------|
| `cardnumber` | Matrícula del alumno               |
| `surname`    | Apellido(s)                        |
| `firstname`  | Nombre(s)                          |
| `sort1`      | Carrera / profesión                |

La carga reemplaza el padrón completo cada vez.

---

## Estructura del proyecto

```
Proyecto-biblioteca/
├── README.md
└── SERVIDOR-V2/
    ├── main.py              # Servidor Flask principal
    ├── auth.py              # Módulo de autenticación del dashboard
    ├── requirements.txt     # Dependencias del servidor
    ├── .env.example         # Plantilla de variables de entorno
    ├── templates/
    │   ├── dashboard.html   # Panel de control (monitoreo + estadísticas)
    │   └── login.html       # Pantalla de inicio de sesión
    ├── static/
    │   ├── css/style.css
    │   └── js/dashboard.js
    └── cliente/
        └── client_kiosk.py  # App Tkinter que corre en cada nodo
```

---

## API del servidor (referencia rápida)

| Método | Ruta                        | Descripción                                      |
|--------|-----------------------------|--------------------------------------------------|
| GET    | `/`                         | Dashboard (requiere sesión)                      |
| GET    | `/login`                    | Formulario de login                              |
| GET    | `/logout`                   | Cierra la sesión                                 |
| POST   | `/api/upload`               | Carga el padrón CSV (requiere sesión)            |
| GET    | `/api/computers`            | Estado de todos los equipos (requiere sesión)    |
| DELETE | `/api/computer/<id>`        | Elimina un equipo del monitor (requiere sesión)  |
| GET    | `/api/stats`                | Estadísticas de uso (requiere sesión)            |
| POST   | `/api/heartbeat`            | Latido del nodo kiosko (abierto)                 |
| POST   | `/api/verify_student`       | Verifica matrícula y registra LOGIN (abierto)    |
