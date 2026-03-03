# Proyecto-biblioteca

Este proyecto es para monitoreo de computadoras se basa en

**Servidor:**


<img width="542" height="366" alt="Image" src="https://github.com/user-attachments/assets/24a02015-0b24-403c-b474-042c72f78306" />


**cliente:**

El cliente es solamente usado en las nodos(hijos), utiliza tkinter y se necesita cambiar la ip del servidor para funcionar correctamente.

Las librerias estan en requirements.txt

lenguaje usado: Python 3.12 en adelante

---

## Ejecutar con Docker

### Requisitos previos

- [Docker](https://docs.docker.com/get-docker/) instalado
- [Docker Compose](https://docs.docker.com/compose/install/) instalado (viene incluido en Docker Desktop)

### Pasos

1. Clona el repositorio y entra a la carpeta del servidor:

   ```bash
   git clone https://github.com/emilianopime/Proyecto-biblioteca.git
   cd Proyecto-biblioteca/SERVIDOR-V2
   ```

2. Construye e inicia todos los servicios (base de datos + servidor web):

   ```bash
   docker compose up --build
   ```

   > La primera vez descargará la imagen de PostgreSQL y construirá la imagen de Flask. Las ejecuciones siguientes son más rápidas.

3. Abre el navegador en [http://localhost:8000](http://localhost:8000).

4. Inicia sesión con las credenciales por defecto:
   - **Usuario:** `admin`
   - **Contraseña:** `1234`

Para detener los contenedores presiona `Ctrl+C` o ejecuta:

```bash
docker compose down
```

### Variables de entorno

Las variables de entorno se configuran directamente en `docker-compose.yml`. Los valores por defecto son:

| Variable            | Valor por defecto         | Descripción                          |
|---------------------|---------------------------|--------------------------------------|
| `FLASK_SECRET_KEY`  | `tu_clave_secreta_generada` | Clave secreta de sesión de Flask   |
| `DASHBOARD_USER`    | `admin`                   | Usuario del panel de administración  |
| `DASHBOARD_PASSWORD`| `1234`                    | Contraseña del panel                 |
| `DB_HOST`           | `db`                      | Nombre del servicio de base de datos |
| `DB_NAME`           | `basedatosuach`           | Nombre de la base de datos           |
| `DB_USER`           | `postgres`                | Usuario de PostgreSQL                |
| `DB_PASSWORD`       | `1234`                    | Contraseña de PostgreSQL             |
| `DB_PORT`           | `5432`                    | Puerto de PostgreSQL                 |

> **Recomendación de seguridad:** Cambia `FLASK_SECRET_KEY` y `DASHBOARD_PASSWORD` antes de desplegar en producción.
