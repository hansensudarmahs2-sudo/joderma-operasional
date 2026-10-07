"""Owner sebagai penerima task project: kartu di dashboard Owner, selesai dengan bukti, percakapan, dan Tolak."""
from __future__ import annotations

import io

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from accounts.models import Role, User, UserRole
from core import task_services as ts
from core.models import (
    ActionItemStatus, Clinic, TaskAssignmentMode, TaskAssignmentStatus, TaskEventType,
)
from notifications.models import Notification
from projects import services as ps

pytestmark = pytest.mark.django_db

PASSWORD = "TestPassword123!"
IND = TaskAssignmentMode.INDIVIDUAL
BER = TaskAssignmentMode.BERSAMA


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _png(name="bukti.png"):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 30)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _messages(response) -> list[str]:
    return [str(m) for m in response.context["messages"]]


@pytest.fixture
def clinic(db):
    return Clinic.objects.create(code="jemur", name="Jemur", open_time="14:00", close_time="22:00")


@pytest.fixture
def clinic2(db):
    return Clinic.objects.create(code="citraland", name="Citraland", open_time="14:00", close_time="22:00")


@pytest.fixture
def yohanes(clinic):
    return _user(clinic, "yohanes", Role.OWNER)  # hanya punya peran di cabang 1


@pytest.fixture
def jean(clinic):
    return _user(clinic, "jean", Role.OWNER)


@pytest.fixture
def aom1(clinic):
    return _user(clinic, "aom1", Role.AOM)


@pytest.fixture
def sa(clinic):
    return _user(clinic, "staf_a", Role.STAF)


@pytest.fixture
def sb(clinic):
    return _user(clinic, "staf_b", Role.STAF)


@pytest.fixture
def sc(clinic):
    return _user(clinic, "staf_c", Role.STAF)


@pytest.fixture
def project(aom1, sa, sb):
    """Dibuat aom1; leader staf A; co-leader staf B; lintas cabang."""
    return ps.create_project(actor=aom1, name="Renovasi ruang tunggu", leader=sa, co_leaders=[sb])


def _login(client, user):
    client.force_login(user)
    return client


def _add(project, actor, *people, mode=IND, title="Pasang rak", clinic=None):
    return ps.add_task(project, actor=actor, title=title, user_ids=[u.pk for u in people], mode=mode, clinic=clinic)


def _notes(type_code, user=None):
    qs = Notification.objects.filter(type_code=type_code)
    return list(qs.filter(user=user) if user else qs)


def _recipients(type_code):
    return set(Notification.objects.filter(type_code=type_code).values_list("user__username", flat=True))


def _submit(client, a, **extra):
    data = {"catatan": "Sudah terpasang", **extra}
    return client.post(reverse("projects:my_submit", args=[a.pk]), data)


# --- Penerima ------------------------------------------------------------------------------------


def test_add_task_accepts_owner_for_clinic_without_role(project, aom1, yohanes, clinic2):
    item = _add(project, aom1, yohanes, clinic=clinic2)
    assert item.clinic_id == clinic2.pk
    a = item.task_assignments.get()
    assert a.assignee_id == yohanes.pk and a.status == TaskAssignmentStatus.OPEN


def test_add_task_accepts_both_owners_in_default_clinic(project, aom1, yohanes, jean, clinic):
    item = _add(project, aom1, yohanes, jean)
    assert set(item.task_assignments.values_list("assignee__username", flat=True)) == {"yohanes", "jean"}


def test_add_task_mixed_staff_and_owner_in_second_clinic(project, aom1, yohanes, sa, clinic2):
    # staf tanpa peran di cabang 2 tetap ditolak; Owner lolos
    with pytest.raises(ValidationError):
        _add(project, aom1, yohanes, sa, clinic=clinic2)


def test_people_marks_owner_as_recipient_everywhere(client, project, aom1, yohanes):
    from projects.views import _people

    row = next(p for p in _people() if p["user"].pk == yohanes.pk)
    assert row["clinics"] == "*"
    body = _login(client, aom1).get(reverse("projects:detail", args=[project.pk])).content.decode()
    assert f'<option value="{yohanes.pk}" data-clinics="*">' in body


