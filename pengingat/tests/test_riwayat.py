"""Riwayat Pengingat Harian DO: saringan, CSV, dan akses baca untuk Owner (kebutuhan 3.4)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import Clinic
from pengingat.models import Diingatkan, Materi

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur", name="JoDerma Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def citra(db):
    return Clinic.objects.create(code="JC", name="JoDerma Citraland", open_time="14:00", close_time="22:00")


@pytest.fixture
def do(jemur):
    return _user(jemur, "hansen1", Role.AOM)


@pytest.fixture
def logs(do, jemur, citra):
    sp, ar = Materi.objects.get(kode="SP-01"), Materi.objects.get(kode="AR-07")
    return [
        Diingatkan.objects.create(materi=sp, tanggal=dt.date(2026, 10, 15), clinic=None, saluran="GRUP_WA",
                                  catatan="Grup pagi", oleh=do),
        Diingatkan.objects.create(materi=ar, tanggal=dt.date(2026, 10, 16), clinic=citra, saluran="BRIEFING",
                                  catatan="=HYPERLINK(1)", oleh=do),
        Diingatkan.objects.create(materi=ar, tanggal=dt.date(2026, 11, 2), clinic=jemur, saluran="LANGSUNG", oleh=do),
    ]


def _rows(body):
    tbody = body.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return tbody.count("<tr>")


def test_history_lists_and_filters(client, do, logs, jemur, citra):
    client.force_login(do)
    url = reverse("pengingat:riwayat")
    body = client.get(url).content.decode()
    assert _rows(body) == 3 and "Jemur dan Citraland" in body and "Grup pagi" in body
    assert _rows(client.get(url, {"materi": logs[1].materi_id}).content.decode()) == 2
    assert _rows(client.get(url, {"bulan": "2026-10"}).content.decode()) == 2
    # Saringan cabang memuat pengingat untuk kedua cabang.
    body = client.get(url, {"cabang": citra.pk}).content.decode()
    assert _rows(body) == 2 and "Termasuk pengingat yang dikirim untuk kedua cabang" in body
    assert _rows(client.get(url, {"cabang": jemur.pk, "bulan": "2026-11"}).content.decode()) == 1
    assert _rows(client.get(url, {"materi": "x", "bulan": "13-2026"}).content.decode()) == 3  # tak dikenal diabaikan


def test_csv_export(client, do, logs):
    client.force_login(do)
    res = client.get(reverse("pengingat:riwayat"), {"bulan": "2026-10", "unduh": "csv"})
    assert res["Content-Type"].startswith("text/csv")
    assert 'filename="riwayat-pengingat-2026-10.csv"' in res["Content-Disposition"]
    text = res.content.decode("utf-8")
    assert text.startswith("﻿Tanggal,Kode,Materi,Cabang,Saluran,Catatan,Oleh")
    lines = text.strip().splitlines()
    assert len(lines) == 3 and "2026-10-16,AR-07" in lines[1] and "Citraland" in lines[1]
    assert "'=HYPERLINK(1)" in lines[1]  # sel rumus dinetralkan
    ev = AuditEvent.objects.get(action=AuditAction.EXPORT, entity_type="pengingat.riwayat")
    assert ev.after_json["baris"] == 2 and ev.after_json["bulan"] == "2026-10"


def test_owner_reads_history_but_not_catalog(client, jemur, logs):
    owner = _user(jemur, "yohanes", Role.OWNER)
    client.force_login(owner)
    body = client.get(reverse("pengingat:riwayat")).content.decode()
    assert _rows(body) == 3 and "Riwayat pengingat" in body
    assert reverse("pengingat:materi_ubah", args=[logs[0].materi_id]) not in body  # tanpa tautan ubah
    assert client.get(reverse("pengingat:riwayat"), {"unduh": "csv"}).status_code == 200
    assert client.post(reverse("pengingat:riwayat")).status_code == 403
    assert client.get(reverse("pengingat:katalog")).status_code == 403
    # Tab kelompok Kebijakan untuk Owner: tanpa Katalog.
    bar = body.split('class="subnav"', 1)[1].split("</nav>", 1)[0]
    assert "Riwayat pengingat" in bar and ">Pengingat<" not in bar


@pytest.mark.parametrize("roles", [(Role.STAF,), (Role.PIC, Role.FRONT_DESK), (Role.SUPERVISOR,)])
def test_history_forbidden_for_staff(client, jemur, logs, roles):
    client.force_login(_user(jemur, "orang", *roles))
    assert client.get(reverse("pengingat:riwayat")).status_code == 403
    assert client.get(reverse("pengingat:riwayat"), {"unduh": "csv"}).status_code == 403
