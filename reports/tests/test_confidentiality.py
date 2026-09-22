"""Fase 4: gate kebocoran laporan rahasia lewat URL langsung, list, dan akses lintas cabang.

Ini adalah gate paling kritis (plan 15/16): laporan RAHASIA_AOM tidak boleh
bocor via list, direct object access, atau service-layer queryset kepada
staf lain di cabang yang sama.
"""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from reports.models import ReportVisibility
from reports.services import create_laporan

pytestmark = pytest.mark.django_db


@pytest.fixture
def other_staf_same_clinic(clinic):
    return _create_staf(clinic)


def _create_staf(clinic):
    user = User.objects.create_user(username="other_staf", password="TestPassword123!")
    UserRole.objects.create(user=user, clinic=clinic, role=Role.STAF)
    return user


def test_confidential_report_direct_url_blocked_for_other_staf_same_clinic(
    client, clinic, staf, other_staf_same_clinic
):
    laporan = create_laporan(
        clinic=clinic, user=staf, title="Rahasia untuk AOM", visibility=ReportVisibility.RAHASIA_AOM
    )

    client.login(username="other_staf", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_detail", args=[laporan.pk]))
    assert response.status_code == 403


def test_confidential_report_not_in_list_for_other_staf_same_clinic(
    client, clinic, staf, other_staf_same_clinic
):
    create_laporan(clinic=clinic, user=staf, title="Rahasia untuk AOM", visibility=ReportVisibility.RAHASIA_AOM)

    client.login(username="other_staf", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_list"))
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_reporter_can_access_own_confidential_report(client, clinic, staf):
    laporan = create_laporan(
        clinic=clinic, user=staf, title="Rahasia untuk AOM", visibility=ReportVisibility.RAHASIA_AOM
    )
    client.login(username="staf", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_detail", args=[laporan.pk]))
    assert response.status_code == 200
    assert response.json()["id"] == laporan.pk


def test_aom_can_access_confidential_report_of_other_user(client, clinic, staf):
    aom_user = User.objects.create_user(username="aom_view", password="TestPassword123!")
    UserRole.objects.create(user=aom_user, clinic=clinic, role=Role.AOM)

    laporan = create_laporan(
        clinic=clinic, user=staf, title="Rahasia untuk AOM", visibility=ReportVisibility.RAHASIA_AOM
    )
    client.login(username="aom_view", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_detail", args=[laporan.pk]))
    assert response.status_code == 200


def test_cross_clinic_confidential_report_blocked(client, clinic, clinic_b, staf):
    laporan = create_laporan(
        clinic=clinic, user=staf, title="Rahasia cabang A", visibility=ReportVisibility.RAHASIA_AOM
    )
    other_b = User.objects.create_user(username="staf_b_cross", password="TestPassword123!")
    UserRole.objects.create(user=other_b, clinic=clinic_b, role=Role.STAF)

    client.login(username="staf_b_cross", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_detail", args=[laporan.pk]))
    assert response.status_code == 403


def test_cabang_report_from_other_clinic_not_visible(client, clinic, clinic_b, staf):
    """Laporan CABANG juga tidak boleh bocor lintas cabang meski tidak rahasia."""
    laporan = create_laporan(
        clinic=clinic, user=staf, title="Umum cabang A", visibility=ReportVisibility.CABANG
    )
    other_b = User.objects.create_user(username="staf_b_general", password="TestPassword123!")
    UserRole.objects.create(user=other_b, clinic=clinic_b, role=Role.STAF)

    client.login(username="staf_b_general", password="TestPassword123!")
    response = client.get(reverse("reports:laporan_detail", args=[laporan.pk]))
    assert response.status_code == 403


def test_unauthenticated_user_cannot_access_report_detail(client, clinic, staf):
    laporan = create_laporan(clinic=clinic, user=staf, title="Umum", visibility=ReportVisibility.CABANG)
    response = client.get(reverse("reports:laporan_detail", args=[laporan.pk]))
    assert response.status_code in (302, 403)  # login_required redirect, never leaks content