# --- Kartu di dashboard Owner --------------------------------------------------------------------


def test_dashboard_card_lists_open_project_task(client, project, aom1, yohanes):
    item = _add(project, aom1, yohanes, title="Tanda tangan kontrak")
    body = _login(client, yohanes).get(reverse("owner:dashboard")).content.decode()
    assert "Tugas saya (project)" in body and 'id="tugas-project"' in body
    assert "Tanda tangan kontrak" in body and "Project: Renovasi ruang tunggu" in body
    assert reverse("projects:task_detail", args=[project.pk, item.pk]) in body
    a = item.task_assignments.get()
    for name in ("my_submit", "my_decline"):
        assert reverse(f"projects:{name}", args=[a.pk]) in body
    assert reverse("projects:my_comment", args=[item.pk]) in body


def test_dashboard_card_hidden_when_nothing_open(client, project, aom1, yohanes, jean):
    _add(project, aom1, jean)  # task milik orang lain
    assert "Tugas saya (project)" not in _login(client, yohanes).get(reverse("owner:dashboard")).content.decode()


def test_dashboard_card_hidden_after_finish_and_shows_revision_note(client, project, aom1, yohanes):
    item = _add(project, aom1, yohanes)
    a = item.task_assignments.get()
    _login(client, yohanes)
    _submit(client, a, foto=_png())
    assert "Tugas saya (project)" not in client.get(reverse("owner:dashboard")).content.decode()
    a.refresh_from_db()
    ps.reopen_assignment(a, actor=aom1, note="Foto kurang jelas")
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Tugas saya (project)" in body and "Foto kurang jelas" in body


# --- Tandai selesai ------------------------------------------------------------------------------


def test_my_submit_without_file_errors_and_changes_nothing(client, project, aom1, yohanes):
    item = _add(project, aom1, yohanes)
    a = item.task_assignments.get()
    r = _submit(_login(client, yohanes), a, next=reverse("owner:dashboard"))
    assert r.status_code == 302 and r.url == reverse("owner:dashboard")
    a.refresh_from_db()
    item.refresh_from_db()
    assert a.status == TaskAssignmentStatus.OPEN and item.status == ActionItemStatus.BARU
    r = client.post(reverse("projects:my_submit", args=[a.pk]), {"catatan": "x"}, follow=True)
    assert "Bukti wajib: lampirkan foto atau dokumen." in _messages(r)


def test_my_submit_with_png_confirms_and_notifies_leader(client, project, aom1, yohanes, sa):
    item = _add(project, aom1, yohanes)
    a = item.task_assignments.get()
    Notification.objects.all().delete()
    r = _submit(_login(client, yohanes), a, foto=_png(), next=reverse("owner:dashboard"))
    assert r.status_code == 302 and r.url == reverse("owner:dashboard")
    a.refresh_from_db()
    item.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and item.status == ActionItemStatus.SELESAI
    from core.models import Attachment

    assert Attachment.objects.filter(entity_type="taskassignment", entity_id=a.pk).exists()
    assert _recipients("PROJECT_TASK_DONE") == {"staf_a", "staf_b", "aom1"}
    r = client.get(reverse("owner:dashboard"))
    assert "Task selesai dan tercatat di project." in _messages(r)


def test_my_submit_bersama_owner_and_staff_autoclaims(client, project, aom1, yohanes, sb):
    item = _add(project, aom1, yohanes, sb, mode=BER)
    mine = item.task_assignments.get(assignee=yohanes)
    _submit(_login(client, yohanes), mine, foto=_png())
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI
    assert set(item.task_assignments.values_list("claimed_by__username", flat=True)) == {"yohanes"}
    assert item.task_assignments.get(assignee=yohanes).status == TaskAssignmentStatus.CONFIRMED


def test_my_submit_requires_post_and_login(client, project, aom1, yohanes):
    a = _add(project, aom1, yohanes).task_assignments.get()
    url = reverse("projects:my_submit", args=[a.pk])
    assert client.post(url, {}).status_code == 302  # login
    assert _login(client, yohanes).get(url).status_code == 405


