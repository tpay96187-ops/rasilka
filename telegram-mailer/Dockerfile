FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/sessions /app/reports && \
    chmod +x entrypoint.sh

ENV PYTHONPATH=/app

ENTRYPOINT ["./entrypoint.sh"]
