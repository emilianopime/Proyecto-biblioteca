FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias primero (aprovecha caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
