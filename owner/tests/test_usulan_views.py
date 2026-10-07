"""Halaman Usulan Direktur ke Owner (tahap 4, 7 Okt 2026): daftar, form, detail, menu, kartu Dashboard."""
from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic, local_today
from notifications.models import Notification
from owner import usulan as us
from owner.models import Usulan, UsulanKind, UsulanStatus

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def yani(jemur):
    return _user(jemur, "yani", Role.STAF, display_name="Yani")


@pytest.fixture
def sandra(jemur):
    return _user(jemur, "sandra", Role.SUPERVISOR, display_name="Sandra")


def _as(client, user):
    client.force_login(user)
    return client


def _minta(hansen, jemur=None, **kw):
    data = dict(actor=hansen, kind=UsulanKind.PERSETUJUAN, title="Beli AC ruang tindakan",
                description="AC lama bocor.", amount=1500000, clinic=jemur)
    data.update(kw)
    return us.create_usulan(**data)


def _lapor(hansen, **kw):
    data = dict(actor=hansen, kind=UsulanKind.LAPORAN, title="Stok sunscreen menipis", description="Sisa 3 hari.")
    data.update(kw)
    return us.create_usulan(**data)


def _msgs(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


def _post(client, url, **data):
    return client.post(url, data)


# --- membuat -----------------------------------------------------------------------------


def test_aom_creates_usulan_via_post(client, jemur, yohanes, hansen):
    _as(client, hansen)
    r = _post(client, reverse("owner:usulan_new"), jenis="PERSETUJUAN", judul="Beli AC", uraian="AC bocor.",
              nominal="1.500.000", cabang=str(jemur.pk), batas="")
    u = Usulan.objects.get()
    assert r.status_code == 302 and r["Location"] == reverse("owner:usulan_detail", args=[u.pk])
    assert u.amount == 1500000 and u.clinic == jemur and u.created_by == hansen
    assert Notification.objects.filter(user=yohanes, type_code="USULAN_NEW").exists()
    assert "Usulan dikirim ke Owner." in _msgs(r)


def test_new_form_get_for_aom(client, hansen):
    r = _as(client, hansen).get(reverse("owner:usulan_new"))
    assert r.status_code == 200 and "Perlu jawaban sebelum" in r.content.decode()


@pytest.mark.parametrize("data, pesan", [
    (dict(judul="Beli AC", uraian="x", nominal="abc"), "Nominal harus angka."),
    (dict(judul="Beli AC", uraian="x", nominal="1000000000000"), "Nominal terlalu besar."),
    (dict(judul="  ", uraian="x", nominal=""), "Judul wajib diisi."),
])
def test_new_invalid_shows_error_and_creates_nothing(client, hansen, data, pesan):
    r = _post(_as(client, hansen), reverse("owner:usulan_new"), jenis="PERSETUJUAN", cabang="", batas="", **data)
    assert r.status_code == 200 and not Usulan.objects.exists()
    assert pesan in _msgs(r)
    if data["judul"].strip():
        assert f'value="{data["judul"]}"' in r.content.decode()


def test_owner_cannot_open_or_post_new(client, yohanes):
    _as(client, yohanes)
    assert client.get(reverse("owner:usulan_new")).status_code == 403
    r = _post(client, reverse("owner:usulan_new"), jenis="PERSETUJUAN", judul="X", uraian="Y")
    assert r.status_code == 403 and not Usulan.objects.exists()


# --- hak akses ---------------------------------------------------------------------------


def test_staff_and_supervisor_are_forbidden(client, jemur, hansen, yani, sandra):
    u = _minta(hansen, jemur)
    for who in (yani, sandra):
        _as(client, who)
        assert client.get(reverse("owner:usulan_list")).status_code == 403
        assert client.get(reverse("owner:usulan_detail", args=[u.pk])).status_code == 403
        assert _post(client, reverse("owner:usulan_detail", args=[u.pk]), aksi="setuju").status_code == 403


# --- keputusan Owner ---------------------------------------------------------------------


def test_owner_approves(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur)
    url = reverse("owner:usulan_detail", args=[u.pk])
    page = _as(client, yohanes).get(url).content.decode()
    assert "Setujui" in page and "Bahas di rapat Kamis" in page and "Batalkan usulan" not in page
    r = _post(client, url, aksi="setuju", catatan="Boleh.")
    assert r["Location"] == url and "Keputusan dikirim ke Direktur Operasional." in _msgs(r)
    u.refresh_from_db()
    assert u.status == UsulanStatus.DISETUJUI and u.decided_by == yohanes
    assert "Boleh." in client.get(url).content.decode()


def test_owner_reject_requires_reason(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur)
    url = reverse("owner:usulan_detail", args=[u.pk])
    r = _post(_as(client, yohanes), url, aksi="tolak", catatan="")
    assert "Tulis alasan penolakan." in _msgs(r)
    u.refresh_from_db()
    assert u.status == UsulanStatus.MENUNGGU
    _post(client, url, aksi="tolak", catatan="Belum ada anggaran.")
    u.refresh_from_db()
    assert u.status == UsulanStatus.DITOLAK


def test_owner_brings_to_meeting_and_link_shown(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur)
    url = reverse("owner:usulan_detail", args=[u.pk])
    r = _post(_as(client, yohanes), url, aksi="rapat", catatan="")
    assert "Dibawa ke rapat Kamis; Direktur Operasional sudah diberi tahu." in _msgs(r)
    u.refresh_from_db()
    assert u.status == UsulanStatus.RAPAT and u.decision_id
    assert reverse("direktur:decision_detail", args=[u.decision_id]) in client.get(url).content.decode()


def test_owner_marks_report_read(client, yohanes, hansen):
    u = _lapor(hansen)
    url = reverse("owner:usulan_detail", args=[u.pk])
    page = _as(client, yohanes).get(url).content.decode()
    assert "Tandai sudah dibaca" in page and "Setujui" not in page
    r = _post(client, url, aksi="dibaca")
    assert "Ditandai sudah dibaca." in _msgs(r)
    u.refresh_from_db()
    assert u.status == UsulanStatus.DIBACA
    assert "Dibaca Owner pukul" in client.get(url).content.decode()


def test_aom_cannot_decide(client, jemur, hansen):
    u = _minta(hansen, jemur)
    r = _post(_as(client, hansen), reverse("owner:usulan_detail", args=[u.pk]), aksi="setuju")
    assert r.status_code == 403
    u.refresh_from_db()
    assert u.status == UsulanStatus.MENUNGGU


# --- pembatalan dan percakapan -----------------------------------------------------------


def test_aom_cancels(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur)
    url = reverse("owner:usulan_detail", args=[u.pk])
    page = _as(client, hansen).get(url).content.decode()
    assert "Batalkan usulan" in page and "Setujui" not in page
    r = _post(client, url, aksi="batal", alasan="Sudah ditangani.")
    assert "Usulan dibatalkan." in _msgs(r)
    u.refresh_from_db()
    assert u.status == UsulanStatus.DIBATALKAN
    assert "Sudah ditangani." in client.get(url).content.decode()


def test_notes_from_both_sides_appear(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur)
    url = reverse("owner:usulan_detail", args=[u.pk])
    r = _post(_as(client, yohanes), url, aksi="catatan", catatan="Berapa vendor?")
    assert "Catatan terkirim." in _msgs(r)
    _post(_as(client, hansen), url, aksi="catatan", catatan="Ada tiga vendor.")
    page = client.get(url).content.decode()
    assert page.index("Berapa vendor?") < page.index("Ada tiga vendor.")
    assert "dr. Yohanes" in page and "dr. Hansen" in page
    r = _post(client, url, aksi="catatan", catatan="  ")
    assert "Catatan kosong." in _msgs(r)


# --- daftar ------------------------------------------------------------------------------


def test_list_default_hides_decided_and_semua_shows(client, jemur, yohanes, hansen):
    buka = _minta(hansen, jemur, title="Usulan terbuka")
    putus = _minta(hansen, jemur, title="Usulan diputus")
    us.decide_usulan(putus, actor=yohanes, verdict="setuju")
    page = _as(client, yohanes).get(reverse("owner:usulan_list")).content.decode()
    assert "Usulan terbuka" in page and "Usulan diputus" not in page
    page = client.get(reverse("owner:usulan_list") + "?semua=1").content.decode()
    assert "Usulan terbuka" in page and "Usulan diputus" in page
    assert buka.pk and "Usulan baru" not in page


def test_list_empty_and_create_button_for_aom(client, hansen):
    page = _as(client, hansen).get(reverse("owner:usulan_list")).content.decode()
    assert "Belum ada usulan." in page and "+ Usulan baru" in page


def test_nominal_formatted_with_dots(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur)
    _as(client, yohanes)
    assert "Rp1.500.000" in client.get(reverse("owner:usulan_list")).content.decode()
    assert "Rp1.500.000" in client.get(reverse("owner:usulan_detail", args=[u.pk])).content.decode()


def test_overdue_tag(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur, needed_by=local_today())
    Usulan.objects.filter(pk=u.pk).update(needed_by=local_today() - dt.timedelta(days=2))
    assert "Lewat tenggat" in _as(client, yohanes).get(reverse("owner:usulan_list")).content.decode()


# --- dashboard dan menu ------------------------------------------------------------------


def test_dashboard_card_shows_and_disappears(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur, title="Beli AC kamar")
    _lapor(hansen, title="Stok menipis")
    page = _as(client, yohanes).get(reverse("owner:dashboard")).content.decode()
    assert "Usulan Direktur" in page and "Beli AC kamar" in page and "Putuskan" in page and "Belum dibaca" in page
    assert reverse("owner:usulan_detail", args=[u.pk]) in page
    us.decide_usulan(u, actor=yohanes, verdict="setuju")
    page = client.get(reverse("owner:dashboard")).content.decode()
    assert "Beli AC kamar" not in page and "Stok menipis" in page


def test_dashboard_without_usulan_has_no_card(client, yohanes):
    assert 'id="judul-usulan"' not in _as(client, yohanes).get(reverse("owner:dashboard")).content.decode()


def test_menu_entries(client, jemur, yohanes, hansen):
    owner_page = _as(client, yohanes).get(reverse("owner:dashboard")).content.decode()
    assert "Usulan Direktur" in owner_page
    list_url = reverse("owner:usulan_list")
    assert f'href="{list_url}"' in owner_page
    page = _as(client, hansen).get(list_url).content.decode()
    assert "Usulan ke Owner" in page


# --- masukan tak terduga -----------------------------------------------------------------


def test_new_non_ascii_nominal_is_error_not_500(client, hansen):
    for nilai in ("\u00b2", "\u0661\u0662\u0663"):
        r = _post(_as(client, hansen), reverse("owner:usulan_new"), jenis="PERSETUJUAN", judul="Beli AC",
                  uraian="x", nominal=nilai, cabang="", batas="")
        assert r.status_code == 200 and not Usulan.objects.exists()
        assert "Nominal harus angka." in _msgs(r)


def test_new_non_ascii_cabang_is_not_500(client, hansen):
    r = _post(_as(client, hansen), reverse("owner:usulan_new"), jenis="PERSETUJUAN", judul="Beli AC",
              uraian="x", nominal="", cabang="\u00b2", batas="")
    assert r.status_code == 302
    assert Usulan.objects.get().clinic is None


def test_owner_cannot_cancel_usulan(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur)
    r = _post(_as(client, yohanes), reverse("owner:usulan_detail", args=[u.pk]), aksi="batal", alasan="Tidak perlu.")
    assert r.status_code == 403
    u.refresh_from_db()
    assert u.status == UsulanStatus.MENUNGGU


def test_rapat_decision_listed_in_meeting_not_in_owner_awaiting(client, jemur, yohanes, hansen):
    u = _minta(hansen, jemur, title="Beli AC rapat")
    _post(_as(client, yohanes), reverse("owner:usulan_detail", args=[u.pk]), aksi="rapat", catatan="")
    u.refresh_from_db()
    assert u.status == UsulanStatus.RAPAT and u.decision_id
    assert "Beli AC rapat" in _as(client, hansen).get(reverse("direktur:meeting")).content.decode()
    page = _as(client, yohanes).get(reverse("owner:dashboard")).content.decode()
    # Perkara rapat bukan perkara Owner: tidak masuk kartu keputusan, hanya agenda rapat Kamis.
    assert "Menunggu keputusan Anda" not in page and "judul-keputusan" not in page
    assert "Agenda rapat Kamis" in page and "Beli AC rapat" in page
