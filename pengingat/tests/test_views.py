"""Kartu Pengingat hari ini di Ringkasan Direktur dan izinnya (kebutuhan bagian 2 dan 3.1)."""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic, local_today
from pengingat import services as sv
from pengingat.models import Butir, Diingatkan, Kartu, Pengaturan, Status

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
def do(jemur):
    return _user(jemur, "hansen1", Role.AOM)


@pytest.fixture
def setiap_hari(db):
    """Semua hari dianggap hari kerja, supaya test tidak bergantung pada hari dijalankan."""
    cfg = Pengaturan.get()
    cfg.hari_kerja = list(range(7))
    cfg.save()
    return cfg


@pytest.fixture
def butir(setiap_hari):
    return sv.kartu_untuk(local_today()).butir.first()


def test_overview_shows_card_for_director(client, do, setiap_hari):
    client.force_login(do)
    body = client.get(reverse("direktur:overview")).content.decode()
    assert 'id="pengingat"' in body and "Pengingat hari ini" in body
    assert "SP-01" in body and "Salin teks WA" in body and "7 hari ke depan (perkiraan)" in body
    assert "{cabang}" not in body  # SP-01 untuk kedua cabang: placeholder dihapus
    assert body.index('id="pengingat"') < body.index("Yang belum selesai")
    assert Kartu.objects.filter(tanggal=local_today()).count() == 1


def test_owner_and_staff_do_not_get_card(client, jemur, setiap_hari):
    owner = _user(jemur, "yohanes", Role.OWNER)
    client.force_login(owner)
    assert 'id="pengingat"' not in client.get(reverse("owner:dashboard")).content.decode()
    assert not Kartu.objects.exists()


@pytest.mark.parametrize("roles", [(Role.STAF,), (Role.PIC, Role.FRONT_DESK), (Role.OWNER,), (Role.SUPERVISOR,)])
def test_non_director_forbidden_on_all_urls(client, jemur, butir, roles):
    client.force_login(_user(jemur, "orang", *roles))
    for name in ("diingatkan", "tunda", "lewati"):
        url = reverse(f"pengingat:{name}", args=[butir.pk])
        assert client.post(url, {"cabang": "keduanya", "saluran": "GRUP_WA", "alasan": "x"}).status_code == 403
        assert client.get(url).status_code == 403
    assert Butir.objects.get(pk=butir.pk).status == Status.TERBUKA and not Diingatkan.objects.exists()


def test_director_marks_reminded(client, do, butir):
    client.force_login(do)
    res = client.post(reverse("pengingat:diingatkan", args=[butir.pk]),
                      {"cabang": "keduanya", "saluran": "BRIEFING", "catatan": "pagi"})
    assert res.status_code == 302 and res["Location"].endswith("#pengingat")
    log = Diingatkan.objects.get()
    assert log.oleh == do and log.clinic is None and log.saluran == "BRIEFING"
    body = client.get(reverse("direktur:overview")).content.decode()
    assert "Sudah diingatkan</span> " + butir.materi.kode in body


def test_director_tunda_and_lewati(client, do, setiap_hari):
    kartu = sv.kartu_untuk(local_today())
    first, second = list(kartu.butir.all())[:2]
    client.force_login(do)
    client.post(reverse("pengingat:tunda", args=[first.pk]))
    assert Butir.objects.get(pk=first.pk).status == Status.DITUNDA
    res = client.post(reverse("pengingat:lewati", args=[second.pk]), {"alasan": ""}, follow=True)
    assert "Tulis alasan melewati" in res.content.decode()
    client.post(reverse("pengingat:lewati", args=[second.pk]), {"alasan": "Sedang direvisi"})
    assert Butir.objects.get(pk=second.pk).status == Status.DILEWATI


def test_bad_channel_rejected(client, do, butir):
    client.force_login(do)
    res = client.post(reverse("pengingat:diingatkan", args=[butir.pk]),
                      {"cabang": "keduanya", "saluran": "SMS"}, follow=True)
    assert "Pilih saluran" in res.content.decode() and not Diingatkan.objects.exists()


def test_holiday_card_message(client, do):
    cfg = Pengaturan.get()
    cfg.hari_kerja = []
    cfg.save()
    client.force_login(do)
    body = client.get(reverse("direktur:overview")).content.decode()
    assert "bukan hari kerja" in body and not Kartu.objects.exists()
