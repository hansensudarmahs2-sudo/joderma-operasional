"""Owner memutuskan permintaan keputusan Direktur Operasional (7 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import ActionItem, Clinic, local_today
from direktur import services as direktur
from direktur.models import Decider, Decision, DecisionStatus, Verdict
from notifications.models import Notification
from owner import services

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
def yani(jemur):
    return _user(jemur, "yani", Role.STAF, display_name="Yani")


def _perkara(hansen, jemur, title="Tambah anggaran tissue", decider=Decider.OWNER, **kw):
    return direktur.create_decision(actor=hansen, title=title, decider=decider, clinic=jemur,
                                    background="Tissue habis tiap Sabtu.", **kw)


# --- Task 1: service ---------------------------------------------------------------


def test_owner_approves_with_note(jemur, yohanes, hansen):
    d = services.decide(_perkara(hansen, jemur), actor=yohanes, verdict="setuju", note="boleh, maksimal Rp1,5 juta")
    d.refresh_from_db()
    assert (d.status, d.verdict, d.decided_by, d.decided_on) == (
        DecisionStatus.DITETAPKAN, Verdict.SETUJU, yohanes, local_today())
    assert d.decision_text == "Disetujui dr. Yohanes: boleh, maksimal Rp1,5 juta"
    note = Notification.objects.get(user=hansen, type_code="DECISION_DECIDED")
    assert note.title == "Keputusan Owner: Tambah anggaran tissue" and note.body == d.decision_text
    assert note.url == reverse("direktur:decision_detail", args=[d.pk])
    assert AuditEvent.objects.filter(entity_type="decision", entity_id=str(d.pk), action=AuditAction.APPROVE).exists()


def test_approve_without_note(jemur, yohanes, hansen):
    d = services.decide(_perkara(hansen, jemur), actor=yohanes, verdict="setuju")
    assert d.decision_text == "Disetujui dr. Yohanes"


def test_reject_requires_reason(jemur, jean, hansen):
    d = _perkara(hansen, jemur)
    with pytest.raises(ValidationError, match="alasan penolakan"):
        services.decide(d, actor=jean, verdict="tolak", note="  ")
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU
    services.decide(d, actor=jean, verdict="tolak", note="perlu angka pembanding dulu")
    d.refresh_from_db()
    assert (d.verdict, d.decision_text) == (Verdict.TOLAK, "Ditolak Jean: perlu angka pembanding dulu")


def test_move_to_meeting_keeps_waiting(jemur, yohanes, hansen):
    d = services.decide(_perkara(hansen, jemur), actor=yohanes, verdict="rapat", note="bahas bareng apoteker")
    d.refresh_from_db()
    assert (d.status, d.decider, d.verdict, d.decided_by) == (
        DecisionStatus.MENUNGGU, Decider.RAPAT_BERSAMA, "", None)
    assert d.background.endswith(f"Catatan Owner (dr. Yohanes, {local_today():%d/%m/%Y}): bahas bareng apoteker")
    note = Notification.objects.get(user=hansen, type_code="DECISION_DECIDED")
    assert note.body == "Dibawa ke rapat Kamis: bahas bareng apoteker"


def test_waiting_tasks_released_only_when_decided(jemur, yohanes, hansen):
    held = ActionItem.objects.create(clinic=jemur, title="Beli tissue", source_type="manual")
    d = _perkara(hansen, jemur)
    d.waiting_tasks.add(held)
    services.decide(d, actor=yohanes, verdict="rapat")
    assert ActionItem.objects.get(pk=held.pk).on_hold
    d2 = _perkara(hansen, jemur, title="Perkara kedua")
    held2 = ActionItem.objects.create(clinic=jemur, title="Pasang rak", source_type="manual")
    d2.waiting_tasks.add(held2)
    services.decide(d2, actor=yohanes, verdict="setuju")
    assert not ActionItem.objects.get(pk=held2.pk).on_hold


def test_dirut_decider_is_also_decided_by_owner(jemur, jean, hansen):
    d = services.decide(_perkara(hansen, jemur, decider=Decider.DIRUT), actor=jean, verdict="setuju")
    assert d.status == DecisionStatus.DITETAPKAN


@pytest.mark.parametrize("who", ["hansen", "yani"])
def test_only_owner_decides(jemur, hansen, yani, who):
    d = _perkara(hansen, jemur)
    with pytest.raises(PermissionDenied):
        services.decide(d, actor={"hansen": hansen, "yani": yani}[who], verdict="setuju")
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU


def test_owner_cannot_decide_other_or_closed_matters(jemur, yohanes, jean, hansen):
    meeting = _perkara(hansen, jemur, decider=Decider.RAPAT_BERSAMA)
    with pytest.raises(ValidationError):
        services.decide(meeting, actor=yohanes, verdict="setuju")
    first = _perkara(hansen, jemur, title="Sudah diputuskan")
    services.decide(first, actor=yohanes, verdict="setuju")
    with pytest.raises(ValidationError):
        services.decide(first, actor=jean, verdict="tolak", note="tidak")
    assert Decision.objects.get(pk=first.pk).decided_by == yohanes
    cancelled = _perkara(hansen, jemur, title="Dibatalkan")
    direktur.cancel_decision(cancelled, actor=hansen, reason="tidak relevan")
    with pytest.raises(ValidationError):
        services.decide(cancelled, actor=yohanes, verdict="setuju")
    moved = _perkara(hansen, jemur, title="Sudah ke rapat")
    services.decide(moved, actor=yohanes, verdict="rapat")
    with pytest.raises(ValidationError):
        services.decide(moved, actor=jean, verdict="setuju")
    with pytest.raises(ValidationError):
        services.decide(_perkara(hansen, jemur, title="Pilihan aneh"), actor=yohanes, verdict="nanti")


def test_decisions_awaiting_order_and_scope(jemur, yohanes, hansen):
    later = _perkara(hansen, jemur, title="Nanti", needed_by=local_today() + dt.timedelta(days=5))
    none = _perkara(hansen, jemur, title="Tanpa tenggat")
    late = _perkara(hansen, jemur, title="Terlambat")
    Decision.objects.filter(pk=late.pk).update(needed_by=local_today() - dt.timedelta(days=1))
    _perkara(hansen, jemur, title="Rapat", decider=Decider.RAPAT_BERSAMA)
    services.decide(_perkara(hansen, jemur, title="Sudah"), actor=yohanes, verdict="setuju")
    rows = services.decisions_awaiting(yohanes)
    assert [r["decision"].pk for r in rows] == [late.pk, later.pk, none.pk]
    assert rows[0]["late"] and not rows[1]["late"] and rows[0]["age_days"] == 0
    assert services.decisions_awaiting(hansen) == []


# --- Task 2: halaman dan dashboard ----------------------------------------------------


def test_owner_page_decides(client, jemur, yohanes, hansen):
    d = _perkara(hansen, jemur)
    url = reverse("owner:decision", args=[d.pk])
    client.force_login(yohanes)
    body = client.get(url).content.decode()
    for text in ("Tambah anggaran tissue", "Tissue habis tiap Sabtu.", 'value="setuju"', 'value="tolak"',
                 'value="rapat"', "Bahas di rapat Kamis"):
        assert text in body
    response = client.post(url, {"aksi": "setuju", "catatan": "oke"})
    assert response["Location"] == url
    d.refresh_from_db()
    assert d.decision_text == "Disetujui dr. Yohanes: oke"
    body = client.get(url).content.decode()
    assert "Disetujui dr. Yohanes: oke" in body and 'value="setuju"' not in body


def test_reject_without_reason_shows_error(client, jemur, yohanes, hansen):
    d = _perkara(hansen, jemur)
    client.force_login(yohanes)
    body = client.post(reverse("owner:decision", args=[d.pk]), {"aksi": "tolak", "catatan": ""}, follow=True)
    assert "Tulis alasan penolakan." in body.content.decode()
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU


def test_director_reads_but_cannot_post_and_staff_blocked(client, jemur, hansen, yani):
    d = _perkara(hansen, jemur)
    url = reverse("owner:decision", args=[d.pk])
    client.force_login(hansen)
    body = client.get(url).content.decode()
    assert "Tambah anggaran tissue" in body and 'value="setuju"' not in body
    assert client.post(url, {"aksi": "setuju"}).status_code == 403
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU
    client.force_login(yani)
    assert client.get(url).status_code == 403


def test_dashboard_card(client, jemur, yohanes, hansen):
    client.force_login(yohanes)
    assert "Menunggu keputusan Anda" not in client.get(reverse("owner:dashboard")).content.decode()
    d = _perkara(hansen, jemur)
    Decision.objects.filter(pk=d.pk).update(needed_by=local_today() - dt.timedelta(days=1))
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Menunggu keputusan Anda" in body and "Tambah anggaran tissue" in body and "Lewat tenggat" in body
    assert reverse("owner:decision", args=[d.pk]) in body
    services.decide(d, actor=yohanes, verdict="setuju")
    assert "Menunggu keputusan Anda" not in client.get(reverse("owner:dashboard")).content.decode()


# --- Gelombang perbaikan akhir (7 Okt 2026) -----------------------------------------------


@pytest.mark.parametrize("verdict", ["setuju", "tolak"])
def test_direktur_cannot_override_or_cancel_owner_verdict(jemur, yohanes, hansen, verdict):
    d = _perkara(hansen, jemur)
    services.decide(d, actor=yohanes, verdict=verdict, note="alasan")
    d.refresh_from_db()
    text, v, policy = d.decision_text, d.verdict, d.is_policy
    with pytest.raises(ValidationError, match="sudah diputuskan Owner"):
        direktur.settle_decision(d, actor=hansen, decision_text="Ganti", is_policy=True)
    with pytest.raises(ValidationError, match="sudah diputuskan Owner"):
        direktur.cancel_decision(d, actor=hansen, reason="Batal")
    d.refresh_from_db()
    assert (d.decision_text, d.verdict, d.is_policy, d.status) == (text, v, policy, DecisionStatus.DITETAPKAN)


def test_direktur_stale_object_cannot_override_owner_verdict(jemur, yohanes, hansen):
    stale = _perkara(hansen, jemur)
    services.decide(Decision.objects.get(pk=stale.pk), actor=yohanes, verdict="setuju")
    with pytest.raises(ValidationError):
        direktur.settle_decision(stale, actor=hansen, decision_text="Ganti")


def test_direktur_still_settles_and_cancels_without_verdict(jemur, hansen):
    d = direktur.settle_decision(_perkara(hansen, jemur), actor=hansen, decision_text="Ya", is_policy=True)
    assert d.status == DecisionStatus.DITETAPKAN and d.verdict == ""
    d2 = direktur.cancel_decision(_perkara(hansen, jemur, title="Lain"), actor=hansen, reason="Tidak jadi")
    assert d2.status == DecisionStatus.DIBATALKAN


def _rejected(jemur, yohanes, hansen):
    d = _perkara(hansen, jemur, title="Anggaran ditolak")
    services.decide(d, actor=yohanes, verdict="tolak", note="terlalu mahal")
    return d


def test_rejection_is_tagged_and_hides_forms(client, jemur, yohanes, hansen):
    d = _rejected(jemur, yohanes, hansen)
    client.force_login(hansen)
    listing = client.get(reverse("direktur:decisions"), {"status": "DITETAPKAN"}).content.decode()
    assert "Anggaran ditolak" in listing and "Ditolak</span>" in listing
    detail = client.get(reverse("direktur:decision_detail", args=[d.pk])).content.decode()
    assert "Ditolak</span>" in detail
    assert 'name="isi"' not in detail and 'name="alasan"' not in detail
    client.force_login(yohanes)
    assert "Ditolak</span>" in client.get(reverse("owner:decision", args=[d.pk])).content.decode()


def test_approval_is_tagged_disetujui(client, jemur, yohanes, hansen):
    d = _perkara(hansen, jemur)
    services.decide(d, actor=yohanes, verdict="setuju")
    client.force_login(yohanes)
    assert "Disetujui</span>" in client.get(reverse("owner:decision", args=[d.pk])).content.decode()


def test_rejected_decision_is_not_a_new_policy(jemur, yohanes, hansen):
    from direktur import dashboard

    ok = _perkara(hansen, jemur, title="Disetujui")
    services.decide(ok, actor=yohanes, verdict="setuju")
    Decision.objects.filter(pk=ok.pk).update(is_policy=True)
    bad = _rejected(jemur, yohanes, hansen)
    Decision.objects.filter(pk=bad.pk).update(is_policy=True)
    assert [d.title for d in dashboard.recent_policies(hansen)] == ["Disetujui"]
    assert dashboard.headline_counts(hansen)["policies"] == 1


def test_owner_reaches_decision_from_direktur_detail(client, jemur, yohanes, hansen):
    d = _perkara(hansen, jemur)
    meeting = _perkara(hansen, jemur, title="Rapat", decider=Decider.RAPAT_BERSAMA)
    client.force_login(yohanes)
    body = client.get(reverse("direktur:decision_detail", args=[d.pk])).content.decode()
    assert reverse("owner:decision", args=[d.pk]) in body and "Putuskan" in body
    body = client.get(reverse("direktur:decision_detail", args=[meeting.pk])).content.decode()
    assert reverse("owner:decision", args=[meeting.pk]) not in body
    client.force_login(hansen)
    body = client.get(reverse("direktur:decision_detail", args=[d.pk])).content.decode()
    assert reverse("owner:decision", args=[d.pk]) not in body


def test_owner_page_shows_recipients_and_cancel_reason(client, jemur, yohanes, hansen, yani):
    from core.models import TaskAssignment

    held = ActionItem.objects.create(clinic=jemur, title="Beli tissue", source_type="manual")
    TaskAssignment.objects.create(action_item=held, assignee=yani)
    other = ActionItem.objects.create(clinic=jemur, title="Pasang rak", source_type="manual")
    d = _perkara(hansen, jemur)
    d.waiting_tasks.add(held, other)
    client.force_login(yohanes)
    body = client.get(reverse("owner:decision", args=[d.pk])).content.decode()
    assert "Yani" in body and "belum ada penerima" in body and "Jemur Andayani" in body
    direktur.cancel_decision(d, actor=hansen, reason="Sudah tidak relevan")
    body = client.get(reverse("owner:decision", args=[d.pk])).content.decode()
    assert "Dibatalkan" in body and "Sudah tidak relevan" in body


@pytest.mark.parametrize("who", ["admin", "yani"])
def test_admin_and_staff_cannot_post_decision(client, jemur, hansen, yani, who):
    admin = _user(jemur, "admin1", Role.ADMIN)
    d = _perkara(hansen, jemur)
    client.force_login({"admin": admin, "yani": yani}[who])
    assert client.post(reverse("owner:decision", args=[d.pk]), {"aksi": "setuju"}).status_code == 403
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU and d.verdict == ""


def test_rapat_message_says_director_notified(client, jemur, yohanes, hansen):
    d = _perkara(hansen, jemur)
    client.force_login(yohanes)
    body = client.post(reverse("owner:decision", args=[d.pk]), {"aksi": "rapat", "catatan": "bahas"},
                       follow=True).content.decode()
    assert "Dibawa ke rapat Kamis; Direktur Operasional sudah diberi tahu." in body
    assert "Keputusan dikirim ke Direktur Operasional." not in body
