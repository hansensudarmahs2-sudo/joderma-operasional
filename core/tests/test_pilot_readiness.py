"""Test perintah pilot_check dan konfigurasi port lewat environment."""
from __future__ import annotations

import io

import pytest
from django.core.management import call_command

from accounts.models import Role, User, UserRole
from checklists.models import ChecklistTemplate
from nurses.models import NurseEligibility

pytestmark = pytest.mark.django_db


def _run(**kwargs) -> str:
    out = io.StringIO()
    call_command("pilot_check", stdout=out, stderr=out, **kwargs)
    return out.getvalue()


def _all_templates(clinic):
    """Keempat area PRD 8.2 harus punya template aktif agar tidak jadi blocker."""
    from checklists.models import ChecklistArea, ChecklistTemplateItem

    for area, label in ChecklistArea.choices:
        tpl, created = ChecklistTemplate.objects.get_or_create(
            clinic=clinic, area=area, version=1, defaults={"name": label, "active": True}
        )
        if created:
            ChecklistTemplateItem.objects.create(
                template=tpl, label=f"Item {label}", required=True, sort_order=1
            )
    return ChecklistTemplate.objects.filter(clinic=clinic)


def test_reports_no_blocker_when_data_ready(
    clinic, template, supervisor, kasir, kasir2, perawat, kategori, eligible_nurses
):
    _all_templates(clinic)
    output = _run()
    assert "Tidak ada blocker" in output
    assert "Klinik aktif" in output


def test_detects_missing_supervisor(clinic, template, kasir, perawat, kategori, eligible_nurses):
    output = _run()
    assert "Supervisor" in output
    assert "BLOCKER" in output


def test_detects_inactive_template(
    clinic, template, supervisor, kasir, kasir2, perawat, kategori, eligible_nurses
):
    ChecklistTemplate.objects.filter(pk=template.pk).update(active=False)
    output = _run()
    assert "Template checklist area" in output
    assert "BLOCKER" in output


def test_detects_category_without_eligible_nurse(
    clinic, template, supervisor, kasir, kasir2, perawat, kategori
):
    """Kategori tanpa perawat eligible memaksa override supervisor tiap penugasan."""
    NurseEligibility.objects.all().delete()
    output = _run()
    assert "eligible" in output.lower()
    assert "BLOCKER" in output


def test_detects_demo_password(clinic, template, supervisor, kasir, kasir2, perawat, kategori, eligible_nurses):
    demo = User.objects.create_user(username="demo_user", password="JoDermaDemo2026!")
    UserRole.objects.create(user=demo, clinic=clinic, role=Role.STAF)
    output = _run()
    assert "password demo" in output
    assert "demo_user" in output


def test_strict_mode_exits_nonzero_on_blocker(clinic, kasir):
    with pytest.raises(SystemExit):
        _run(strict=True)


def test_command_is_read_only(
    clinic, template, supervisor, kasir, kasir2, perawat, kategori, eligible_nurses
):
    """pilot_check tidak boleh mengubah data apa pun."""
    from core.models import OperationalDay
    from audit.models import AuditEvent

    before_users = User.objects.count()
    before_days = OperationalDay.objects.count()
    before_audit = AuditEvent.objects.count()

    _run()

    assert User.objects.count() == before_users
    assert OperationalDay.objects.count() == before_days
    assert AuditEvent.objects.count() == before_audit


def test_backup_script_includes_source_code():
    """Data tanpa aplikasinya tidak cukup untuk memulihkan layanan.

    Basis data SQLite tidak berguna bila kode yang membacanya ikut hilang,
    dan prosedur pemulihan ada di dalam dokumentasi yang sama.
    """
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent.parent
    backup = (repo / "scripts" / "backup.sh").read_text(encoding="utf-8")

    assert "source.tar.gz" in backup, "backup tidak menyertakan kode dan dokumentasi"
    assert "ls-files" in backup, (
        "backup sebaiknya memakai daftar berkas Git agar rahasia tidak ikut"
    )
    assert "source_included=" in backup, "manifest tidak mencatat status penyertaan kode"

    restore = (repo / "scripts" / "restore.sh").read_text(encoding="utf-8")
    assert "source.tar.gz" in restore, "restore tidak memulihkan kode"


