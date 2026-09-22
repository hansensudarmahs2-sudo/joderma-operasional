"""Navigasi utama mengikuti fungsi kerja, bukan hanya status login."""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole

pytestmark = pytest.mark.django_db


def _role_user(clinic, username, *roles):
    user = User.objects.create_user(username=username, password="TestPassword123!")
    for role in roles:
        UserRole.objects.create(user=user, clinic=clinic, role=role)
    return user


@pytest.mark.parametrize(
    ("username", "roles", "visible", "hidden"),
    [
        (
            "nav_kasir",
            (Role.FRONT_DESK, Role.STAF),
            ("Kas",),
            ("Giliran Perawat",),
        ),
        (
            "nav_perawat",
            (Role.PERAWAT, Role.STAF),
            ("Giliran Perawat",),
            ("Kas",),
        ),
        (
            "nav_apoteker",
            (Role.APOTEKER, Role.STAF),
            ("Checklist Saya", "Order Produk Online"),
            ("Kas", "Giliran Perawat"),
        ),
        (
            "nav_online",
            (Role.ONLINE, Role.STAF),
            ("Order Produk Online", "Checklist Saya"),
            ("Kas", "Giliran Perawat"),
        ),
    ],
)
def test_role_navigation_is_scoped(client, clinic, username, roles, visible, hidden):
    user = _role_user(clinic, username, *roles)
    assert client.login(username=user.username, password="TestPassword123!")

    response = client.get(reverse("core:dashboard"))
    body = response.content.decode()
    for label in visible:
        assert label in body
    for label in hidden:
        assert label not in body


def test_supervisor_sees_operational_coordination_menus(client, supervisor):
    assert client.login(username=supervisor.username, password="TestPassword123!")
    body = client.get(reverse("core:dashboard")).content.decode()
    for label in ("Kas", "Order Produk Online", "Giliran Perawat", "Laporan Operasional"):
        assert label in body
    assert "Antrean & Reservasi" not in body
