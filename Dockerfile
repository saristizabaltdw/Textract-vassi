FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instalar dependencias primero (mejor cache de capas)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copiar código y configuración
COPY *.py ./
COPY *.yaml ./

# Comando por defecto: ejecuta el flujo completo
CMD ["python", "run.py"]