def test_owner_cannot_submit_someone_elses_assignment(client, project, aom1, yohanes, jean):
    a = _add(project, aom1, jean).task_assignments.get()
    r = _submit(_login(client, yohanes), a, foto=_png())
    assert r.status_code in (403, 404)
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.OPEN


def test_my_submit_rejects_non_project_task(client, clinic, aom1, yohanes):
    from core.models import TaskAudienceType

    item = ts.create_task(clinic=clinic, actor=aom1, title="Biasa", audience_type=TaskAudienceType.USER,
                          user_ids=[yohanes.pk])
    a = item.task_assignments.get()
    r = _submit(_login(client, yohanes), a, foto=_png())
    assert r.status_code in (403, 404)
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.OPEN


# --- Percakapan ----------------------------------------------------------------------------------


def test_my_comment_creates_event_and_notifies_watchers(client, project, aom1, yohanes):
    item = _add(project, aom1, yohanes)
    Notification.objects.all().delete()
    r = _login(client, yohanes).post(reverse("projects:my_comment", args=[item.pk]),
                                     {"catatan": "Vendor minta DP", "next": reverse("owner:dashboard")})
    assert r.status_code == 302 and r.url == reverse("owner:dashboard")
    ev = item.task_events.get(event_type=TaskEventType.COMMENT)
    assert ev.note == "Vendor minta DP" and ev.actor_id == yohanes.pk
    assert {"staf_a", "aom1"} <= _recipients("TASK_COMMENT")


def test_my_comment_empty_errors(client, project, aom1, yohanes):
    item = _add(project, aom1, yohanes)
    r = _login(client, yohanes).post(reverse("projects:my_comment", args=[item.pk]), {"catatan": " "}, follow=True)
    assert not item.task_events.filter(event_type=TaskEventType.COMMENT).exists()
    assert any("kosong" in m.lower() for m in _messages(r))


def test_my_comment_denied_for_non_recipient_owner(client, project, aom1, yohanes, jean):
    item = _add(project, aom1, jean)
    r = _login(client, yohanes).post(reverse("projects:my_comment", args=[item.pk]), {"catatan": "Halo"})
    assert r.status_code in (403, 404)
    assert not item.task_events.filter(event_type=TaskEventType.COMMENT).exists()


def test_dashboard_card_shows_thread(client, project, aom1, yohanes):
    item = _add(project, aom1, yohanes)
    ts.add_task_comment(item, actor=aom1, note="Mohon dicek hari ini")
    body = _login(client, yohanes).get(reverse("owner:dashboard")).content.decode()
    assert "Mohon dicek hari ini" in body


# --- Tolak ---------------------------------------------------------------------------------------


def _decline(client, a, reason="Bentrok dengan jadwal praktik", **extra):
    return client.post(reverse("projects:my_decline", args=[a.pk]), {"alasan": reason, **extra})


def test_decline_cancels_logs_and_notifies(client, project, aom1, yohanes, sa, sb):
    item = _add(project, aom1, yohanes)
    a = item.task_assignments.get()
    Notification.objects.all().delete()
    r = _decline(_login(client, yohanes), a, next=reverse("owner:dashboard"))
    assert r.status_code == 302 and r.url == reverse("owner:dashboard")
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CANCELLED
    ev = item.task_events.get(event_type=TaskEventType.CANCELLED)
    assert ev.note == "Ditolak: Bentrok dengan jadwal praktik" and ev.metadata == {"ditolak": True}
    assert ev.actor_id == yohanes.pk and ev.assignment_id == a.pk
    assert _recipients("PROJECT_TASK_DECLINED") == {"staf_a", "staf_b", "aom1"}  # leader, co-leader, pembuat
    n = _notes("PROJECT_TASK_DECLINED", sa)[0]
    assert n.title == "Task ditolak: Pasang rak" and n.body == "Yohanes: Bentrok dengan jadwal praktik"
    assert n.url == reverse("projects:task_detail", args=[project.pk, item.pk])


