"""Konfigurasi Gunicorn: HANYA listen di localhost (PRD 15.1).

Tailscale Serve yang bertindak sebagai reverse proxy HTTPS privat.
Tidak boleh mengganti bind host ke 0.0.0.0 — itu membuka aplikasi ke LAN.

Port berasal dari environment (APP_PORT), bukan hardcode, sehingga host yang
port 8000-nya sudah terpakai layanan lain dapat memakai port lain tanpa
mengubah kode. Default 8731 dipakai untuk pilot.
"""
import multiprocessing
import os

APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = os.environ.get("APP_PORT", "8731")

bind = os.environ.get("GUNICORN_BIND", f"{APP_HOST}:{APP_PORT}")
workers = int(os.environ.get("GUNICORN_WORKERS", min(4, multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
access_log_format = '%({X-Correlation-ID}o)s %(h)s "%(r)s" %(s)s %(b)s %(M)sms'
forwarded_allow_ips = "127.0.0.1"
