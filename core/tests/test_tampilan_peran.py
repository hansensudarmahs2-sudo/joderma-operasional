"""Fase 3 redefinisi peran: menu per peran, halaman pertama, dan penolakan server-side.

Lihat `docs/KEBUTUHAN_REDEFINISI_PERAN.md` dan `core/peran.py`.
"""
from __future__ import annotations

import re

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from accounts.models import PicAssignment, PicFunction, Role, User, UserRole
from core import peran

pytestmark = pytest.mark.django_db

PASSWORD = "TestPassword123!"

# Menu yang TIDAK boleh ada pada Owner (keputusan 29 September 2026).
OWNER_FORBIDDEN_MENU = ("Hari Ini", "Checklist Saya", "Pembagian Tugas", "Audit", "Laporan Operasional",
                        "Laporan Saya", "Masukan Saya", "Pengaturan Klinik", "Kas", "Checklist Direktur")


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _nav(body: str) -> list[str]:
    nav = body.split('id="main-nav"', 1)[1].split("</nav>", 1)[0]
    return [re.sub(r"\s+", " ", t).strip() for t in re.findall(r"<a href=\"[^\"]*\"[^>]*>([^<]+)</a>", nav)]


def _all_routes():
    """Semua rute aplikasi (tanpa Django admin) dengan URL contoh."""
    out = []

    def walk(patterns, prefix="", ns=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern), p.namespace or ns)
            elif isinstance(p, URLPattern) and p.name:
                path = prefix + str(p.pattern)
                if path.startswith("django-admin"):
                    continue
                url = "/" + re.sub(r"<int:\w+>", "1", re.sub(r"<(str:)?\w+>", "x", path))
                out.append((f"{ns}:{p.name}", url))

    walk(get_resolver().url_patterns)
    return out


# --- Tampilan ----------------------------------------------------------------


def test_persona_from_roles(clinic):
    assert peran.persona(_user(clinic, "d", Role.AOM, Role.ADMIN)) == peran.DIREKTUR
    assert peran.persona(_user(clinic, "o", Role.OWNER)) == peran.OWNER
    assert peran.persona(_user(clinic, "k", Role.SUPERVISOR, Role.PERAWAT)) == peran.PIC
    assert peran.persona(_user(clinic, "p", Role.PIC, Role.FRONT_DESK)) == peran.PIC
    assert peran.persona(_user(clinic, "s", Role.PERAWAT, Role.STAF)) == peran.STAF
    assert peran.persona(_user(clinic, "a", Role.ADMIN)) == peran.ADMIN
    assert peran.persona(_user(clinic, "a2", Role.ADMIN, Role.FRONT_DESK)) == peran.STAF
    assert peran.persona(User.objects.create_superuser("root", password=PASSWORD)) == peran.ADMIN


@pytest.mark.parametrize(
    ("roles", "home"),
    [
        ((Role.OWNER,), "owner:dashboard"),
        ((Role.AOM,), "direktur:overview"),
        ((Role.PIC, Role.FRONT_DESK), "core:dashboard"),
        ((Role.PERAWAT, Role.STAF), "core:today"),
        ((Role.ADMIN,), "accounts:user_list"),
    ],
)
def test_login_lands_on_role_home(client, clinic, roles, home):
    _user(clinic, "u1", *roles)
    response = client.post(reverse("accounts:login"), {"username": "u1", "password": PASSWORD}, follow=True)
    assert response.redirect_chain[-1][0] == reverse(home)
    assert response.status_code == 200
    assert client.get(reverse("home"))["Location"] == reverse(home)


def test_login_ignores_external_next(client, clinic):
    _user(clinic, "u1", Role.STAF)
    response = client.post(reverse("accounts:login") + "?next=https://contoh.invalid/", {
        "username": "u1", "password": PASSWORD})
    assert response["Location"] == reverse("home")
    client.logout()
    response = client.post(reverse("accounts:login") + "?next=/jadwal/", {"username": "u1", "password": PASSWORD})
    assert response["Location"] == "/jadwal/"


def test_owner_menu_is_short(client, clinic):
    client.force_login(_user(clinic, "yohanes", Role.OWNER))
    body = client.get(reverse("owner:dashboard")).content.decode()
    menu = _nav(body)
    assert menu[:7] == ["Dashboard", "Inbox", "Task", "Evaluasi staf", "Kebijakan", "Summary Harian", "Jadwal"]
    for label in OWNER_FORBIDDEN_MENU:
        assert label not in menu
    assert "Owner / Direktur Utama" in body


