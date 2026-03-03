# Dockerización Flask + PostgreSQL — Plan de Implementación

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Contenerizar el servidor Flask y PostgreSQL 16 con docker-compose, incluyendo inicialización automática de tablas.

**Architecture:** Dockerfile con python:3.12-slim instala dependencias y corre main.py. docker-compose orquesta dos servicios (db + web) leyendo credenciales de un archivo .env. Un script SQL se monta en postgres para crear las 3 tablas al inicio.

**Tech Stack:** Docker, docker-compose, python:3.12-slim, postgres:16, Flask, psycopg2-binary

---

### Task 1: Crear `docker/init.sql`

**Files:**
- Create: `docker/init.sql`

**Step 1: Crear el archivo SQL con las 3 tablas**

```sql
-- docker/init.sql
-- Este archivo se ejecuta automáticamente la primera vez que
-- el contenedor de PostgreSQL arranca (directorio initdb.d).

CREATE TABLE IF NOT EXISTS computadoras (
    id             TEXT PRIMARY KEY,
    name           TEXT,
    ip             TEXT,
    last_heartbeat TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alumnos (
    cardnumber BIGINT PRIMARY KEY,
    surname    TEXT,
    firstname  TEXT,
    sort1      TEXT
);

CREATE TABLE IF NOT EXISTS bitacora_uso (
    id          SERIAL PRIMARY KEY,
    computer_id TEXT,
    matricula   BIGINT,
    evento      TEXT,
    timestamp   TIMESTAMP DEFAULT NOW()
);
```

**Step 2: Verificar sintaxis del archivo**

Revisar que el archivo tiene exactamente 3 bloques `CREATE TABLE IF NOT EXISTS`.

**Step 3: Commit**

```bash
git add docker/init.sql
git commit -m "feat: agregar script SQL de inicialización de tablas"
```

---

### Task 2: Crear `.env.example`

**Files:**
- Create: `.env.example`

**Step 1: Crear la plantilla de variables de entorno**

```env
# .env.example — Copia este archivo a .env y ajusta los valores

# Base de datos (usados por Flask)
DB_HOST=db
DB_NAME=basedatosuach
DB_USER=postgres
DB_PASSWORD=cambia-esto
DB_PORT=5432

# Variables nativas de la imagen postgres:16
POSTGRES_DB=basedatosuach
POSTGRES_USER=postgres
POSTGRES_PASSWORD=cambia-esto

# Flask
SECRET_KEY=cambia-esto-por-una-clave-larga-y-aleatoria

# Dashboard
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=cambia-esto
```

> Nota: `DB_HOST=db` apunta al nombre del servicio postgres dentro de la red de docker-compose.
> `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` deben coincidir con `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

**Step 2: Verificar que .env.example no está en .gitignore (no debe ignorarse, es una plantilla pública)**

Revisar `.gitignore` y asegurarse de que `.env` (sin example) sí esté ignorado pero `.env.example` no.

**Step 3: Commit**

```bash
git add .env.example
git commit -m "feat: agregar plantilla de variables de entorno"
```

---

### Task 3: Crear `Dockerfile`

**Files:**
- Create: `Dockerfile`

**Step 1: Escribir el Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias primero (aprovecha caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
```

**Step 2: Verificar que el Dockerfile no incluye la carpeta .venv**

Asegurarse de que existe un `.dockerignore` que excluya `.venv`, `__pycache__`, `*.pyc`, `docs/`, `.env`.

Si no existe, crear `.dockerignore`:

```
.venv
__pycache__
*.pyc
*.pyo
.env
docs/
.git
```

**Step 3: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: agregar Dockerfile python 3.12-slim"
```

---

### Task 4: Crear `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

**Step 1: Escribir el docker-compose**

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  web:
    build: .
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      db:
        condition: service_healthy

volumes:
  postgres_data:
```

> Nota: `depends_on` con `condition: service_healthy` garantiza que Flask no arranca hasta que PostgreSQL esté listo y aceptando conexiones.

**Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: agregar docker-compose con postgres 16 y flask"
```

---

### Task 5: Verificación manual

**Step 1: Copiar .env.example a .env y llenar los valores reales**

```bash
cp .env.example .env
# Editar .env con valores reales
```

**Step 2: Construir y levantar los contenedores**

```bash
docker compose up --build
```

Salida esperada:
- `db` levanta y corre `init.sql` (solo la primera vez)
- `web` espera a que `db` esté healthy antes de iniciar
- Flask imprime `Running on http://0.0.0.0:8000`

**Step 3: Verificar que las tablas existen**

```bash
docker compose exec db psql -U postgres -d basedatosuach -c "\dt"
```

Salida esperada: lista con `alumnos`, `bitacora_uso`, `computadoras`.

**Step 4: Verificar el servidor Flask**

```bash
curl http://localhost:8000/login
```

Esperado: respuesta HTTP 200 con el HTML del formulario de login.

**Step 5: Detener los contenedores**

```bash
docker compose down
```

---

### Orden de ejecución

1. Task 1 — `docker/init.sql`
2. Task 2 — `.env.example`
3. Task 3 — `Dockerfile` + `.dockerignore`
4. Task 4 — `docker-compose.yml`
5. Task 5 — Verificación manual
