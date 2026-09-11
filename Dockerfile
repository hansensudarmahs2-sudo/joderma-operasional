FROM python:3.12-slim

ARG APP_PORT=8731
# UID/GID harus cocok dengan pemilik direktori bind-mount di host, jika tidak
# container tidak dapat menulis ke data/, logs/, private_media/, dan backups/.
# Host Linux umumnya memakai 1000 untuk user pertama.
ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Jakarta \
    APP_PORT=${APP_PORT}

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd --gid ${APP_GID} joderma 2>/dev/null || true \
 && useradd --uid ${APP_UID} --gid ${APP_GID} --no-create-home joderma 2>/dev/null || true \
 && mkdir -p /app/data /app/private_media /app/logs /app/staticfiles /app/backups \
 && chown -R ${APP_UID}:${APP_GID} /app

USER ${APP_UID}:${APP_GID}

RUN python manage.py collectstatic --noinput

EXPOSE ${APP_PORT}
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${APP_PORT}/health/" || exit 1

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn -c gunicorn.conf.py config.wsgi:application"]