def test_director_menu_keeps_everything(client, clinic):
    client.force_login(_user(clinic, "hansen1", Role.AOM))
    menu = _nav(client.get(reverse("direktur:overview")).content.decode())
    assert menu[:7] == ["Ringkasan", "Inbox", "Dari staf", "Tim", "Task", "Evaluasi staf", "Kebijakan"]
    for label in ("Komplain", "Kerusakan", "Laporan staf", "Masukan privat staf"):
        assert label not in menu  # tab di halaman Dari staf
    for label in ("Checklist Direktur",
                  "Catatan", "Hari Ini", "Checklist Saya", "Jadwal Jaga", "Pembagian Tugas",
                  "Laporan Operasional", "Audit", "Pengaturan Klinik"):
        assert label in menu


def test_staff_menu_is_simple(client, clinic):
    client.force_login(_user(clinic, "yani", Role.PERAWAT, Role.STAF))
    menu = _nav(client.get(reverse("core:today")).content.decode())
    assert menu[:4] == ["Tugas hari ini", "Jadwal saya", "Istirahat saya", "Tindakan saya"]
    for label in ("Komplain", "Masukan", "Kerusakan", "Laporan Saya", "Masukan Saya", "Kebijakan"):
        assert label in menu
    for label in ("Hari Ini", "Checklist Saya", "Jadwal Jaga", "Jadwal Istirahat", "Giliran Perawat",
                  "Pembagian Tugas", "Laporan Operasional", "Audit", "Ringkasan", "Kas", "Admin"):
        assert label not in menu


def test_pic_menu_adds_team_pages(client, clinic):
    pic = _user(clinic, "desy", Role.PIC, Role.FRONT_DESK)
    PicAssignment.objects.create(user=pic, clinic=clinic, function=PicFunction.CASHIER, starts_on="2026-09-01")
    client.force_login(pic)
    menu = _nav(client.get(reverse("core:dashboard")).content.decode())
    for label in ("Pembagian Tugas", "Laporan Operasional", "Kas"):
        assert label in menu
    for label in ("Ringkasan", "Checklist Direktur"):
        assert label not in menu


def test_admin_menu(client, clinic):
    client.force_login(_user(clinic, "superadmin", Role.ADMIN))
    menu = _nav(client.get(reverse("accounts:user_list")).content.decode())
    assert menu[:2] == ["Pengguna", "Reset peran"]
    for label in ("Hari Ini", "Checklist Saya", "Kas", "Ringkasan"):
        assert label not in menu


@pytest.mark.parametrize(
    "roles",
    [(Role.OWNER,), (Role.AOM,), (Role.PIC, Role.FRONT_DESK), (Role.SUPERVISOR, Role.PERAWAT),
     (Role.PERAWAT, Role.STAF), (Role.APOTEKER, Role.STAF), (Role.ADMIN,)],
)
def test_every_menu_link_opens(client, clinic, roles):
    """Tidak ada menu yang berujung 403: menu dan penolakan server sejalan."""
    user = _user(clinic, "u1", *roles)
    client.force_login(user)
    for section in peran.nav_sections(user):
        for label, url, _also in section.items:
            # Reset peran mengalihkan kembali ke Pengguna bila cabang standar belum ada.
            assert client.get(url, follow=True).status_code == 200, (roles, label, url)


# --- Penolakan server-side ---------------------------------------------------


def test_owner_blocked_everywhere_outside_owner_view(client, clinic):
    client.force_login(_user(clinic, "yohanes", Role.OWNER))
    checked = 0
    for route, url in _all_routes():
        if peran.route_allowed(User.objects.get(username="yohanes"), route):
            continue
        for method in (client.get, client.post):
            assert method(url).status_code == 403, (route, url)
        checked += 1
    assert checked > 60


@pytest.mark.parametrize(
    "route",
    ["core:dashboard", "checklists:index", "jadwal:plan", "audit:log", "reports:index", "reports:laporan_page",
     "reports:masukan_page", "core:clinic_profile", "cash:index", "direktur:checklist", "direktur:notes",
     "direktur:task_new", "direktur:overview", "issues:list", "nurses:board", "breaks:list"],
)
def test_owner_named_pages_forbidden(client, clinic, route):
    client.force_login(_user(clinic, "jean", Role.OWNER))
    assert client.get(reverse(route)).status_code == 403


@pytest.mark.parametrize("route", ["owner:dashboard", "owner:summary", "owner:jadwal", "owner:request_new",
                                   "direktur:decisions", "direktur:team", "direktur:kanban",
                                   "direktur:matrix", "direktur:gantt", "jadwal:roster", "notifications:list"])
def test_owner_pages_open(client, clinic, route):
    client.force_login(_user(clinic, "jean", Role.OWNER))
    assert client.get(reverse(route)).status_code == 200


