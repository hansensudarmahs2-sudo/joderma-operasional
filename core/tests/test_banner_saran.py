"""Banner saran lembut: password awal dan izin lokasi (3 Okt 2026). Tidak memaksa."""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from accounts.peran_standar import DEFAULT_PASSWORD
from core.models import Clinic
from jejak.models import KnownDevice

pytestmark = pytest.mark.django_db


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


def _user(clinic, name, password, *roles):
    u = User.objects.create_user(username=name, password=password, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _login(client, name, password):
    return client.post(reverse("accounts:login"), {"username": name, "password": password})


def test_password_banner_for_default_password(client, jemur):
    _user(jemur, "silvi", DEFAULT_PASSWORD, Role.PERAWAT, Role.STAF)
    _login(client, "silvi", DEFAULT_PASSWORD)
    body = client.get(reverse("core:dashboard")).content.decode()
    assert 'data-banner="sandi"' in body and "masih memakai password awal" in body and "Ganti sekarang" in body
    assert 'data-banner="lokasi"' not in body  # satu banner saja, password didahulukan
    page = client.get(reverse("accounts:change_password")).content.decode()
    assert 'data-banner="sandi"' not in page
    client.post(reverse("accounts:change_password"), {
        "current_password": DEFAULT_PASSWORD, "new_password": "SilviBaru#2026", "confirm_password": "SilviBaru#2026"})
    assert not User.objects.get(username="silvi").check_password(DEFAULT_PASSWORD)
    body = client.get(reverse("core:dashboard")).content.decode()
    assert 'data-banner="sandi"' not in body and 'data-banner="lokasi"' in body


def test_location_banner_and_exclusions(client, jemur):
    staff = _user(jemur, "ayu", "RahasiaKuat#1", Role.APOTEKER, Role.STAF)
    _login(client, "ayu", "RahasiaKuat#1")
    body = client.get(reverse("core:dashboard")).content.decode()
    assert 'data-banner="lokasi"' in body and "Izinkan lokasi agar checklist" in body and "Tidak wajib" in body
    assert "Pengaturan → Safari → Lokasi" in body  # petunjuk bila izin sudah ditolak
    # Perangkat klinik terdaftar: tidak perlu ajakan lokasi.
    KnownDevice.objects.create(ip_address="100.90.94.23", name="PC Jemur", clinic=jemur, is_clinic_device=True)
    body = client.get(reverse("core:dashboard"), HTTP_X_FORWARDED_FOR="100.90.94.23").content.decode()
    assert 'data-banner="lokasi"' not in body
    # Owner tidak diajak.
    client.logout()
    _user(jemur, "jean", "OwnerKuat#1", Role.OWNER)
    _login(client, "jean", "OwnerKuat#1")
    assert 'data-banner=' not in client.get(reverse("owner:dashboard")).content.decode()


def test_existing_session_is_checked_once(client, jemur):
    u = _user(jemur, "nanda", DEFAULT_PASSWORD, Role.STAF)
    client.force_login(u)  # sesi lama: belum ada penanda dari login
    assert 'data-banner="sandi"' in client.get(reverse("core:dashboard")).content.decode()
    assert client.session["sandi_awal"] is True
