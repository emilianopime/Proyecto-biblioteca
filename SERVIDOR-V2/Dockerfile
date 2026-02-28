FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# Instalamos  dependencias
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Exponemos el puerto 8000 que usa tu servidor Flask
EXPOSE 8000
RUN chmod 777 /app
# El comando que ejecutará el contenedor al iniciar
CMD ["python", "main.py"]