def test_owner_cannot_edit_roster(client, clinic):
    client.force_login(_user(clinic, "jean", Role.OWNER))
    other = _user(clinic, "yani", Role.PERAWAT)
    response = client.post(reverse("jadwal:roster"), {"orang": other.pk, "tanggal": "2026-10-01", "status": "OFF"})
    assert response.status_code == 403


@pytest.mark.parametrize("route", ["jadwal:plan", "reports:index", "audit:log", "direktur:overview",
                                   "direktur:checklist", "accounts:user_list", "accounts:role_reset"])
def test_staff_forbidden(client, clinic, route):
    client.force_login(_user(clinic, "yani", Role.PERAWAT, Role.STAF))
    assert client.get(reverse(route)).status_code == 403


def test_staff_forbidden_team_day_and_export(client, clinic):
    client.force_login(_user(clinic, "yani", Role.PERAWAT, Role.STAF))
    assert client.get(reverse("jadwal:day", args=["2026-10-02"])).status_code == 403
    assert client.get(reverse("reports:export", args=["kas"])).status_code == 403


@pytest.mark.parametrize("route", ["core:dashboard", "checklists:index", "cash:index", "nurses:board",
                                   "issues:list", "reports:laporan_page", "direktur:overview"])
def test_admin_forbidden_operational_pages(client, clinic, route):
    client.force_login(_user(clinic, "superadmin", Role.ADMIN))
    assert client.get(reverse(route)).status_code == 403


def test_pic_and_director_open_team_pages(client, clinic):
    client.force_login(_user(clinic, "heni", Role.SUPERVISOR, Role.PERAWAT))
    assert client.get(reverse("jadwal:plan")).status_code == 200
    assert client.get(reverse("reports:index")).status_code == 200
    client.force_login(_user(clinic, "hansen1", Role.AOM))
    for route in ("jadwal:plan", "reports:index", "audit:log", "direktur:checklist", "core:dashboard"):
        assert client.get(reverse(route)).status_code == 200, route


def test_staff_team_plan_link_hidden(client, clinic):
    client.force_login(_user(clinic, "yani", Role.PERAWAT, Role.STAF))
    assert "Pembagian tugas bulan ini" not in client.get(reverse("jadwal:roster")).content.decode()
    client.force_login(_user(clinic, "hansen1", Role.AOM))
    assert "Pembagian tugas bulan ini" in client.get(reverse("jadwal:roster")).content.decode()


def test_grouped_menu_and_page_tabs(client, clinic):
    """5 Okt 2026: Task / Evaluasi staf / Kebijakan satu menu; halaman kelompoknya punya tab di atas."""
    client.force_login(_user(clinic, "hansen1", Role.AOM))
    for route, tabs, active in (
        ("direktur:kanban", ["Daftar Task", "Kanban", "Prioritas", "Jadwal Task"], "Kanban"),
        ("jejak:index", ["KPI", "Jejak", "Absensi"], "Jejak"),
        ("absensi:index", ["KPI", "Jejak", "Absensi"], "Absensi"),
        ("direktur:meeting", ["Kebijakan", "Keputusan", "Bahan Rapat"], "Bahan Rapat"),
    ):
        body = client.get(reverse(route)).content.decode()
        bar = body.split('class="subnav"', 1)[1].split("</nav>", 1)[0]
        assert re.findall(r">([^<]+)</a>", bar) == tabs, route
        assert re.search(r'aria-current="page">' + active + "<", bar), route
    assert 'class="subnav"' not in client.get(reverse("direktur:overview")).content.decode()
    # Dari staf: tab ber-query (Komplain/Masukan/Kerusakan berbagi satu halaman daftar).
    tabs = ["Komplain", "Masukan", "Kerusakan", "Laporan staf", "Masukan privat staf"]
    for url, active in ((reverse("issues:list") + "?tipe=MASUKAN&cabang=semua", "Masukan"),
                        (reverse("issues:list") + "?tipe=KERUSAKAN", "Kerusakan"),
                        (reverse("reports:masukan_page"), "Masukan privat staf")):
        bar = client.get(url).content.decode().split('class="subnav"', 1)[1].split("</nav>", 1)[0]
        assert re.findall(r">([^<]+)</a>", bar) == tabs, url
        assert re.findall(r'aria-current="page">([^<]+)<', bar) == [active], url
    bar = client.get(reverse("issues:list")).content.decode().split('class="subnav"', 1)[1].split("</nav>", 1)[0]
    assert "aria-current" not in bar  # semua tipe: tidak ada tab aktif
    # Owner: tab hanya halaman yang boleh ia buka.
    client.force_login(_user(clinic, "yohanes", Role.OWNER))
    body = client.get(reverse("direktur:kpi")).content.decode()
    assert 'class="subnav"' in body and ">Jejak<" in body
