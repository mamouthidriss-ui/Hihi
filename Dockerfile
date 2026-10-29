FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV ENGINE=mock
# 1 seul worker : la file d'attente et les jobs sont en mémoire
CMD gunicorn app:app -b 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 300
