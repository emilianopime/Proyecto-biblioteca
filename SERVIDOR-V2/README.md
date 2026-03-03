# Sistema de Monitoreo de Laboratorio — UACH

Servidor Flask que monitorea en tiempo real las computadoras de un laboratorio universitario. Permite al administrador ver qué equipos están encendidos, qué alumno tiene sesión activa en cada uno y consultar estadísticas de uso. Los nodos kiosko instalados en cada PC reportan su estado periódicamente al servidor.

---

## Arquitectura general

```
┌─────────────────────────────────────────────────────┐
│  Laboratorio                                         │
│                                                      │
│  [PC Kiosko 1] ──┐                                   │
│  [PC Kiosko 2] ──┼──▶  Servidor Flask :8000          │
│  [PC Kiosko N] ──┘        │                          │
│                            ▼                         │
│                       PostgreSQL 16                  │
└─────────────────────────────────────────────────────┘
         ▲
         │  Dashboard web (navegador del administrador)
```

- **Servidor Flask** (`main.py`): expone el dashboard administrativo y la API que consumen los nodos kiosko.
- **Nodo kiosko** (`cliente/client_kiosk.py`): script Python instalado en cada PC del laboratorio. Envía un heartbeat cada pocos segundos y verifica matrículas cuando un alumno se identifica.
- **PostgreSQL 16**: almacena el padrón de alumnos, la bitácora de uso y el registro de equipos conocidos.

---

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) y Docker Compose (incluido en Docker Desktop)
- Git

No se necesita Python, PostgreSQL ni ninguna dependencia instalada localmente; todo corre dentro de contenedores.

---

## Puesta en marcha (Docker)

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd SERVIDOR-V2
```

### 2. Crear el archivo de variables de entorno

```bash
cp .env.example .env
```

Edita `.env` y cambia los valores marcados:

```env
# Base de datos (usados por Flask)
DB_HOST=db          # NO cambiar — es el nombre del servicio en Docker
DB_NAME=basedatosuach
DB_USER=postgres
DB_PASSWORD=pon-una-contrasena-segura   # ← cambiar

# Variables nativas de la imagen postgres:16
# Deben coincidir exactamente con DB_NAME, DB_USER, DB_PASSWORD
POSTGRES_DB=basedatosuach
POSTGRES_USER=postgres
POSTGRES_PASSWORD=pon-una-contrasena-segura   # ← cambiar (igual que DB_PASSWORD)

# Flask
SECRET_KEY=genera-una-clave-larga-y-aleatoria   # ← cambiar

# Credenciales del dashboard web
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=pon-una-contrasena-segura   # ← cambiar
```

> **Importante:** `DB_HOST` debe quedarse como `db`. Ese nombre apunta al contenedor de PostgreSQL dentro de la red de Docker.

### 3. Levantar los contenedores

```bash
docker compose up -d
```

Docker construye la imagen de Flask, descarga la imagen de PostgreSQL, crea las tablas automáticamente (via `docker/init.sql`) y levanta ambos servicios.

### 4. Verificar que todo está corriendo

```bash
docker compose ps
```

Debes ver los dos servicios con estado `Up` y `(healthy)` en el de base de datos:

```
NAME                  IMAGE              STATUS
servidor-v2-db-1      postgres:16        Up (healthy)
servidor-v2-web-1     servidor-v2-web    Up
```

### 5. Acceder al dashboard

Abre el navegador en: **http://localhost:8000**

Inicia sesión con las credenciales que configuraste en `DASHBOARD_USER` y `DASHBOARD_PASSWORD`.

---

## Comandos útiles

```bash
# Levantar en background
docker compose up -d

# Ver logs del servidor Flask
docker compose logs web

# Ver logs de PostgreSQL
docker compose logs db

# Seguir los logs en tiempo real
docker compose logs -f web

# Detener y eliminar los contenedores (los datos del volumen se conservan)
docker compose down

# Detener y eliminar también los datos de la base de datos
docker compose down -v

