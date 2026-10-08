"""Arus balik staf ↔ Direktur pada task (tahap 3a, 7 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import (
    ActionItem, ActionItemStatus, Clinic, TaskAssignmentStatus, TaskAudienceType, TaskEventType, local_today,
)
from core import task_services as ts
from notifications.models import Notification

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
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def rina(jemur):
    return _user(jemur, "rina", Role.AOM, display_name="Rina")


@pytest.fixture
def sinta(jemur):
    return _user(jemur, "sinta", Role.SUPERVISOR, Role.STAF, display_name="Sinta")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.STAF, display_name="Desy")


@pytest.fixture
def yani(jemur):
    return _user(jemur, "yani", Role.STAF, display_name="Yani")


def _task(actor, clinic, *people, title="Ganti filter AC"):
    ids = [p.pk for p in people]
    audience = TaskAudienceType.USER if len(ids) == 1 else TaskAudienceType.USERS
    return ts.create_task(clinic=clinic, actor=actor, title=title, audience_type=audience, user_ids=ids)


def _notes(type_code):
    return {n.user.username: n for n in Notification.objects.filter(type_code=type_code)}


# --- Task 1: aturan dan notifikasi --------------------------------------------------------


def test_progress_notifies_creator_and_all_directors(jemur, hansen, rina, sinta, desy):
    item = _task(sinta, jemur, desy)
    ts.report_progress(item.task_assignments.get(), user=desy, note="Vendor dihubungi")
    notes = _notes("TASK_PROGRESS")
    assert set(notes) == {"sinta", "hansen1", "rina"}
    assert notes["hansen1"].url == reverse("direktur:task_detail", args=[item.pk])
    assert "Ganti filter AC" in notes["sinta"].title


def test_progress_no_duplicate_when_creator_is_director(jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    ts.report_progress(item.task_assignments.get(), user=desy, note="Mulai")
    assert Notification.objects.filter(type_code="TASK_PROGRESS", user=hansen).count() == 1


def test_staff_reply_to_watchers_and_director_comment_to_active_recipients(jemur, hansen, sinta, desy, yani):
    item = _task(sinta, jemur, desy, yani)
    ts.cancel_assignment(item.task_assignments.get(assignee=yani), actor=sinta, reason="dipindah")
    ts.add_task_comment(item, actor=desy, note="Boleh pakai vendor lama?")
    assert set(_notes("TASK_COMMENT")) == {"sinta", "hansen1"}
    Notification.objects.all().delete()
    ts.add_task_comment(item, actor=hansen, note="Boleh, maksimal Rp200 ribu")
    notes = _notes("TASK_COMMENT")
    assert set(notes) == {"desy"}  # yani dibatalkan; sinta pemberi tugas, bukan penerima
    assert notes["desy"].url == reverse("core:today") + f"#task-{item.pk}"


def test_blocker_validation(jemur, hansen, desy, yani):
    a = _task(hansen, jemur, desy).task_assignments.get()
    with pytest.raises(ValidationError):
        ts.report_blocker(a, user=desy, reason="  ")
    with pytest.raises(ValidationError):
        ts.report_blocker(a, user=desy, reason="Vendor telat", proposed_due=local_today() - dt.timedelta(days=1))
    with pytest.raises(PermissionDenied):
        ts.report_blocker(a, user=yani, reason="Bukan tugas saya")
    item = ActionItem.objects.get(pk=a.action_item_id)
    assert not item.is_blocked and not item.task_events.filter(event_type=TaskEventType.KENDALA).exists()


def test_blocker_marks_task_and_notifies(jemur, hansen, sinta, desy):
    item = _task(sinta, jemur, desy)
    proposed = local_today() + dt.timedelta(days=3)
    ts.report_blocker(item.task_assignments.get(), user=desy, reason="Vendor baru bisa Jumat", proposed_due=proposed)
    item.refresh_from_db()
    assert item.is_blocked and item.blocked_by == desy and item.blocked_reason == "Vendor baru bisa Jumat"
    local_due = dt.datetime.combine(proposed, dt.time(21, 0))
    from django.utils import timezone
    assert timezone.localtime(item.proposed_due_at).replace(tzinfo=None) == local_due
    event = item.task_events.get(event_type=TaskEventType.KENDALA)
    assert event.note == f"Vendor baru bisa Jumat · usul target {proposed:%d/%m/%Y}"
    assert set(_notes("TASK_BLOCKED")) == {"sinta", "hansen1"}


def test_blocker_refused_after_submit(jemur, hansen, desy):
    a = _task(hansen, jemur, desy).task_assignments.get()
    ts.submit_assignment(a, user=desy, note="Selesai")
    a.refresh_from_db()
    with pytest.raises(ValidationError):
        ts.report_blocker(a, user=desy, reason="Telat")


def test_progress_clears_blocked(jemur, hansen, desy):
    a = _task(hansen, jemur, desy).task_assignments.get()
    ts.report_blocker(a, user=desy, reason="Menunggu sparepart")
    ts.report_progress(a, user=desy, note="Sparepart datang")
    item = ActionItem.objects.get(pk=a.action_item_id)
    assert not item.is_blocked and item.blocked_at is None and item.blocked_reason == ""


def test_approve_proposed_due(jemur, hansen, sinta, desy):
    item = _task(sinta, jemur, desy)
    proposed = local_today() + dt.timedelta(days=2)
    ts.report_blocker(item.task_assignments.get(), user=desy, reason="Vendor telat", proposed_due=proposed)
    Notification.objects.all().delete()
    item.refresh_from_db()
    with pytest.raises(PermissionDenied):
        ts.approve_proposed_due(item, actor=desy)
    expected = item.proposed_due_at
    ts.approve_proposed_due(item, actor=hansen)
    item.refresh_from_db()
    assert item.due_at == expected and not item.is_blocked and item.proposed_due_at is None
    assert item.task_events.filter(event_type=TaskEventType.TARGET_DIUBAH, actor=hansen).exists()
    note = Notification.objects.get(type_code="TASK_DUE_CHANGED")
    assert note.user == desy and note.url == reverse("core:today") + f"#task-{item.pk}"
    with pytest.raises(ValidationError):
        ts.approve_proposed_due(item, actor=hansen)


def test_approve_proposed_due_expected_due(jemur, hansen, sinta, desy):
    item = _task(sinta, jemur, desy)
    a = item.task_assignments.get()
    ts.report_blocker(a, user=desy, reason="Vendor telat", proposed_due=local_today() + dt.timedelta(days=2))
    item.refresh_from_db()
    seen = item.proposed_due_at
    old_due = item.due_at
    ts.report_blocker(a, user=desy, reason="Vendor makin telat", proposed_due=local_today() + dt.timedelta(days=5))
    item.refresh_from_db()
    with pytest.raises(ValidationError, match="sudah berubah"):
        ts.approve_proposed_due(item, actor=hansen, expected_due=seen.isoformat())
    item.refresh_from_db()
    assert item.is_blocked and item.due_at == old_due and item.proposed_due_at != seen
    ts.approve_proposed_due(item, actor=hansen, expected_due=item.proposed_due_at.isoformat())
    item.refresh_from_db()
    assert not item.is_blocked and item.due_at is not None


def test_finish_and_cancel_clear_blocked(jemur, hansen, desy):
    done = _task(hansen, jemur, desy, title="Selesai")
    a = done.task_assignments.get()
    ts.report_blocker(a, user=desy, reason="Telat")
    ts.submit_assignment(a, user=desy, note="Beres")
    ts.confirm_assignment(ActionItem.objects.get(pk=done.pk).task_assignments.get(), reviewer=hansen, rating=5)
    done.refresh_from_db()
    assert done.status == ActionItemStatus.SELESAI and done.blocked_at is None
    cancelled = _task(hansen, jemur, desy, title="Batal")
    ts.report_blocker(cancelled.task_assignments.get(), user=desy, reason="Telat")
    ts.cancel_task(ActionItem.objects.get(pk=cancelled.pk), actor=hansen, reason="Tidak perlu")
    cancelled.refresh_from_db()
    assert cancelled.blocked_at is None


def test_old_tasks_not_blocked(jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    assert not item.is_blocked and item.blocked_reason == ""


# --- Task 2: kartu staf -----------------------------------------------------------------


def test_staff_card_has_thread_and_blocker(client, jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    ts.report_progress(item.task_assignments.get(), user=desy, note="Mulai dikerjakan")
    ts.add_task_comment(item, actor=hansen, note="Tolong foto hasilnya")
    client.force_login(desy)
    body = client.get(reverse("core:today")).content.decode()
    assert f'id="task-{item.pk}"' in body and "Percakapan (2)" in body and "Ada kendala" in body
    assert body.index("Mulai dikerjakan") < body.index("Tolong foto hasilnya")


def test_staff_posts_blocker_and_sees_label(client, jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    a = item.task_assignments.get()
    client.force_login(desy)
    target = (local_today() + dt.timedelta(days=2)).isoformat()
    client.post(reverse("core:assignment_blocker", args=[a.pk]), {"alasan": "Vendor telat", "target": target})
    item.refresh_from_db()
    assert item.is_blocked and item.proposed_due_at is not None
    assert "Terhambat" in client.get(reverse("core:today")).content.decode()


def test_blocker_bad_date_and_missing_reason_show_errors(client, jemur, hansen, desy):
    a = _task(hansen, jemur, desy).task_assignments.get()
    client.force_login(desy)
    body = client.post(reverse("core:assignment_blocker", args=[a.pk]), {"alasan": "x", "target": "31-12-2026"},
                       follow=True).content.decode()
    assert "Format tanggal target tidak valid." in body
    body = client.post(reverse("core:assignment_blocker", args=[a.pk]), {"alasan": ""}, follow=True).content.decode()
    assert "Tulis kendalanya." in body
    assert not ActionItem.objects.get(pk=a.action_item_id).is_blocked


def test_staff_reply_from_card(client, jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    client.force_login(desy)
    client.post(reverse("core:task_comment", args=[item.pk]), {"catatan": "Boleh pakai vendor lama?"})
    assert item.task_events.filter(event_type=TaskEventType.COMMENT, actor=desy).exists()
    assert Notification.objects.filter(user=hansen, type_code="TASK_COMMENT").exists()


def test_non_recipient_cannot_post_blocker_or_reply(client, jemur, hansen, desy, yani):
    item = _task(hansen, jemur, desy)
    client.force_login(yani)
    assert client.post(reverse("core:assignment_blocker", args=[item.task_assignments.get().pk]),
                       {"alasan": "x"}).status_code == 403
    assert client.post(reverse("core:task_comment", args=[item.pk]), {"catatan": "x"}).status_code == 403
    assert not item.task_events.filter(event_type__in=[TaskEventType.KENDALA, TaskEventType.COMMENT]).exists()
