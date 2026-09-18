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

# Usuario invitado que se agrega al padrón en cada carga (opcional)
# Deja INVITADO_CARDNUMBER vacío para no agregar ninguno.
INVITADO_CARDNUMBER=10203
INVITADO_NOMBRE=Especial
INVITADO_APELLIDO=Invitado
INVITADO_CARRERA=Invitado
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

Desde el dashboard (`http://localhost:8000`), ve al módulo **Padrón**, elige o arrastra el archivo CSV que exporta el sistema de la biblioteca y confirma el reemplazo. Se puede subir tal cual: las columnas que no se usan se ignoran. La misma pantalla muestra cuántos alumnos tiene el padrón actual.

El servidor reconoce las columnas por nombre, sin importar mayúsculas, acentos ni paréntesis:

| Campo     | Encabezados aceptados                    | Obligatorio |
|-----------|------------------------------------------|-------------|
| Matrícula | `Carnet`, `cardnumber`, `matricula`      | Sí          |
| Apellido  | `Apellido(s)`, `apellido`, `surname`     | Sí          |
| Nombre    | `Nombre(s)`, `nombre`, `firstname`       | No          |
| Carrera   | `Carrera`, `sort1`, `profesion`          | No          |

Reglas de limpieza:

- Se aceptan archivos en UTF-8 (con o sin BOM) y en latin-1, separados por coma, punto y coma, tabulador o barra.
- Las filas cuya matrícula no sea un número se descartan. Si una matrícula se repite, se conserva la primera.
- Si no viene la columna de nombre pero el apellido trae la forma `Apellido, Nombre`, se separa por la coma.
- Si la carrera viene vacía o no existe la columna, se guarda `Sin Profesion`.
- Nombres, apellidos y carreras se guardan con la primera letra de cada palabra en mayúscula.
- Al final se agrega el usuario invitado definido en el `.env` (ver sección 1).

Si el archivo no trae matrícula o apellido, el dashboard muestra qué columna faltó y cuáles sí traía el archivo, y la base de datos no se toca. Si se pierde la conexión a media carga, el dashboard lo dice y ofrece reintentar. La carga reemplaza el padrón completo cada vez.

> Nota: el export de la biblioteca a veces trae nombre y apellido intercambiados en algunas filas. El servidor los guarda tal como vienen; el kiosko y el dashboard muestran siempre nombre y apellido juntos, así que solo cambia el orden en que se leen.

Para agregar otro encabezado aceptado, edita el diccionario `ALIAS` en `SERVIDOR-V2/padron.py`.

---

## 6. Reporte de uso por periodo

En **Estadísticas**, el bloque *Generar reporte* permite elegir el periodo (este mes, mes anterior, semestre actual o un rango de fechas) y obtener el mismo contenido en tres formas:

| Salida | Ruta | Uso |
|---|---|---|
| Página imprimible | `/reporte?periodo=...` | Se abre en el navegador; desde ahí se imprime o se guarda como PDF |
| PDF | `/reporte.pdf?periodo=...` | Descarga directa, generado con WeasyPrint |
| Excel | `/reporte.xlsx?periodo=...` | Una hoja por tabla: resumen, equipos, carreras, horas y días |

El reporte incluye entradas del periodo, alumnos distintos, días con actividad, promedio por día, equipos más usados, carreras con más uso, horas del día con más uso y entradas por día. Para un rango se pasan `desde` y `hasta` en formato `AAAA-MM-DD`. El semestre es enero-julio o agosto-diciembre, y la tarjeta "Este semestre" de Estadísticas usa el mismo criterio.

---

## Pruebas

Las pruebas de lectura del CSV corren sin base de datos. Las de carga y del endpoint necesitan un Postgres y se saltan si no se define `TEST_DB_DSN`.

```bash
cd SERVIDOR-V2
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest tests

# Con base de datos (Postgres desechable en Docker):
docker run -d --rm --name padron-test-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16
TEST_DB_DSN="host=localhost port=55432 user=postgres password=test dbname=postgres" .venv/bin/python -m pytest tests
docker stop padron-test-pg
```

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
