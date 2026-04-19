FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Build from `edge/` directory: docker build -f docker/Dockerfile .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py", "--config", "config.yaml", "--synthetic", "--mqtt-offline-only", "--max-frames", "1"]
