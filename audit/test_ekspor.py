"""Ekspor audit ke CSV (permintaan product owner 3 Oktober 2026)."""
from __future__ import annotations

import csv
import io

import pytest
from django.urls import reverse

from accounts.models import Capability, Role, User, UserCapability, UserRole
from audit.models import AuditAction, AuditEvent
from audit.services import log_event
from core.models import Clinic

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def clinic(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


def _rows(response):
    body = b"".join(response.streaming_content).decode("utf-8")
    assert body.startswith("﻿")
    return list(csv.reader(io.StringIO(body.lstrip("﻿"))))


def test_director_exports_filtered_csv(client, clinic):
    hansen = _user(clinic, "hansen1", Role.AOM)
    regita = _user(clinic, "regita", Role.SUPERVISOR)
    log_event(action=AuditAction.CORRECTION, entity_type="nurseactiontally", entity_id=1,
              entity_label="JC-0108 Sculptra", actor=regita, before={"tally": 2}, after={"tally": 0},
              reason="Dobel input")
    log_event(action=AuditAction.UPDATE, entity_type="cashsession", entity_id=5, entity_label="Kas awal",
              actor=hansen, after={"note": "=HYPERLINK(\"x\")"})
    client.force_login(hansen)
    page = client.get(reverse("audit:log") + "?aktor=regita").content.decode()
    assert "Unduh CSV" in page and reverse("audit:export") + "?aktor=regita" in page
    response = client.get(reverse("audit:export") + "?aktor=regita")
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    assert 'filename="audit_semua_' in response["Content-Disposition"]
    rows = _rows(response)
    assert rows[0][:4] == ["Waktu (WIB)", "Pengguna", "Username", "Aksi"]
    data = [r for r in rows[1:] if r[4] == "CORRECTION"]
    assert len(data) == 1 and data[0][2] == "regita" and data[0][8] == "Dobel input"
    assert '"tally": 2' in data[0][9] and '"tally": 0' in data[0][10]
    assert not any(r[5] == "cashsession" for r in rows[1:])  # tersaring
    # Rumus spreadsheet dinetralkan.
    rows = _rows(client.get(reverse("audit:export") + "?entitas=cashsession"))
    assert rows[1][10].startswith("'") or rows[1][10].startswith('{')
    # Unduhan tercatat.
    assert AuditEvent.objects.filter(action=AuditAction.EXPORT, entity_type="audit", actor=hansen).count() == 2


def test_date_filter_and_filename(client, clinic):
    hansen = _user(clinic, "hansen1", Role.AOM)
    log_event(action=AuditAction.UPDATE, entity_type="issue", actor=hansen)
    client.force_login(hansen)
    from core.models import local_today

    today = local_today().isoformat()
    response = client.get(reverse("audit:export") + f"?dari={today}&sampai={today}")
    assert f'audit_{today}_{today}_' in response["Content-Disposition"]
    assert len(_rows(response)) >= 2
    assert len(_rows(client.get(reverse("audit:export") + "?dari=2000-01-01&sampai=2000-01-02"))) == 1


def test_who_can_export(client, clinic):
    heni = _user(clinic, "heni", Role.SUPERVISOR)
    yani = _user(clinic, "yani", Role.PERAWAT, Role.STAF)
    admin = _user(clinic, "superadmin", Role.ADMIN)
    UserCapability.objects.create(user=admin, capability=Capability.ADMIN_FULL_ACCESS)
    client.force_login(heni)
    assert client.get(reverse("audit:log")).status_code == 200
    assert "Unduh CSV" not in client.get(reverse("audit:log")).content.decode()
    assert client.get(reverse("audit:export")).status_code == 403
    client.force_login(yani)
    assert client.get(reverse("audit:export")).status_code == 403
    client.force_login(admin)
    assert client.get(reverse("audit:export")).status_code == 200


def test_pagination_keeps_filters(client, clinic):
    hansen = _user(clinic, "hansen1", Role.AOM)
    for i in range(60):
        log_event(action=AuditAction.UPDATE, entity_type="issue", entity_id=i, actor=hansen)
    client.force_login(hansen)
    page = client.get(reverse("audit:log") + "?entitas=issue").content.decode()
    assert "?entitas=issue&hal=2" in page