# Reconstruir la imagen después de cambios en el código
docker compose up -d --build
```

---

## Estructura del proyecto

```
SERVIDOR-V2/
├── main.py               # Servidor Flask principal
├── auth.py               # Módulo de autenticación del dashboard
├── requirements.txt      # Dependencias Python
├── pyproject.toml        # Configuración del proyecto (uv)
│
├── Dockerfile            # Imagen Python 3.12-slim del servidor
├── docker-compose.yml    # Orquestación: Flask + PostgreSQL 16
├── .env.example          # Plantilla de variables de entorno
├── .dockerignore         # Archivos excluidos del build de Docker
│
├── docker/
│   └── init.sql          # Script SQL que crea las tablas al iniciar Postgres
│
├── templates/
│   ├── dashboard.html    # Panel de administración
│   └── login.html        # Pantalla de inicio de sesión
│
├── static/
│   ├── css/
│   │   ├── style.css
│   │   ├── dashboard.css
│   │   └── login.css
│   └── js/
│       └── dashboard.js
│
└── cliente/
    └── client_kiosk.py   # Script para instalar en cada PC del laboratorio
```

---

## Base de datos

Las tablas se crean automáticamente cuando el contenedor de PostgreSQL arranca por primera vez gracias a `docker/init.sql`.

| Tabla | Descripción |
|---|---|
| `alumnos` | Padrón de alumnos cargado desde CSV (cardnumber, nombre, carrera) |
| `bitacora_uso` | Registro de cada LOGIN y LOGOUT de alumno en cada equipo |
| `computadoras` | Equipos conocidos por el servidor; persisten entre reinicios |

---

## API del servidor

### Rutas del dashboard (requieren sesión activa)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Panel principal |
| `GET` | `/api/computers` | Lista de equipos con estado en tiempo real |
| `DELETE` | `/api/computer/<id>` | Eliminar un equipo del monitor |
| `POST` | `/api/upload` | Cargar padrón de alumnos desde CSV |
| `GET` | `/api/stats` | Estadísticas de uso del laboratorio |

### Rutas de la API kiosko (abiertas, llamadas desde los nodos)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/heartbeat` | Latido periódico del nodo; registra que el equipo sigue encendido |
| `POST` | `/api/verify_student` | Verifica una matrícula y registra el LOGIN en la bitácora |

---

## Cargar el padrón de alumnos

El dashboard incluye una zona de carga (drag & drop) para subir el CSV del padrón. El archivo se procesa en memoria sin guardarse en disco.

**Columnas esperadas en el CSV:**

| Columna | Descripción |
|---|---|
| `cardnumber` | Número de matrícula del alumno |
| `surname` | Apellido(s) |
| `firstname` | Nombre(s) |
| `sort1` | Carrera o programa académico |

---

## Configuración del nodo kiosko

El script `cliente/client_kiosk.py` se instala en cada PC del laboratorio. Necesita saber la dirección IP del servidor:

```python
# Editar en client_kiosk.py
SERVER_URL = "http://<ip-del-servidor>:8000"
```

El nodo kiosko requiere Python y las dependencias necesarias instaladas localmente en cada PC (no usa Docker).

---

## Variables de entorno — referencia completa

| Variable | Descripción | Ejemplo |
|---|---|---|
| `DB_HOST` | Hostname de PostgreSQL | `db` (dentro de Docker) |
| `DB_NAME` | Nombre de la base de datos | `basedatosuach` |
| `DB_USER` | Usuario de PostgreSQL | `postgres` |
| `DB_PASSWORD` | Contraseña de PostgreSQL | *(valor seguro)* |
| `DB_PORT` | Puerto de PostgreSQL | `5432` |
| `POSTGRES_DB` | Igual que `DB_NAME` (requerido por la imagen oficial) | `basedatosuach` |
| `POSTGRES_USER` | Igual que `DB_USER` (requerido por la imagen oficial) | `postgres` |
| `POSTGRES_PASSWORD` | Igual que `DB_PASSWORD` (requerido por la imagen oficial) | *(valor seguro)* |
| `SECRET_KEY` | Clave para firmar las cookies de sesión de Flask | *(cadena larga y aleatoria)* |
| `DASHBOARD_USER` | Usuario del panel administrativo | `admin` |
| `DASHBOARD_PASSWORD` | Contraseña del panel administrativo | *(valor seguro)* |
