FROM python:3.12-slim

WORKDIR /app

# Librerias de sistema que necesita WeasyPrint para generar el PDF del reporte
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 \
        libgdk-pixbuf-2.0-0 libffi8 shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias primero para aprovechar la caché
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

EXPOSE 8000

# Comando original usando Werkzeug (Flask dev server)
CMD ["python", "main.py"]