def test_decline_notification_url_resolves_for_leader(client, project, aom1, yohanes, sa):
    item = _add(project, aom1, yohanes)
    _decline(_login(client, yohanes), item.task_assignments.get())
    n = _notes("PROJECT_TASK_DECLINED", sa)[0]
    assert _login(client, sa).get(n.url).status_code == 200


def test_decline_not_notifying_actor_when_creator(client, project, aom1, yohanes):
    owner_project = ps.create_project(actor=yohanes, name="Milik Owner", leader=aom1)
    item = ps.add_task(owner_project, actor=yohanes, title="Sendiri", user_ids=[yohanes.pk])
    Notification.objects.all().delete()
    _decline(_login(client, yohanes), item.task_assignments.get())
    assert _recipients("PROJECT_TASK_DECLINED") == {"aom1"}


def test_decline_reason_required(client, project, aom1, yohanes):
    a = _add(project, aom1, yohanes).task_assignments.get()
    _login(client, yohanes)
    r = client.post(reverse("projects:my_decline", args=[a.pk]), {"alasan": "  "})
    assert r.status_code == 302
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.OPEN
    r = client.post(reverse("projects:my_decline", args=[a.pk]), {"alasan": ""}, follow=True)
    assert "Tulis alasan menolak." in _messages(r)
    with pytest.raises(ValidationError):
        ps.decline_assignment(a, actor=yohanes, reason="")


def test_decline_message_on_success(client, project, aom1, yohanes):
    a = _add(project, aom1, yohanes).task_assignments.get()
    r = _login(client, yohanes).post(reverse("projects:my_decline", args=[a.pk]), {"alasan": "Tidak sempat"},
                                     follow=True)
    assert "Task ditolak; pengatur project diberi tahu." in _messages(r)


def test_staff_cannot_decline_even_via_route(client, project, aom1, sc):
    a = _add(project, aom1, sc).task_assignments.get()
    r = _decline(_login(client, sc), a)
    assert r.status_code == 403
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.OPEN
    with pytest.raises(PermissionDenied):
        ps.decline_assignment(a, actor=sc, reason="Capek")


def test_aom_cannot_decline(project, aom1, sa):
    a = _add(project, aom1, sa).task_assignments.get()
    with pytest.raises(PermissionDenied):
        ps.decline_assignment(a, actor=aom1, reason="Tidak")


def test_owner_cannot_decline_someone_elses_assignment(client, project, aom1, yohanes, jean):
    a = _add(project, aom1, jean).task_assignments.get()
    r = _decline(_login(client, yohanes), a)
    assert r.status_code in (403, 404)
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.OPEN
    with pytest.raises(PermissionDenied):
        ps.decline_assignment(a, actor=yohanes, reason="Bukan punya saya")


def test_decline_confirmed_assignment_errors(client, project, aom1, yohanes):
    a = _add(project, aom1, yohanes).task_assignments.get()
    _login(client, yohanes)
    _submit(client, a, foto=_png())
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED
    r = client.post(reverse("projects:my_decline", args=[a.pk]), {"alasan": "Menyesal"}, follow=True)
    assert _messages(r)
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED
    with pytest.raises(ValidationError):
        ps.decline_assignment(a, actor=yohanes, reason="Menyesal")


def test_decline_non_project_task_rejected(clinic, aom1, yohanes):
    from core.models import TaskAudienceType

    item = ts.create_task(clinic=clinic, actor=aom1, title="Biasa", audience_type=TaskAudienceType.USER,
                          user_ids=[yohanes.pk])
    with pytest.raises(ValidationError):
        ps.decline_assignment(item.task_assignments.get(), actor=yohanes, reason="Tidak")


def test_all_recipients_decline_item_stays_open_and_detail_shows_flag(client, project, aom1, yohanes, jean):
    item = _add(project, aom1, yohanes, jean)
    ps.decline_assignment(item.task_assignments.get(assignee=yohanes), actor=yohanes, reason="Sibuk A")
    ps.decline_assignment(item.task_assignments.get(assignee=jean), actor=jean, reason="Sibuk B")
    item.refresh_from_db()
    assert item.status == ActionItemStatus.BARU
    body = _login(client, aom1).get(reverse("projects:detail", args=[project.pk])).content.decode()
    assert "Semua penerima menolak" in body
    body = client.get(reverse("projects:task_detail", args=[project.pk, item.pk])).content.decode()
    assert "Ditolak" in body and "Sibuk A" in body and "Sibuk B" in body


