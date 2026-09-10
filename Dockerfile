FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Jakarta

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 curl tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --system --uid 10001 joderma \
 && mkdir -p /app/data /app/private_media /app/logs /app/staticfiles /app/backups \
 && chown -R joderma:joderma /app

USER joderma

RUN python manage.py collectstatic --noinput

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health/ || exit 1

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn -c gunicorn.conf.py config.wsgi:application"]
