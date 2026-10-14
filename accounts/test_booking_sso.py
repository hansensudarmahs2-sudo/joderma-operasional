"""14 Okt 2026: aplikasi CS Booking di /booking memakai login ops lewat /akun/sesi-booking/, dan menu Booking."""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.booking import booking_role
from accounts.models import Role, User, UserRole
from core.models import Clinic

pytestmark = pytest.mark.django_db
URL = "/akun/sesi-booking/"


def _user(clinic, name, *roles, active=True):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title(),
                                 is_active=active)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


def test_url_is_stable_for_booking_app():
    assert reverse("accounts:booking_session") == URL


def test_anonymous_gets_401_with_login_url_not_redirect(client):
    resp = client.get(URL)
    assert resp.status_code == 401 and resp["Cache-Control"] == "no-store"
    assert resp.json() == {"masuk": "/akun/login/?next=/booking/"}


@pytest.mark.parametrize("roles, expected", [
    ((Role.AOM,), "admin"),
    ((Role.OWNER,), "admin"),
    ((Role.ONLINE, Role.STAF), "cs"),
    ((Role.ONLINE, Role.AOM), "admin"),  # peran tertinggi
])
def test_roles_map_to_booking_roles(client, jemur, roles, expected):
    u = _user(jemur, "orang", *roles)
    client.force_login(u)
    resp = client.get(URL)
    assert resp.status_code == 200 and resp["Cache-Control"] == "no-store"
    assert resp.json() == {"username": "orang", "nama": "Orang", "peran": expected}


@pytest.mark.parametrize("roles", [
    (Role.PERAWAT, Role.STAF),
    (Role.FRONT_DESK, Role.STAF),
    (Role.ADMIN,),
    (Role.SUPERVISOR, Role.STAF),
])
def test_staff_without_booking_role_gets_403(client, jemur, roles):
    client.force_login(_user(jemur, "staf", *roles))
    resp = client.get(URL)
    assert resp.status_code == 403 and resp.json()["peran"] is None


def test_only_get_allowed(client, jemur):
    client.force_login(_user(jemur, "dir", Role.AOM))
    assert client.post(URL).status_code == 405


def test_inactive_user_has_no_booking_role(jemur):
    assert booking_role(_user(jemur, "lama", Role.AOM, active=False)) is None


def test_survey_session_unchanged(client, jemur):
    """Endpoint survei tetap seperti semula; booking tidak mengubah peran survei."""
    client.force_login(_user(jemur, "cs", Role.ONLINE, Role.STAF))
    assert client.get("/akun/sesi-survei/").json()["peran"] == "cs"


def _nav(body: str) -> str:
    return body.split('id="main-nav"', 1)[1].split("</nav>", 1)[0]


def test_menu_shows_booking_only_for_booking_roles(client, jemur):
    pages = {
        "dir": ((Role.AOM,), "direktur:overview", True),
        "own": ((Role.OWNER,), "owner:dashboard", True),
        "cs": ((Role.ONLINE, Role.STAF), "core:today", True),
        "nurse": ((Role.PERAWAT, Role.STAF), "core:today", False),
    }
    for name, (roles, page, shown) in pages.items():
        client.force_login(_user(jemur, name, *roles))
        nav = _nav(client.get(reverse(page)).content.decode())
        assert ('href="/booking/"' in nav) is shown, name