def test_partial_decline_does_not_show_all_declined_flag(client, project, aom1, yohanes, sb):
    item = _add(project, aom1, yohanes, sb)
    ps.decline_assignment(item.task_assignments.get(assignee=yohanes), actor=yohanes, reason="Sibuk")
    body = _login(client, aom1).get(reverse("projects:detail", args=[project.pk])).content.decode()
    assert "Semua penerima menolak" not in body


def test_decline_after_other_confirmed_finishes_item(project, aom1, yohanes, sb):
    item = _add(project, aom1, yohanes, sb)
    ts.submit_assignment(item.task_assignments.get(assignee=sb), user=sb)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.DIKERJAKAN
    ps.decline_assignment(item.task_assignments.get(assignee=yohanes), actor=yohanes, reason="Tidak perlu saya")
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI


def test_decline_by_bersama_claimer_clears_claim(project, aom1, yohanes, sb):
    item = _add(project, aom1, yohanes, sb, mode=BER)
    ts.claim_shared_task(item.task_assignments.get(assignee=yohanes), user=yohanes)
    assert set(item.task_assignments.values_list("claimed_by__username", flat=True)) == {"yohanes"}
    ps.decline_assignment(item.task_assignments.get(assignee=yohanes), actor=yohanes, reason="Batal ikut")
    assert set(item.task_assignments.values_list("claimed_by", flat=True)) == {None}


def test_decline_writes_audit_log(project, aom1, yohanes):
    from audit.models import AuditEvent

    item = _add(project, aom1, yohanes)
    a = item.task_assignments.get()
    ps.decline_assignment(a, actor=yohanes, reason="Tidak bisa")
    ev = AuditEvent.objects.filter(entity_type="actionitem", entity_id=str(item.pk), actor=yohanes).latest("pk")
    assert ev.reason == "Tidak bisa" and "Task ditolak" in ev.entity_label


# --- Tautan notifikasi ---------------------------------------------------------------------------


def test_owner_notifications_link_to_dashboard(project, aom1, yohanes, sa):
    item = _add(project, aom1, yohanes, sa)
    n = _notes("TASK_ASSIGNED", yohanes)[0]
    assert n.url.startswith(reverse("owner:dashboard")) and "#tugas-project" in n.url
    assert _notes("TASK_ASSIGNED", sa)[0].url == reverse("core:action_items")
    ts.submit_assignment(item.task_assignments.get(assignee=yohanes), user=yohanes)
    ps.reopen_assignment(item.task_assignments.get(assignee=yohanes), actor=aom1, note="Ulangi")
    assert _notes("TASK_REVISION", yohanes)[0].url.startswith(reverse("owner:dashboard"))
    ts.add_task_comment(item, actor=aom1, note="Tolong cek")
    assert _notes("TASK_COMMENT", yohanes)[0].url.startswith(reverse("owner:dashboard"))
    assert _notes("TASK_COMMENT", sa)[0].url == reverse("core:today") + f"#task-{item.pk}"


def test_staff_revision_link_unchanged(project, aom1, sa):
    item = _add(project, aom1, sa)
    ts.submit_assignment(item.task_assignments.get(), user=sa)
    ps.reopen_assignment(item.task_assignments.get(), actor=aom1, note="Ulangi")
    assert _notes("TASK_REVISION", sa)[0].url == reverse("core:today") + f"#task-{item.pk}"


def test_owner_due_changed_notification_links_to_dashboard(project, aom1, yohanes):
    import datetime as dt

    item = _add(project, aom1, yohanes)
    Notification.objects.all().delete()
    ts._notify_task([yohanes], actor=aom1, item=item, type_code="TASK_DUE_CHANGED", title="t", body="b",
                    to_staff=True)
    assert _notes("TASK_DUE_CHANGED", yohanes)[0].url.startswith(reverse("owner:dashboard"))


# --- Persona tetap membatasi core ----------------------------------------------------------------


