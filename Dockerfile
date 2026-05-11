FROM --platform=linux/amd64 python:3.11-slim

# Evitar que Python escriba archivos .pyc en el disco
ENV PYTHONDONTWRITEBYTECODE=1
# Evitar que Python almacene en búfer la salida estándar y de error
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero (aprovechar la caché de capas de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del bot
COPY . .

# Establecer main.py como el punto de entrada predeterminado
ENTRYPOINT ["python", "main.py"]

# Argumentos predeterminados (se pueden sobrescribir al hacer docker run)
CMD ["--days-ahead", "2", "--schedule", "schedule_9907.json"]
