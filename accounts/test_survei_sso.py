"""13 Okt 2026: aplikasi Survei di /survei memakai login ops lewat /akun/sesi-survei/, dan menu Survei."""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from accounts.survei import survey_role
from core.models import Clinic

pytestmark = pytest.mark.django_db
URL = "/akun/sesi-survei/"


def _user(clinic, name, *roles, active=True):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title(),
                                 is_active=active)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


def test_url_is_stable_for_survey_app():
    assert reverse("accounts:survey_session") == URL


def test_anonymous_gets_401_with_login_url_not_redirect(client):
    resp = client.get(URL)
    assert resp.status_code == 401 and resp["Cache-Control"] == "no-store"
    assert resp.json() == {"masuk": "/akun/login/?next=/survei/"}


@pytest.mark.parametrize("roles, expected", [
    ((Role.AOM,), "direktur"),
    ((Role.OWNER,), "owner"),
    ((Role.ONLINE, Role.STAF), "cs"),
    ((Role.OWNER, Role.AOM), "direktur"),  # peran tertinggi
    ((Role.ONLINE, Role.OWNER), "owner"),
])
def test_roles_map_to_survey_roles(client, jemur, roles, expected):
    u = _user(jemur, "orang", *roles)
    client.force_login(u)
    resp = client.get(URL)
    assert resp.status_code == 200 and resp["Cache-Control"] == "no-store"
    assert resp.json() == {"username": "orang", "nama": "Orang", "peran": expected}


def test_staff_without_survey_role_gets_403(client, jemur):
    client.force_login(_user(jemur, "perawat", Role.PERAWAT, Role.STAF))
    resp = client.get(URL)
    assert resp.status_code == 403 and resp.json()["peran"] is None


def test_only_get_allowed(client, jemur):
    client.force_login(_user(jemur, "dir", Role.AOM))
    assert client.post(URL).status_code == 405


def test_inactive_user_has_no_survey_role(jemur):
    assert survey_role(_user(jemur, "lama", Role.AOM, active=False)) is None


def _nav(body: str) -> str:
    return body.split('id="main-nav"', 1)[1].split("</nav>", 1)[0]


def test_menu_shows_survei_only_for_survey_roles(client, jemur):
    pages = {
        "dir": ((Role.AOM,), "direktur:overview", True),
        "own": ((Role.OWNER,), "owner:dashboard", True),
        "cs": ((Role.ONLINE, Role.STAF), "core:today", True),
        "nurse": ((Role.PERAWAT, Role.STAF), "core:today", False),
    }
    for name, (roles, page, shown) in pages.items():
        client.force_login(_user(jemur, name, *roles))
        nav = _nav(client.get(reverse(page)).content.decode())
        assert ('href="/survei/"' in nav) is shown, name