def test_owner_still_blocked_from_core_today_and_submit(client, project, aom1, yohanes):
    a = _add(project, aom1, yohanes).task_assignments.get()
    _login(client, yohanes)
    assert client.get(reverse("core:today")).status_code == 403
    assert client.post(reverse("core:assignment_submit", args=[a.pk]), {"foto": _png()}).status_code == 403


# --- Tinjauan: halaman task Direktur, AOM, jejak, tautan --------------------------------------


def test_direktur_task_page_for_owner_uses_project_route_only(client, project, aom1, yohanes):
    import re

    item = _add(project, aom1, yohanes)
    a = item.task_assignments.get()
    r = _login(client, yohanes).get(reverse("direktur:task_detail", args=[item.pk]))
    body = r.content.decode()
    assert reverse("core:assignment_submit", args=[a.pk]) not in body
    assert reverse("core:assignment_progress", args=[a.pk]) not in body
    assert "Buka di Dashboard (Tugas saya)" in body and reverse("owner:dashboard") + "#tugas-project" in body
    form = re.search(r'<form method="post"[^>]*action="([^"]+)"[^>]*enctype', body)
    assert form and form.group(1) == reverse("projects:my_submit", args=[a.pk])
    assert re.search(r'data-photo="1" required', body)
    _submit(client, a, foto=_png(), next=reverse("direktur:task_detail", args=[item.pk]))
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED


def test_direktur_task_page_owner_has_no_submit_on_non_project_task(client, clinic, aom1, yohanes):
    from core.models import TaskAudienceType

    item = ts.create_task(clinic=clinic, actor=aom1, title="Biasa", audience_type=TaskAudienceType.USER,
                          user_ids=[yohanes.pk])
    a = item.task_assignments.get()
    body = _login(client, yohanes).get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert reverse("core:assignment_submit", args=[a.pk]) not in body
    assert reverse("core:assignment_progress", args=[a.pk]) not in body


def test_decline_notifies_active_aom_too(project, aom1, yohanes, clinic):
    aom2 = _user(clinic, "aom2", Role.AOM)
    item = _add(project, aom1, yohanes)
    Notification.objects.all().delete()
    ps.decline_assignment(item.task_assignments.get(), actor=yohanes, reason="Tidak bisa")
    assert _recipients("PROJECT_TASK_DECLINED") == {"staf_a", "staf_b", "aom1", "aom2"}
    assert len(_notes("PROJECT_TASK_DECLINED", aom2)) == 1


def test_owner_comment_does_not_overwrite_watcher_notification(project, aom1, yohanes, jean):
    project.co_leaders.add(jean)  # jean pengamat sekaligus penerima
    item = _add(project, aom1, yohanes, jean)
    Notification.objects.all().delete()
    ts.add_task_comment(item, actor=yohanes, note="Halo")
    notes = _notes("TASK_COMMENT", jean)
    assert len(notes) == 1 and notes[0].title.startswith("Balasan di task")
    assert notes[0].url == reverse("direktur:task_detail", args=[item.pk])


def test_aom_plus_owner_recipient_keeps_core_links(project, aom1, clinic):
    both = _user(clinic, "ganda", Role.OWNER, Role.AOM)
    item = _add(project, aom1, both)
    assert _notes("TASK_ASSIGNED", both)[0].url == reverse("core:action_items")
    ts.add_task_comment(item, actor=aom1, note="Cek")
    assert _notes("TASK_COMMENT", both)[0].url == reverse("core:today") + f"#task-{item.pk}"


def test_owner_submit_writes_no_presence_stamp_but_staff_does(client, project, aom1, yohanes, sc):
    from jejak.models import PresenceStamp

    a = _add(project, aom1, yohanes).task_assignments.get()
    _submit(_login(client, yohanes), a, foto=_png())
    assert not PresenceStamp.objects.filter(user=yohanes).exists()
    b = _add(project, aom1, sc, title="Staf").task_assignments.get()
    _login(client, sc).post(reverse("core:assignment_submit", args=[b.pk]), {"foto": _png()})
    assert PresenceStamp.objects.filter(user=sc, event="AJUKAN").exists()
