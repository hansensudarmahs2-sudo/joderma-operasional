"""Fase 5: halaman HTML laporan/masukan di atas service layer (plan 13 Fase 5, 14).

Melengkapi endpoint JSON Fase 4 dengan UI yang dapat dipakai tanpa Django
admin, dengan filter status eksplisit (data selesai/arsip tetap tersedia)
dan pemeriksaan akses server-side yang sama seperti endpoint JSON.
"""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from reports.models import ReportStatus, ReportVisibility
from reports.services import archive_laporan, archive_masukan, create_laporan, create_masukan

pytestmark = pytest.mark.django_db


@pytest.fixture
def aom_user(clinic):
    user = User.objects.create_user(username="aom_page", password="TestPassword123!")
    UserRole.objects.create(user=user, clinic=clinic, role=Role.AOM)
    return user


def test_laporan_page_lists_cabang_report(client, clinic, staf):
    create_laporan(clinic=clinic, user=staf, title="Umum satu cabang", visibility=ReportVisibility.CABANG)
    client.login(username="staf", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_page"))
    assert response.status_code == 200
    assert "Umum satu cabang" in response.content.decode()


def test_laporan_page_direct_detail_blocked_for_other_staf(client, clinic, staf):
    laporan = create_laporan(
        clinic=clinic, user=staf, title="Rahasia halaman", visibility=ReportVisibility.RAHASIA_AOM
    )
    other = User.objects.create_user(username="other_page_staf", password="TestPassword123!")
    UserRole.objects.create(user=other, clinic=clinic, role=Role.STAF)

    client.login(username="other_page_staf", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_page_detail", args=[laporan.pk]))
    assert response.status_code == 403


def test_laporan_page_archived_report_reachable_via_status_filter(client, clinic, staf, aom_user):
    laporan = create_laporan(clinic=clinic, user=staf, title="Akan diarsipkan")
    archive_laporan(laporan, user=aom_user, reason="Sudah tidak relevan.")

    client.login(username="staf", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_page"), {"status": ReportStatus.ARCHIVED})
    assert response.status_code == 200
    assert "Akan diarsipkan" in response.content.decode()


def test_laporan_page_create_via_form(client, clinic, staf):
    client.login(username="staf", password="TestPassword123!")
    response = client.post(
        reverse("reports:laporan_page"),
        {"title": "Dari form UI", "description": "isi", "visibility": "CABANG"},
    )
    assert response.status_code == 302
    from reports.models import Laporan

    assert Laporan.objects.filter(title="Dari form UI").exists()


def test_masukan_page_lists_own_masukan(client, clinic, staf):
    create_masukan(clinic=clinic, user=staf, title="Usul jam UI")
    client.login(username="staf", password="TestPassword123!")
    response = client.get(reverse("reports:masukan_page"))
    assert response.status_code == 200
    assert "Usul jam UI" in response.content.decode()


def test_masukan_page_direct_detail_blocked_for_other_staf(client, clinic, staf):
    masukan = create_masukan(clinic=clinic, user=staf, title="Privat halaman")
    other = User.objects.create_user(username="other_page_staf2", password="TestPassword123!")
    UserRole.objects.create(user=other, clinic=clinic, role=Role.STAF)

    client.login(username="other_page_staf2", password="TestPassword123!")
    response = client.get(reverse("reports:masukan_page_detail", args=[masukan.pk]))
    assert response.status_code == 403


def test_masukan_page_archived_reachable_via_status_filter(client, clinic, staf, aom_user):
    masukan = create_masukan(clinic=clinic, user=staf, title="Masukan diarsipkan")
    archive_masukan(masukan, user=aom_user, reason="Sudah diterapkan.")

    client.login(username="staf", password="TestPassword123!")
    response = client.get(reverse("reports:masukan_page"), {"status": "archived"})
    assert response.status_code == 200
    assert "Masukan diarsipkan" in response.content.decode()

    response_active = client.get(reverse("reports:masukan_page"), {"status": "active"})
    assert "Masukan diarsipkan" not in response_active.content.decode()


def test_masukan_page_publish_rejects_non_aom_direct_post(client, clinic, staf):
    masukan = create_masukan(clinic=clinic, user=staf, title="Coba publikasi paksa")
    client.login(username="staf", password="TestPassword123!")
    response = client.post(
        reverse("reports:masukan_page_detail", args=[masukan.pk]),
        {"aksi": "publikasi", "clinics": [clinic.pk]},
    )
    # publish_masukan melempar PermissionDenied -> redirect dengan pesan error,
    # tapi publikasi TIDAK boleh tercipta untuk non-AOM.
    masukan.refresh_from_db()
    assert masukan.is_published is False


def test_unauthenticated_cannot_view_laporan_page(client, clinic, staf):
    create_laporan(clinic=clinic, user=staf, title="Tanpa login")
    response = client.get(reverse("reports:laporan_page"))
    assert response.status_code == 302