def test_backup_never_includes_secrets():
    """Berkas rahasia tidak boleh masuk arsip, bahkan pada jalur cadangan."""
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent.parent
    backup = (repo / "scripts" / "backup.sh").read_text(encoding="utf-8")

    fallback = backup.split('if [ "$CODE_INCLUDED" = "no" ]')[1].split("\nfi")[0]
    for rahasia in (".env", "data", "private_media", "backups", "logs"):
        assert f"--exclude='{rahasia}'" in fallback, (
            f"jalur cadangan backup tidak mengecualikan {rahasia}"
        )


def test_gunicorn_bind_follows_app_port_env(monkeypatch):
    """Port pilot harus dapat diubah lewat environment, bukan hardcode."""
    import importlib
    import sys

    monkeypatch.setenv("APP_PORT", "8731")
    monkeypatch.delenv("GUNICORN_BIND", raising=False)
    sys.modules.pop("gunicorn_conf_probe", None)

    import pathlib

    source = pathlib.Path(__file__).resolve().parents[2] / "gunicorn.conf.py"
    namespace: dict = {}
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    assert namespace["bind"] == "127.0.0.1:8731"

    monkeypatch.setenv("APP_PORT", "9001")
    namespace2: dict = {}
    exec(compile(source.read_text(), str(source), "exec"), namespace2)
    assert namespace2["bind"] == "127.0.0.1:9001"


def test_gunicorn_never_binds_wildcard_by_default(monkeypatch):
    import pathlib

    monkeypatch.delenv("GUNICORN_BIND", raising=False)
    monkeypatch.delenv("APP_HOST", raising=False)
    source = pathlib.Path(__file__).resolve().parents[2] / "gunicorn.conf.py"
    namespace: dict = {}
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    assert namespace["bind"].startswith("127.0.0.1:")


# --- Regresi deployment Docker (ditemukan saat migrasi ke mini-PC klinik) ---

def _compose() -> str:
    import pathlib

    return (pathlib.Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()


def _dockerfile() -> str:
    import pathlib

    return (pathlib.Path(__file__).resolve().parents[2] / "Dockerfile").read_text()


def test_compose_publishes_port_only_on_loopback():
    """Port publishing WAJIB diawali 127.0.0.1 — inilah yang mencegah akses LAN."""
    text = _compose()
    assert '"127.0.0.1:${APP_PORT:-8731}:${APP_PORT:-8731}"' in text
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and ":8731" in stripped and "/app" not in stripped:
            assert stripped.startswith('- "127.0.0.1:'), f"port publishing tanpa loopback: {stripped}"


def test_compose_sets_container_bind_to_all_interfaces():
    """Di DALAM container Gunicorn harus bind 0.0.0.0.

    Dengan 127.0.0.1 di dalam container, docker-proxy tidak dapat meneruskan
    koneksi dan health check host gagal ('connection reset by peer').
    """
    assert "APP_HOST: 0.0.0.0" in _compose()


def test_dockerfile_uid_is_configurable():
    """UID container harus dapat disamakan dengan pemilik direktori bind-mount.

    UID tetap (mis. 10001) membuat container gagal menulis logs/ dan data/
    di host, lalu restart terus-menerus.
    """
    text = _dockerfile()
    assert "ARG APP_UID=1000" in text
    assert "ARG APP_GID=1000" in text
    assert "USER ${APP_UID}:${APP_GID}" in text
    assert "--uid 10001" not in text


def test_compose_passes_uid_to_both_services():
    text = _compose()
    assert text.count("APP_UID: ${APP_UID:-1000}") == 2
    assert text.count("APP_GID: ${APP_GID:-1000}") == 2
