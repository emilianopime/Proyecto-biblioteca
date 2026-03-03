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
│  Contenedor: web  (SERVIDOR-V2/main.py)          │
│  Flask · Python 3.12 · Puerto 8000               │
│  - Dashboard protegido con sesión                │
│  - API para los nodos kiosko                     │
└──────────┬───────────────────────┬───────────────┘
           │ psycopg2              │ HTTP (heartbeat / verify)
┌──────────▼──────────┐  ┌────────▼───────────────┐
│  Contenedor: db     │  │  PCs del laboratorio   │
│  PostgreSQL 16      │  │  cliente/client_kiosk.py│
│  Puerto 5432        │  │  Tkinter · modo kiosko  │
└─────────────────────┘  └────────────────────────┘
```

---

## Requisitos previos

- [Docker](https://docs.docker.com/get-docker/) con Docker Compose (incluido en Docker Desktop)
- Git

> El servidor Flask y PostgreSQL corren completamente en contenedores. No se necesita Python ni ninguna dependencia instalada localmente para correr el servidor.

---

## 1. Configurar variables de entorno

Dentro de `SERVIDOR-V2/`, copia la plantilla y rellena los valores:

```bash
cp SERVIDOR-V2/.env.example SERVIDOR-V2/.env
```

Edita `SERVIDOR-V2/.env`:

```env
# Base de datos (usados por Flask)
DB_HOST=db          # NO cambiar — apunta al contenedor de postgres en Docker
DB_NAME=basedatosuach
DB_USER=postgres
DB_PASSWORD=tu_password_seguro

# Requeridos por la imagen oficial de postgres:16
# Deben coincidir exactamente con DB_NAME, DB_USER y DB_PASSWORD
POSTGRES_DB=basedatosuach
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_password_seguro

# Flask
SECRET_KEY=genera-una-con: python -c "import secrets; print(secrets.token_hex(32))"

# Credenciales del dashboard web
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=tu_contraseña_segura
```

---

## 2. Levantar el servidor con Docker Compose

```bash
cd SERVIDOR-V2
docker compose up -d
```

Esto realiza automáticamente:
- Construye la imagen de Flask con Python 3.12
- Descarga la imagen de PostgreSQL 16
- Crea las tablas necesarias en la base de datos (`docker/init.sql`)
- Levanta ambos contenedores y espera a que postgres esté listo antes de iniciar Flask

Verifica que todo esté corriendo:

```bash
docker compose ps
```

```
NAME                  IMAGE              STATUS
servidor-v2-db-1      postgres:16        Up (healthy)
servidor-v2-web-1     servidor-v2-web    Up
```

El servidor queda disponible en **http://localhost:8000**.
Inicia sesión con las credenciales configuradas en `DASHBOARD_USER` y `DASHBOARD_PASSWORD`.

---

## 3. Comandos útiles

```bash
# Ver logs del servidor Flask
docker compose logs web

# Ver logs de PostgreSQL
docker compose logs db

# Seguir logs en tiempo real
docker compose logs -f web

# Detener los contenedores (los datos se conservan)
docker compose down

# Detener y eliminar también los datos de la base de datos
docker compose down -v

# Reconstruir la imagen después de cambios en el código
docker compose up -d --build
```

---

## 4. Configurar y ejecutar el cliente kiosko

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

## 5. Cargar el padrón de alumnos

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
    ├── requirements.txt     # Dependencias Python
    ├── Dockerfile           # Imagen Python 3.12-slim del servidor
    ├── docker-compose.yml   # Orquestación: Flask + PostgreSQL 16
    ├── .env.example         # Plantilla de variables de entorno
    ├── .dockerignore        # Archivos excluidos del build de Docker
    ├── docker/
    │   └── init.sql         # Crea las tablas automáticamente al iniciar postgres
    ├── templates/
    │   ├── dashboard.html   # Panel de control (monitoreo + estadísticas)
    │   └── login.html       # Pantalla de inicio de sesión
    ├── static/
    │   ├── css/
    │   │   ├── style.css
    │   │   ├── dashboard.css
    │   │   └── login.css
    │   └── js/
    │       └── dashboard.js
    └── cliente/
        └── client_kiosk.py  # App Tkinter que corre en cada nodo
```

---

## Base de datos

Las tablas se crean automáticamente cuando el contenedor de PostgreSQL arranca por primera vez gracias a `docker/init.sql`. No es necesario crearlas manualmente.

| Tabla | Descripción |
|---|---|
| `alumnos` | Padrón de alumnos cargado desde CSV |
| `bitacora_uso` | Registro de cada LOGIN y LOGOUT por equipo |
| `computadoras` | Equipos conocidos; persisten entre reinicios del servidor |

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
