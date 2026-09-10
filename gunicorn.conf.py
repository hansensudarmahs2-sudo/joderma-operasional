"""Konfigurasi Gunicorn: HANYA listen di localhost (PRD 15.1).

Tailscale Serve yang bertindak sebagai reverse proxy HTTPS privat.
Tidak boleh mengganti bind ke 0.0.0.0 — itu membuka aplikasi ke LAN.
"""
import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", min(4, multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
access_log_format = '%({X-Correlation-ID}o)s %(h)s "%(r)s" %(s)s %(b)s %(M)sms'
forwarded_allow_ips = "127.0.0.1"
