"""Usulan target baru dari Direktur untuk Permintaan dan Temuan Owner (7 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import ActionItem, ActionItemStatus, Clinic, local_today
from notifications.models import Notification
from owner import services
from owner.models import SOURCE_TYPE, OwnerRequest, OwnerRequestNote, RequestKind

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, **extra)
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
def desy(jemur):
    return _user(jemur, "desy", Role.STAF, display_name="Desy")


def _day(n):
    return local_today() + dt.timedelta(days=n)


def _permintaan(owner, days=10):
    return services.create_request(actor=owner, title="Evaluasi harga paket", target_date=_day(days))


def _temuan(owner, urgent=False):
    return services.create_request(actor=owner, kind=RequestKind.TEMUAN, title="Alur belum seragam", urgent=urgent)


def _msgs(response):
    return [str(m) for m in get_messages(response.wsgi_request)][-1:]


# --- propose_target ---------------------------------------------------------------


def test_director_proposes_for_request(yohanes, hansen):
    req = _permintaan(yohanes)
    Notification.objects.all().delete()
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="Menunggu vendor")
    req.refresh_from_db()
    assert (req.proposed_target, req.proposed_reason, req.proposed_by, req.target_date) == (
        _day(20), "Menunggu vendor", hansen, _day(10))
    assert req.proposed_at is not None
    assert services.has_pending_target(req)
    note = OwnerRequestNote.objects.get(request=req)
    assert note.author == hansen
    assert note.body == f"Usul target baru {_day(20):%d/%m/%Y}: Menunggu vendor"
    notif = Notification.objects.get(user=yohanes)
    assert notif.title == "Usulan target baru: Evaluasi harga paket"
    assert notif.body == f"{_day(10):%d/%m/%Y} → {_day(20):%d/%m/%Y} · Menunggu vendor"
    assert notif.url == reverse("owner:request_detail", args=[req.pk])
    assert not Notification.objects.filter(user=hansen).exists()


def test_propose_wording_without_target(yohanes, hansen):
    req = _temuan(yohanes)
    Notification.objects.all().delete()
    services.propose_target(req, actor=hansen, target_date=_day(45), reason="Besar")
    assert Notification.objects.get(user=yohanes).body.startswith("tanpa target → ")


def test_only_director_proposes(yohanes, hansen, desy):
    req = _permintaan(yohanes)
    for who in (desy, yohanes):
        with pytest.raises(PermissionDenied, match="Hanya Direktur Operasional yang mengusulkan target."):
            services.propose_target(req, actor=who, target_date=_day(20), reason="x")


@pytest.mark.parametrize("day,reason,msg", [
    (-1, "x", "Tanggal target tidak boleh sebelum hari ini."),
    (10, "x", "Usulan sama dengan target sekarang."),
    (20, "  ", "Tulis alasan usulan."),
])
def test_propose_validation(yohanes, hansen, day, reason, msg):
    req = _permintaan(yohanes)
    with pytest.raises(ValidationError) as exc:
        services.propose_target(req, actor=hansen, target_date=_day(day), reason=reason)
    assert msg in exc.value.messages
    req.refresh_from_db()
    assert not services.has_pending_target(req)


def test_finding_within_cap_must_use_plan(yohanes, hansen):
    req = _temuan(yohanes)
    cap = services.deadline_cap(req)
    with pytest.raises(ValidationError) as exc:
        services.propose_target(req, actor=hansen, target_date=cap, reason="x")
    assert exc.value.messages == ["Masih dalam batas; ubah langsung di Rencana penanganan."]


def test_finding_beyond_cap_ok(yohanes, hansen):
    req = _temuan(yohanes)
    beyond = services.deadline_cap(req) + dt.timedelta(days=1)
    services.propose_target(req, actor=hansen, target_date=beyond, reason="Butuh anggaran")
    req.refresh_from_db()
    assert req.proposed_target == beyond


def test_finished_request_rejects_proposal(jemur, yohanes, hansen):
    req = _permintaan(yohanes)
    ActionItem.objects.create(clinic=jemur, title="T", source_type=SOURCE_TYPE, source_id=req.pk,
                              status=ActionItemStatus.SELESAI)
    with pytest.raises(ValidationError) as exc:
        services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    assert exc.value.messages == ["Permintaan ini sudah selesai."]


def test_completed_finding_rejects_proposal(yohanes, hansen):
    req = _temuan(yohanes)
    OwnerRequest.objects.filter(pk=req.pk).update(completed_at=timezone.now(), completed_by=hansen)
    req.refresh_from_db()
    with pytest.raises(ValidationError, match="sudah selesai"):
        services.propose_target(req, actor=hansen, target_date=_day(60), reason="x")


def test_second_proposal_replaces_first(yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="Satu")
    services.propose_target(req, actor=hansen, target_date=_day(25), reason="Dua")
    req.refresh_from_db()
    assert (req.proposed_target, req.proposed_reason) == (_day(25), "Dua")


# --- decide_target ----------------------------------------------------------------


def test_owner_approves(yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="Menunggu vendor")
    Notification.objects.all().delete()
    services.decide_target(req, actor=yohanes, approve=True, note="Oke")
    req.refresh_from_db()
    assert req.target_date == _day(20)
    assert (req.proposed_target, req.proposed_reason, req.proposed_by, req.proposed_at) == (None, "", None, None)
    note = OwnerRequestNote.objects.filter(author=yohanes).get()
    assert note.body.startswith(f"Target baru {_day(20):%d/%m/%Y} disetujui.")
    assert "Oke" in note.body
    assert note.body.endswith(" Target task turunan tidak ikut berubah; ubah di task bila perlu.")
    assert "Target task turunan tidak ikut berubah" in Notification.objects.get(user=hansen).body
    notif = Notification.objects.get(user=hansen)
    assert notif.title == "Target disetujui: Evaluasi harga paket"
    assert not Notification.objects.filter(user=yohanes).exists()


def test_reject_needs_note_then_keeps_target(yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    with pytest.raises(ValidationError) as exc:
        services.decide_target(req, actor=yohanes, approve=False, note=" ")
    assert exc.value.messages == ["Tulis alasan penolakan."]
    Notification.objects.all().delete()
    services.decide_target(req, actor=yohanes, approve=False, note="Terlalu lama")
    req.refresh_from_db()
    assert req.target_date == _day(10)
    assert req.proposed_target is None
    assert OwnerRequestNote.objects.filter(
        author=yohanes, body=f"Usulan target {_day(20):%d/%m/%Y} ditolak: Terlalu lama").exists()
    assert Notification.objects.get(user=hansen).title == "Target ditolak: Evaluasi harga paket"


def test_only_owner_decides(yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    with pytest.raises(PermissionDenied, match="Hanya Owner / Direktur Utama yang memutuskan target."):
        services.decide_target(req, actor=hansen, approve=True)


def test_decide_without_pending(yohanes):
    req = _permintaan(yohanes)
    with pytest.raises(ValidationError) as exc:
        services.decide_target(req, actor=yohanes, approve=True)
    assert exc.value.messages == ["Tidak ada usulan target yang menunggu."]


def test_second_answer_fails(yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    services.decide_target(req, actor=yohanes, approve=True)
    with pytest.raises(ValidationError):
        services.decide_target(req, actor=yohanes, approve=False, note="tolak")


def test_set_plan_with_approved_beyond_cap_target(yohanes, hansen):
    req = _temuan(yohanes)
    beyond = services.deadline_cap(req) + dt.timedelta(days=5)
    services.propose_target(req, actor=hansen, target_date=beyond, reason="Butuh anggaran")
    services.decide_target(req, actor=yohanes, approve=True)
    req.refresh_from_db()
    services.set_plan(req, actor=hansen, plan_title="Buat alur", target_date=beyond)
    req.refresh_from_db()
    assert (req.target_date, req.plan_title) == (beyond, "Buat alur")


# --- views ------------------------------------------------------------------------


def _url(req):
    return reverse("owner:request_detail", args=[req.pk])


def test_view_director_proposes(client, yohanes, hansen):
    req = _permintaan(yohanes)
    client.force_login(hansen)
    resp = client.post(_url(req), {"aksi": "usul_target", "target_baru": _day(20).isoformat(), "alasan": "Vendor"})
    assert resp.status_code == 302
    assert _msgs(resp) == ["Usulan target dikirim ke Owner."]
    req.refresh_from_db()
    assert req.proposed_target == _day(20)


def test_view_bad_date_and_validation_errors(client, yohanes, hansen):
    req = _permintaan(yohanes)
    client.force_login(hansen)
    resp = client.post(_url(req), {"aksi": "usul_target", "target_baru": "bukan", "alasan": "x"})
    assert _msgs(resp) == ["Tanggal tidak valid."]
    resp = client.post(_url(req), {"aksi": "usul_target", "target_baru": _day(20).isoformat(), "alasan": ""})
    assert _msgs(resp) == ["Tulis alasan usulan."]


def test_view_owner_cannot_propose_and_director_cannot_decide(client, yohanes, hansen):
    req = _permintaan(yohanes)
    client.force_login(yohanes)
    assert client.post(_url(req), {"aksi": "usul_target", "target_baru": _day(20).isoformat(),
                                   "alasan": "x"}).status_code == 403
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    client.force_login(hansen)
    assert client.post(_url(req), {"aksi": "setujui_target"}).status_code == 403
    assert client.post(_url(req), {"aksi": "tolak_target", "catatan": "x"}).status_code == 403


def test_view_owner_approves_and_rejects(client, yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    client.force_login(yohanes)
    resp = client.post(_url(req), {"aksi": "tolak_target", "catatan": ""})
    assert _msgs(resp) == ["Tulis alasan penolakan."]
    resp = client.post(_url(req), {"aksi": "tolak_target", "catatan": "Tidak"})
    assert _msgs(resp) == ["Usulan target ditolak; Direktur Operasional diberi tahu."]
    services.propose_target(req, actor=hansen, target_date=_day(21), reason="y")
    resp = client.post(_url(req), {"aksi": "setujui_target", "catatan": ""})
    assert _msgs(resp) == ["Target baru disetujui; Direktur Operasional diberi tahu."]
    req.refresh_from_db()
    assert req.target_date == _day(21)


def test_detail_shows_pending_box_and_buttons_for_owner_only(client, yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="Menunggu vendor")
    client.force_login(yohanes)
    body = client.get(_url(req)).content.decode()
    assert f"Usulan target baru: {_day(20):%d/%m/%Y}" in body
    assert "Menunggu vendor" in body
    assert f"Setujui target {_day(20):%d/%m/%Y}" in body
    assert "Kirim usulan" not in body
    client.force_login(hansen)
    body = client.get(_url(req)).content.decode()
    assert "Menunggu jawaban Owner." in body
    assert "Setujui target" not in body
    assert "Kirim usulan" in body


def test_detail_hides_proposal_form_when_finished(client, jemur, yohanes, hansen):
    req = _permintaan(yohanes)
    ActionItem.objects.create(clinic=jemur, title="T", source_type=SOURCE_TYPE, source_id=req.pk,
                              status=ActionItemStatus.SELESAI)
    client.force_login(hansen)
    assert "Kirim usulan" not in client.get(_url(req)).content.decode()


def test_plan_form_max_not_below_current_target(client, yohanes, hansen):
    req = _temuan(yohanes)
    beyond = services.deadline_cap(req) + dt.timedelta(days=5)
    services.propose_target(req, actor=hansen, target_date=beyond, reason="x")
    services.decide_target(req, actor=yohanes, approve=True)
    client.force_login(hansen)
    body = client.get(_url(req)).content.decode()
    assert f'max="{beyond:%Y-%m-%d}"' in body


def test_dashboard_tag_for_pending_proposal(client, yohanes, hansen):
    req = _permintaan(yohanes)
    client.force_login(yohanes)
    assert "Usul target" not in client.get(reverse("owner:dashboard")).content.decode()
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert f"Usul target {_day(20):%d/%m}" in body


# --- tinjauan: usulan basi, selesai, notifikasi, izin -------------------------------


def _finish(jemur, req):
    ActionItem.objects.create(clinic=jemur, title="T", source_type=SOURCE_TYPE, source_id=req.pk,
                              status=ActionItemStatus.SELESAI)


def test_stale_approval_is_refused(yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="Satu")
    req.refresh_from_db()
    seen = req.proposed_at.isoformat()
    services.propose_target(req, actor=hansen, target_date=_day(25), reason="Dua")
    with pytest.raises(ValidationError) as exc:
        services.decide_target(req, actor=yohanes, approve=True, expected=seen)
    assert exc.value.messages == ["Usulan target sudah berubah; periksa lagi."]
    req.refresh_from_db()
    assert req.target_date == _day(10)
    assert req.proposed_target == _day(25)
    services.decide_target(req, actor=yohanes, approve=True, expected=req.proposed_at.isoformat())
    req.refresh_from_db()
    assert req.target_date == _day(25)


def test_view_hidden_value_round_trips_and_stale_is_refused(client, yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="Satu")
    client.force_login(yohanes)
    import re
    body = client.get(_url(req)).content.decode()
    stamp = re.search(r'name="usulan" value="([^"]+)"', body).group(1)
    services.propose_target(req, actor=hansen, target_date=_day(25), reason="Dua")
    resp = client.post(_url(req), {"aksi": "setujui_target", "usulan": stamp})
    assert _msgs(resp) == ["Usulan target sudah berubah; periksa lagi."]
    body = client.get(_url(req)).content.decode()
    stamp = re.search(r'name="usulan" value="([^"]+)"', body).group(1)
    resp = client.post(_url(req), {"aksi": "setujui_target", "usulan": stamp})
    assert _msgs(resp) == ["Target baru disetujui; Direktur Operasional diberi tahu."]
    req.refresh_from_db()
    assert req.target_date == _day(25)


def test_decide_refused_when_finished(jemur, yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    _finish(jemur, req)
    with pytest.raises(ValidationError) as exc:
        services.decide_target(req, actor=yohanes, approve=True)
    assert exc.value.messages == ["Permintaan ini sudah selesai."]
    req.refresh_from_db()
    assert req.target_date == _day(10)


def test_dashboard_hides_tag_when_done(client, jemur, yohanes, hansen):
    req = _permintaan(yohanes)
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    client.force_login(yohanes)
    assert "Usul target" in client.get(reverse("owner:dashboard")).content.decode()
    _finish(jemur, req)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Evaluasi harga paket" in body
    assert "Usul target" not in body


def test_catatan_does_not_overwrite_proposal_notification(yohanes, hansen):
    req = _permintaan(yohanes)
    Notification.objects.all().delete()
    services.propose_target(req, actor=hansen, target_date=_day(20), reason="x")
    services.add_note(req, actor=hansen, body="Mohon dilihat")
    titles = sorted(Notification.objects.filter(user=yohanes).values_list("title", flat=True))
    assert len(titles) == 2
    assert any(t.startswith("Usulan target baru") for t in titles)


def test_supervisor_and_staff_cannot_post_proposal(client, jemur, yohanes, hansen, desy):
    sup = _user(jemur, "sup", Role.SUPERVISOR, display_name="Sup")
    req = _permintaan(yohanes)
    for who in (sup, desy):
        client.force_login(who)
        resp = client.post(_url(req), {"aksi": "usul_target", "target_baru": _day(20).isoformat(), "alasan": "x"})
        assert resp.status_code == 403
    req.refresh_from_db()
    assert req.proposed_target is None
