"""Usulan Direktur ke Owner atas inisiatif sendiri (tahap 4, 7 Okt 2026): aturan di service."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import Clinic, local_today
from direktur.models import Decider, Decision
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
def jean(jemur):
    return _user(jemur, "jean", Role.OWNER, display_name="Jean")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def dina(jemur):
    return _user(jemur, "dina", Role.AOM, display_name="dr. Dina")


@pytest.fixture
def yani(jemur):
    return _user(jemur, "yani", Role.STAF, display_name="Yani")


def _minta(hansen, jemur=None, **kw):
    data = dict(actor=hansen, kind=UsulanKind.PERSETUJUAN, title="Beli AC ruang tindakan",
                description="AC lama bocor.", amount=4500000, clinic=jemur)
    data.update(kw)
    return us.create_usulan(**data)


def _lapor(hansen, **kw):
    data = dict(actor=hansen, kind=UsulanKind.LAPORAN, title="Stok sunscreen menipis", description="Sisa 3 hari.")
    data.update(kw)
    return us.create_usulan(**data)


def _types(user):
    return set(Notification.objects.filter(user=user).values_list("type_code", flat=True))


# --- create -----------------------------------------------------------------------------


def test_create_persetujuan_notifies_all_owners(jemur, yohanes, jean, hansen, dina):
    u = _minta(hansen, jemur)
    assert u.status == UsulanStatus.MENUNGGU and u.amount == 4500000 and u.created_by == hansen
    for owner in (yohanes, jean):
        n = Notification.objects.get(user=owner, type_code="USULAN_NEW")
        assert n.title == "Usulan Direktur: Beli AC ruang tindakan"
        assert "Rp4.500.000" in n.body and "dr. Hansen" in n.body
        assert n.entity_ref == f"usulan#{u.pk}"
        assert n.url == reverse("owner:usulan_detail", args=[u.pk])
    assert not Notification.objects.filter(user__in=[hansen, dina]).exists()
    assert AuditEvent.objects.filter(entity_type="usulan", entity_id=str(u.pk)).exists()


def test_create_laporan_drops_amount(jemur, yohanes, hansen):
    u = _lapor(hansen, amount=999)
    assert u.status == UsulanStatus.TERKIRIM and u.amount is None
    assert Notification.objects.filter(user=yohanes, type_code="USULAN_NEW").exists()


def test_create_only_aom(jemur, yohanes, yani):
    for who in (yani, yohanes):
        with pytest.raises(PermissionDenied):
            _minta(who)
    assert not Usulan.objects.exists()


@pytest.mark.parametrize("kw,msg", [
    ({"title": "  "}, "Judul wajib"),
    ({"description": ""}, "Uraian wajib"),
    ({"amount": -1}, "Nominal tidak boleh negatif"),
    ({"needed_by": dt.date(2020, 1, 1)}, "sebelum hari ini"),
])
def test_create_validation(hansen, kw, msg):
    with pytest.raises(ValidationError, match=msg):
        _minta(hansen, **kw)


def test_create_needed_by_today_ok(hansen):
    assert _minta(hansen, needed_by=local_today()).needed_by == local_today()


# --- decide -----------------------------------------------------------------------------


def test_decide_setuju(jemur, yohanes, jean, hansen, dina):
    u = _minta(hansen, jemur)
    us.decide_usulan(u, actor=yohanes, verdict="setuju", note="oke")
    u.refresh_from_db()
    assert (u.status, u.decided_by, u.decision_note) == (UsulanStatus.DISETUJUI, yohanes, "oke")
    assert u.decided_at is not None
    for p in (hansen, dina):
        n = Notification.objects.get(user=p, type_code="USULAN_DECIDED")
        assert n.title == "Usulan disetujui: Beli AC ruang tindakan" and n.body == "oke"
    assert not Notification.objects.filter(user__in=[yohanes, jean], type_code="USULAN_DECIDED").exists()


def test_decide_twice_rejected(jemur, yohanes, jean, hansen):
    u = _minta(hansen)
    us.decide_usulan(u, actor=yohanes, verdict="setuju")
    with pytest.raises(ValidationError, match="sudah diputuskan"):
        us.decide_usulan(u, actor=jean, verdict="tolak", note="tidak")
    u.refresh_from_db()
    assert u.decided_by == yohanes


def test_decide_only_owner(hansen, dina, yani):
    u = _minta(hansen)
    for who in (hansen, dina, yani):
        with pytest.raises(PermissionDenied):
            us.decide_usulan(u, actor=who, verdict="setuju")


def test_tolak_requires_note(yohanes, hansen):
    u = _minta(hansen)
    with pytest.raises(ValidationError, match="alasan penolakan"):
        us.decide_usulan(u, actor=yohanes, verdict="tolak", note="  ")
    us.decide_usulan(u, actor=yohanes, verdict="tolak", note="belum ada anggaran")
    u.refresh_from_db()
    assert u.status == UsulanStatus.DITOLAK


def test_unknown_verdict(yohanes, hansen):
    with pytest.raises(ValidationError, match="tidak dikenal"):
        us.decide_usulan(_minta(hansen), actor=yohanes, verdict="mungkin")


def test_rapat_creates_decision(jemur, yohanes, hansen):
    u = _minta(hansen, jemur)
    us.decide_usulan(u, actor=yohanes, verdict="rapat", note="bahas Kamis")
    u.refresh_from_db()
    assert u.status == UsulanStatus.RAPAT and u.decision is not None
    d = u.decision
    assert (d.decider, d.reference, d.title, d.clinic, d.created_by) == (
        Decider.RAPAT_BERSAMA, f"US-{u.pk}", u.title, jemur, hansen)
    assert "AC lama bocor." in d.background and "Nominal: Rp4.500.000" in d.background
    assert "Catatan Owner (dr. Yohanes): bahas Kamis" in d.background
    assert Decision.objects.count() == 1
    n = Notification.objects.get(user=hansen, type_code="USULAN_DECIDED")
    assert n.title == "Usulan dibawa ke rapat: Beli AC ruang tindakan"


def test_rapat_without_note_or_amount(yohanes, hansen):
    u = _minta(hansen, amount=None)
    us.decide_usulan(u, actor=yohanes, verdict="rapat")
    u.refresh_from_db()
    assert u.decision.background == "AC lama bocor."


def test_decide_laporan_rejected(yohanes, hansen):
    with pytest.raises(ValidationError):
        us.decide_usulan(_lapor(hansen), actor=yohanes, verdict="setuju")


def test_decide_cancelled_rejected(yohanes, hansen):
    u = _minta(hansen)
    us.cancel_usulan(u, actor=hansen, reason="salah kirim")
    with pytest.raises(ValidationError, match="sudah diputuskan atau dibatalkan"):
        us.decide_usulan(u, actor=yohanes, verdict="setuju")


# --- mark_read --------------------------------------------------------------------------


def test_mark_read(yohanes, jean, hansen):
    u = _lapor(hansen)
    us.mark_read(u, actor=yohanes)
    u.refresh_from_db()
    assert (u.status, u.read_by) == (UsulanStatus.DIBACA, yohanes) and u.read_at is not None
    n = Notification.objects.get(user=hansen, type_code="USULAN_READ")
    assert n.title == "Laporan dibaca Owner: Stok sunscreen menipis"
    us.mark_read(u, actor=jean)  # no-op
    u.refresh_from_db()
    assert u.read_by == yohanes
    assert Notification.objects.filter(type_code="USULAN_READ").count() == 1


def test_mark_read_persetujuan_rejected(yohanes, hansen):
    with pytest.raises(ValidationError):
        us.mark_read(_minta(hansen), actor=yohanes)


def test_mark_read_only_owner(hansen, yani):
    u = _lapor(hansen)
    for who in (hansen, yani):
        with pytest.raises(PermissionDenied):
            us.mark_read(u, actor=who)


# --- notes ------------------------------------------------------------------------------


def test_owner_note_goes_to_creator_and_directors(yohanes, jean, hansen, dina):
    u = _minta(hansen)
    row = us.add_usulan_note(u, actor=yohanes, note="Berapa vendornya?")
    assert row.author == yohanes and u.notes.count() == 1
    for p in (hansen, dina):
        n = Notification.objects.get(user=p, type_code="USULAN_NOTE")
        assert n.title == "Catatan di usulan: Beli AC ruang tindakan"
        assert n.body == "dr. Yohanes: Berapa vendornya?"
    assert not Notification.objects.filter(user__in=[yohanes, jean], type_code="USULAN_NOTE").exists()


def test_director_note_goes_to_owners(yohanes, jean, hansen, dina):
    u = _minta(hansen)
    us.add_usulan_note(u, actor=dina, note="Dua vendor.")
    assert _types(yohanes) >= {"USULAN_NOTE"} and _types(jean) >= {"USULAN_NOTE"}
    assert not Notification.objects.filter(user__in=[hansen, dina], type_code="USULAN_NOTE").exists()


def test_note_staff_denied_and_blank(yohanes, hansen, yani):
    u = _minta(hansen)
    with pytest.raises(PermissionDenied):
        us.add_usulan_note(u, actor=yani, note="halo")
    with pytest.raises(ValidationError, match="Catatan kosong"):
        us.add_usulan_note(u, actor=yohanes, note="   ")
    assert u.notes.count() == 0


# --- cancel -----------------------------------------------------------------------------


def test_cancel(yohanes, jean, hansen):
    u = _minta(hansen)
    us.cancel_usulan(u, actor=hansen, reason="sudah teratasi")
    u.refresh_from_db()
    assert (u.status, u.cancelled_by, u.cancel_reason) == (UsulanStatus.DIBATALKAN, hansen, "sudah teratasi")
    assert u.cancelled_at is not None
    for owner in (yohanes, jean):
        n = Notification.objects.get(user=owner, type_code="USULAN_CANCELLED")
        assert n.title == "Usulan dibatalkan: Beli AC ruang tindakan" and n.body == "sudah teratasi"


def test_cancel_laporan_ok(hansen):
    u = _lapor(hansen)
    us.cancel_usulan(u, actor=hansen, reason="keliru")
    u.refresh_from_db()
    assert u.status == UsulanStatus.DIBATALKAN


def test_cancel_requires_reason(hansen):
    with pytest.raises(ValidationError, match="alasan pembatalan"):
        us.cancel_usulan(_minta(hansen), actor=hansen, reason="")


def test_cancel_after_decided_rejected(yohanes, hansen):
    u = _minta(hansen)
    us.decide_usulan(u, actor=yohanes, verdict="setuju")
    with pytest.raises(ValidationError, match="sudah diputuskan atau dibatalkan"):
        us.cancel_usulan(u, actor=hansen, reason="telat")


def test_cancel_owner_denied(yohanes, hansen):
    with pytest.raises(PermissionDenied):
        us.cancel_usulan(_minta(hansen), actor=yohanes, reason="x")


# --- izin, kartu, model -----------------------------------------------------------------


def test_can_view(yohanes, hansen, yani, jemur):
    pic = _user(jemur, "pic", Role.PIC) if hasattr(Role, "PIC") else None
    assert us.can_view_usulan(yohanes) and us.can_view_usulan(hansen)
    assert not us.can_view_usulan(yani)
    if pic:
        assert not us.can_view_usulan(pic)


def test_usulan_awaiting_order(yohanes, hansen):
    baru = _minta(hansen, title="Baru")
    lama = _minta(hansen, title="Lama")
    telat = _minta(hansen, title="Telat", needed_by=local_today())
    Usulan.objects.filter(pk=telat.pk).update(needed_by=local_today() - dt.timedelta(days=2))
    laporan = _lapor(hansen)
    selesai = _minta(hansen, title="Selesai")
    us.decide_usulan(selesai, actor=yohanes, verdict="setuju")
    rows = us.usulan_awaiting(yohanes)
    assert [r["usulan"].title for r in rows][0] == "Telat" and rows[0]["late"] is True
    assert {r["usulan"].pk for r in rows} == {baru.pk, lama.pk, telat.pk, laporan.pk}
    assert [r["usulan"].pk for r in rows[1:]] == [baru.pk, lama.pk, laporan.pk][:0] + sorted(
        [baru.pk, lama.pk, laporan.pk])
    assert all(r["late"] is False for r in rows[1:]) and rows[1]["age_days"] == 0


def test_usulan_awaiting_empty_for_non_owner(hansen, yani):
    _minta(hansen)
    assert us.usulan_awaiting(hansen) == [] and us.usulan_awaiting(yani) == []


def test_model_basics(hansen):
    u = _minta(hansen)
    assert str(u) == f"Usulan#{u.pk} · Beli AC ruang tindakan"
    assert u.is_open and not u.is_overdue(local_today())
    assert not _minta(hansen, needed_by=local_today()).is_overdue(local_today())
    assert _minta(hansen, needed_by=local_today()).is_overdue(local_today() + dt.timedelta(days=1))
    u.status = UsulanStatus.DIBACA
    assert not u.is_open
