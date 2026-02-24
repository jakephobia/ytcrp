# Immagine con Python + ffmpeg per Render (o altro hosting Docker)
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render imposta la variabile PORT
ENV PORT=5000
EXPOSE 5000

# Gunicorn per produzione; bind su 0.0.0.0 e porta da env
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300 app:app
