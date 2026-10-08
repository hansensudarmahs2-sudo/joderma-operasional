"""Projects tahap 1: model, aturan izin, task project, selesai tanpa konfirmasi, batal selesai."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile

from accounts.models import Role, User, UserRole
from core import task_services as ts
from core.models import (
    ActionItem, ActionItemStatus, Attachment, Clinic, TaskAssignmentMode, TaskAssignmentStatus, TaskAudienceType,
    TaskEventType,
)
from core.photos import can_view_attachment
from notifications.models import Notification
from projects import services as ps
from projects.models import Project, ProjectStatus

pytestmark = pytest.mark.django_db

IND = TaskAssignmentMode.INDIVIDUAL
BER = TaskAssignmentMode.BERSAMA


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def clinic(db):
    return Clinic.objects.create(code="jemur", name="Jemur", open_time="14:00", close_time="22:00")


@pytest.fixture
def owner(clinic):
    return _user(clinic, "owner1", Role.OWNER)


@pytest.fixture
def aom1(clinic):
    return _user(clinic, "aom1", Role.AOM)


@pytest.fixture
def aom2(clinic):
    return _user(clinic, "aom2", Role.AOM)


@pytest.fixture
def spv(clinic):
    return _user(clinic, "spv", Role.SUPERVISOR, Role.STAF)


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
    """Dibuat aom1; leader staf A; co-leader staf B."""
    return ps.create_project(actor=aom1, name="Renovasi ruang tunggu", leader=sa, co_leaders=[sb],
                             target_date=dt.date(2026, 12, 31))


def _notes(type_code):
    return list(Notification.objects.filter(type_code=type_code))


def _recipients(type_code):
    return {n.user.username for n in _notes(type_code)}


# --- Izin ------------------------------------------------------------------------------------


def test_permission_matrix(project, owner, aom1, aom2, spv, sa, sb, sc):
    cases = {
        # user: (create, view, manage, edit, admin)
        "owner": (owner, (True, True, True, True, True)),
        "aom1": (aom1, (True, True, True, True, True)),
        "aom2": (aom2, (True, True, True, True, True)),
        "leader": (sa, (False, True, True, True, False)),
        "co_leader": (sb, (False, True, True, False, False)),
        "supervisor": (spv, (False, False, False, False, False)),
        "other_staff": (sc, (False, False, False, False, False)),
    }
    for label, (user, expected) in cases.items():
        got = (
            ps.can_create_project(user), ps.can_view_project(user, project), ps.can_manage_tasks(user, project),
            ps.can_edit_project(user, project), ps.can_admin_project(user, project),
        )
        assert got == expected, label


def test_permissions_deny_anonymous(project):
    from django.contrib.auth.models import AnonymousUser

    anon = AnonymousUser()
    assert not ps.can_create_project(anon)
    assert not ps.can_view_project(anon, project)
    assert not ps.can_manage_tasks(anon, project)
    assert not ps.can_edit_project(anon, project)
    assert not ps.can_admin_project(anon, project)
    assert not ps.user_has_projects(anon)


def test_creator_keeps_rights_even_without_role(project, aom1):
    UserRole.objects.filter(user=aom1).delete()
    aom1 = User.objects.get(pk=aom1.pk)  # buang cache peran
    assert ps.can_view_project(aom1, project) and ps.can_admin_project(aom1, project)
    assert not ps.can_create_project(aom1)


def test_user_has_projects(project, owner, aom1, sa, sb, sc, spv):
    assert ps.user_has_projects(owner) and ps.user_has_projects(aom1)
    assert ps.user_has_projects(sa) and ps.user_has_projects(sb)
    assert not ps.user_has_projects(sc) and not ps.user_has_projects(spv)
    ps.cancel_project(project, actor=aom1, note="Batal")
    assert not ps.user_has_projects(sa) and not ps.user_has_projects(sb)


def test_visible_projects(project, owner, aom2, sa, sb, sc):
    for u in (owner, aom2, sa, sb):
        assert project in ps.visible_projects(u)
    assert project not in ps.visible_projects(sc)


# --- Project: buat dan ubah ----------------------------------------------------------------


def test_create_project_notifies_leader_and_co_leaders(project, sa, sb, aom1):
    notes = {n.user.username: n for n in _notes("PROJECT_ROLE")}
    assert set(notes) == {"staf_a", "staf_b"}
    assert notes["staf_a"].title == "Anda Project leader: Renovasi ruang tunggu"
    assert notes["staf_b"].title == "Anda Co-project leader: Renovasi ruang tunggu"
    assert project.status == ProjectStatus.AKTIF and project.created_by == aom1


def test_create_project_requires_owner_or_aom_and_name(sa, sb, aom1):
    with pytest.raises(PermissionDenied):
        ps.create_project(actor=sa, name="X", leader=sb)
    with pytest.raises(ValidationError):
        ps.create_project(actor=aom1, name="   ", leader=sb)
    sb.is_active = False
    sb.save()
    with pytest.raises(ValidationError):
        ps.create_project(actor=aom1, name="X", leader=sb)


def test_create_project_actor_as_leader_not_notified_and_leader_not_duplicated(aom1, sa):
    p = ps.create_project(actor=aom1, name="Sendiri", leader=aom1, co_leaders=[sa, aom1, sa])
    assert list(p.co_leaders.all()) == [sa]
    assert _recipients("PROJECT_ROLE") == {"staf_a"}


def test_update_project_rules(project, sa, sb, sc, aom2):
    ps.update_project(project, actor=sa, description="Baru", target_date=dt.date(2027, 1, 5))
    project.refresh_from_db()
    assert project.description == "Baru" and project.target_date == dt.date(2027, 1, 5)
    ps.update_project(project, actor=aom2, description="Lagi", target_date=None)
    for denied in (sb, sc):  # co-leader tidak boleh ubah target/uraian
        with pytest.raises(PermissionDenied):
            ps.update_project(project, actor=denied, description="x", target_date=None)


def test_set_leader_only_admins_and_notifies(project, sa, sb, sc, aom1, owner):
    with pytest.raises(PermissionDenied):
        ps.set_leader(project, actor=sa, leader=sc)  # leader tidak boleh mengganti leader
    with pytest.raises(PermissionDenied):
        ps.set_leader(project, actor=sb, leader=sc)
    Notification.objects.all().delete()
    ps.set_leader(project, actor=owner, leader=sb)
    project.refresh_from_db()
    assert project.leader == sb
    assert not project.co_leaders.filter(pk=sb.pk).exists()  # tidak rangkap
    assert _recipients("PROJECT_ROLE") == {"staf_b"}
    with pytest.raises(ValidationError):
        ps.set_leader(project, actor=aom1, leader=sb)  # sudah leader


def test_add_and_remove_co_leader_rules(project, sa, sb, sc, aom2):
    Notification.objects.all().delete()
    ps.add_co_leader(project, actor=sa, user=sc)  # leader boleh
    assert _recipients("PROJECT_ROLE") == {"staf_c"}
    assert project.co_leaders.filter(pk=sc.pk).exists()
    with pytest.raises(ValidationError):
        ps.add_co_leader(project, actor=sa, user=sc)  # sudah
    with pytest.raises(ValidationError):
        ps.add_co_leader(project, actor=aom2, user=sa)  # leader tidak jadi co-leader
    with pytest.raises(PermissionDenied):
        ps.add_co_leader(project, actor=sb, user=sc)  # co-leader tidak boleh atur co-leader
    with pytest.raises(PermissionDenied):
        ps.remove_co_leader(project, actor=sb, user=sc)
    ps.remove_co_leader(project, actor=sa, user=sc)
    assert not project.co_leaders.filter(pk=sc.pk).exists()
    with pytest.raises(ValidationError):
        ps.remove_co_leader(project, actor=aom2, user=sc)  # bukan co-leader


# --- Task project ---------------------------------------------------------------------------


def _add(project, actor, *people, mode=IND, title="Cat dinding"):
    return ps.add_task(project, actor=actor, title=title, user_ids=[p.pk for p in people], mode=mode)


def test_add_task_individual_creates_item_and_assignments(project, sa, sb, sc, aom1, clinic):
    item = _add(project, aom1, sb, sc)
    assert item.source_type == "proyek" and item.source_id == project.pk
    assert item.source_label == "Project: Renovasi ruang tunggu"
    assert item.assignment_mode == IND and item.clinic == clinic and item.created_by == aom1
    assert set(item.task_assignments.values_list("assignee__username", flat=True)) == {"staf_b", "staf_c"}
    assert _recipients("TASK_ASSIGNED") == {"staf_b", "staf_c"}
    assert project.tasks().get() == item


def test_add_task_bersama_and_single_assignee(project, sa, sb, sc):
    shared = _add(project, sa, sb, sc, mode=BER, title="Cukup satu")
    assert shared.assignment_mode == BER and shared.task_assignments.count() == 2
    single = _add(project, sb, sc, title="Sendiri")
    assert single.owner == sc  # satu penerima menjadi owner (perilaku create_task)


def test_add_task_rules(project, sa, sb, sc, aom1, spv, aom2):
    with pytest.raises(PermissionDenied):
        _add(project, sc, sb)  # staf lain
    with pytest.raises(PermissionDenied):
        _add(project, spv, sb)
    with pytest.raises(ValidationError):
        ps.add_task(project, actor=sa, title="X", user_ids=[])
    with pytest.raises(ValidationError):
        ps.add_task(project, actor=sa, title="  ", user_ids=[sb.pk])
    with pytest.raises(ValidationError):
        ps.add_task(project, actor=sa, title="X", user_ids=[sb.pk], mode="LAIN")
    sc.is_active = False
    sc.save()
    with pytest.raises(ValidationError):
        _add(project, sa, sc)  # penerima tidak aktif
    ps.cancel_project(project, actor=aom1, note="Batal")
    with pytest.raises(ValidationError):
        _add(project, aom2, sb)  # project tidak aktif


def test_cancel_project_task_by_co_leader_staff(project, sa, sb, sc):
    item = _add(project, sa, sc)  # dibuat leader, dibatalkan co-leader (bukan pembuat task)
    ps.cancel_project_task(item, actor=sb, reason="Tidak jadi")
    item.refresh_from_db()
    assert item.status == ActionItemStatus.BATAL
    assert item.task_assignments.get().status == TaskAssignmentStatus.CANCELLED
    assert project.tasks().count() == 0


def test_cancel_project_task_denied_for_other_staff_and_non_project(project, sa, sb, sc, aom1):
    item = _add(project, sa, sb)
    with pytest.raises(PermissionDenied):
        ps.cancel_project_task(item, actor=sc, reason="x")
    plain = ts.create_task(clinic=item.clinic, actor=aom1, title="Biasa", audience_type=TaskAudienceType.USER,
                           user_ids=[sb.pk])
    with pytest.raises(ValidationError):
        ps.cancel_project_task(plain, actor=aom1, reason="x")


def test_can_manage_task_extended_for_project_tasks(project, sa, sb, sc, spv, owner, aom1):
    item = _add(project, aom1, sc)
    assert ts.can_manage_task(item, sa) and ts.can_manage_task(item, sb) and ts.can_manage_task(item, owner)
    assert not ts.can_manage_task(item, sc) and not ts.can_manage_task(item, spv)
    plain = ts.create_task(clinic=item.clinic, actor=aom1, title="Biasa", audience_type=TaskAudienceType.USER,
                           user_ids=[sc.pk])
    assert not ts.can_manage_task(plain, sa)  # leader tidak mengatur task non-project
    assert not ts.can_manage_task(plain, owner)  # perilaku lama tidak berubah
    item_other = ActionItem.objects.create(clinic=item.clinic, title="Yatim", source_type="proyek", source_id=99999,
                                           created_by=aom1)
    assert not ts.can_manage_task(item_other, sa)  # project hilang -> False


# --- Selesai tanpa konfirmasi -------------------------------------------------------------------


def test_submit_single_assignee_finishes_immediately(project, sa, sb, sc, aom1):
    item = _add(project, aom1, sc)
    a = item.task_assignments.get()
    Notification.objects.all().delete()
    ts.submit_assignment(a, user=sc, note="Sudah dicat")
    a.refresh_from_db()
    item.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and a.confirmed_at and a.reviewer is None
    assert item.status == ActionItemStatus.SELESAI
    events = list(item.task_events.values_list("event_type", "note"))
    assert (TaskEventType.CONFIRMED, "Selesai (task project, tanpa konfirmasi).") in events
    assert _recipients("PROJECT_TASK_DONE") == {"staf_a", "staf_b", "aom1"}  # leader, co-leader, pembuat
    assert not _notes("TASK_SUBMITTED")  # tidak ada permintaan verifikasi
    n = _notes("PROJECT_TASK_DONE")[0]
    assert n.title == "Task project selesai: Cat dinding" and "Project Renovasi ruang tunggu" in n.body


def test_submit_done_notification_skips_actor(project, sa, sb, aom1):
    item = _add(project, aom1, sa)  # penerima = leader
    Notification.objects.all().delete()
    ts.submit_assignment(item.task_assignments.get(), user=sa)
    assert _recipients("PROJECT_TASK_DONE") == {"staf_b", "aom1"}


def test_individual_with_two_assignees_needs_both(project, sb, sc, aom1):
    item = _add(project, aom1, sb, sc)
    ts.submit_assignment(item.task_assignments.get(assignee=sb), user=sb)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.DIKERJAKAN
    ts.submit_assignment(item.task_assignments.get(assignee=sc), user=sc)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI


def test_bersama_auto_claims_then_finishes_after_one(project, sb, sc, aom1):
    item = _add(project, aom1, sb, sc, mode=BER)
    mine = item.task_assignments.get(assignee=sb)
    assert mine.claimed_by_id is None
    ts.submit_assignment(mine, user=sb, note="Beres")
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI
    assert set(item.task_assignments.values_list("claimed_by__username", flat=True)) == {"staf_b"}
    assert item.task_assignments.get(assignee=sb).status == TaskAssignmentStatus.CONFIRMED
    assert item.task_events.filter(event_type=TaskEventType.CLAIMED).count() == 1
    # penerima lain tidak dapat menyelesaikan lagi
    other = item.task_assignments.get(assignee=sc)
    with pytest.raises(ValidationError):
        ts.submit_assignment(other, user=sc)


def test_bersama_other_assignee_blocked_when_already_claimed(project, sb, sc, aom1):
    item = _add(project, aom1, sb, sc, mode=BER)
    ts.claim_shared_task(item.task_assignments.get(assignee=sb), user=sb)
    with pytest.raises(ValidationError):
        ts.submit_assignment(item.task_assignments.get(assignee=sc), user=sc)
    item.refresh_from_db()
    assert item.status != ActionItemStatus.SELESAI


def test_bersama_bug_fix_applies_to_non_project_tasks(clinic, aom1, sb, sc):
    """Task bersama biasa: setelah pengambil dikonfirmasi reviewer, item harus SELESAI.

    Sebelum perbaikan, assignment penerima lain tetap OPEN sehingga item tidak pernah selesai."""
    item = ts.create_task(clinic=clinic, actor=aom1, title="Bersihkan gudang", audience_type=TaskAudienceType.USERS,
                          user_ids=[sb.pk, sc.pk], mode=BER)
    mine = item.task_assignments.get(assignee=sb)
    ts.claim_shared_task(mine, user=sb)
    mine.refresh_from_db()
    ts.submit_assignment(mine, user=sb)
    ts.confirm_assignment(mine, reviewer=aom1, rating=5)
    item.refresh_from_db()
    other = item.task_assignments.get(assignee=sc)
    assert other.status == TaskAssignmentStatus.OPEN  # kondisi yang dulu membuat item menggantung
    assert item.status == ActionItemStatus.SELESAI


def test_individual_non_project_still_needs_everyone(clinic, aom1, sb, sc):
    item = ts.create_task(clinic=clinic, actor=aom1, title="Dua orang", audience_type=TaskAudienceType.USERS,
                          user_ids=[sb.pk, sc.pk])
    a = item.task_assignments.get(assignee=sb)
    ts.submit_assignment(a, user=sb)
    ts.confirm_assignment(a, reviewer=aom1, rating=5)
    item.refresh_from_db()
    assert item.status != ActionItemStatus.SELESAI


def test_non_project_submit_unchanged(clinic, aom1, sb):
    item = ts.create_task(clinic=clinic, actor=aom1, title="Biasa", audience_type=TaskAudienceType.USER,
                          user_ids=[sb.pk])
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=sb)
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.SUBMITTED
    assert not _notes("PROJECT_TASK_DONE")


# --- Progres -------------------------------------------------------------------------------------


def test_progress_empty_partial_and_full(project, sb, sc, aom1):
    assert project.progress() == {"total": 0, "done": 0, "percent": 0, "partial": False}
    item = _add(project, aom1, sb, sc)
    assert project.progress() == {"total": 1, "done": 0, "percent": 0, "partial": False}
    ts.submit_assignment(item.task_assignments.get(assignee=sb), user=sb)
    assert project.progress() == {"total": 1, "done": 0, "percent": 50, "partial": True}
    ts.submit_assignment(item.task_assignments.get(assignee=sc), user=sc)
    assert project.progress() == {"total": 1, "done": 1, "percent": 100, "partial": False}


def test_progress_averages_tasks_ignores_cancelled_and_handles_bersama(project, sb, sc, aom1):
    done = _add(project, aom1, sb, title="A")
    _add(project, aom1, sc, title="B")
    shared = _add(project, aom1, sb, sc, mode=BER, title="C")
    cancelled = _add(project, aom1, sb, title="D")
    ps.cancel_project_task(cancelled, actor=aom1, reason="Batal")
    ts.submit_assignment(done.task_assignments.get(), user=sb)
    assert project.progress() == {"total": 3, "done": 1, "percent": 33, "partial": False}
    ts.claim_shared_task(shared.task_assignments.get(assignee=sc), user=sc)
    assert project.progress()["percent"] == 33  # diambil tapi belum selesai = 0
    ts.submit_assignment(shared.task_assignments.get(assignee=sc), user=sc)
    assert project.progress() == {"total": 3, "done": 2, "percent": 67, "partial": False}


def test_progress_individual_excludes_cancelled_assignment(project, sb, sc, aom1):
    item = _add(project, aom1, sb, sc)
    ts.cancel_assignment(item.task_assignments.get(assignee=sc), actor=aom1, reason="Keluar")
    ts.submit_assignment(item.task_assignments.get(assignee=sb), user=sb)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI
    assert project.progress() == {"total": 1, "done": 1, "percent": 100, "partial": False}  # 1 dari 1 aktif


def test_is_overdue(project):
    assert project.is_overdue(dt.date(2027, 1, 1))
    assert not project.is_overdue(dt.date(2026, 12, 31))
    project.target_date = None
    assert not project.is_overdue(dt.date(2030, 1, 1))
    project.target_date = dt.date(2020, 1, 1)
    project.status = ProjectStatus.SELESAI
    assert not project.is_overdue(dt.date(2030, 1, 1))


# --- Batal selesai (revisi) ----------------------------------------------------------------------


def test_reopen_assignment(project, sa, sb, sc, aom1):
    item = _add(project, aom1, sc)
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=sc)
    Notification.objects.all().delete()
    ps.reopen_assignment(a, actor=sb, note="Foto kurang jelas")  # co-leader staf
    a.refresh_from_db()
    item.refresh_from_db()
    assert a.status == TaskAssignmentStatus.REVISION_REQUIRED and a.revision_note == "Foto kurang jelas"
    assert a.confirmed_at is None
    assert item.status == ActionItemStatus.DIKERJAKAN
    ev = item.task_events.filter(event_type=TaskEventType.REVISION_REQUESTED).get()
    assert ev.note == "Foto kurang jelas" and ev.actor == sb
    note = _notes("TASK_REVISION")
    assert [n.user.username for n in note] == ["staf_c"]
    assert note[0].url.endswith(f"#task-{item.pk}")
    # dikerjakan ulang -> selesai lagi
    ts.submit_assignment(a, user=sc)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI


def test_reopen_assignment_rules(project, sa, sb, sc, spv, aom1):
    item = _add(project, aom1, sc)
    a = item.task_assignments.get()
    with pytest.raises(ValidationError):
        ps.reopen_assignment(a, actor=sa, note="x")  # belum selesai
    ts.submit_assignment(a, user=sc)
    with pytest.raises(ValidationError, match="Tulis catatan revisi."):
        ps.reopen_assignment(a, actor=sa, note="  ")
    for denied in (sc, spv):
        with pytest.raises(PermissionDenied):
            ps.reopen_assignment(a, actor=denied, note="x")
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED


def test_reopen_non_project_assignment_rejected(clinic, aom1, sb):
    item = ts.create_task(clinic=clinic, actor=aom1, title="Biasa", audience_type=TaskAudienceType.USER,
                          user_ids=[sb.pk])
    a = item.task_assignments.get()
    with pytest.raises(ValidationError):
        ps.reopen_assignment(a, actor=aom1, note="x")


def test_reopen_one_of_two_individual_keeps_other_done(project, sa, sb, sc, aom1):
    item = _add(project, aom1, sb, sc)
    for u in (sb, sc):
        ts.submit_assignment(item.task_assignments.get(assignee=u), user=u)
    ps.reopen_assignment(item.task_assignments.get(assignee=sb), actor=sa, note="Ulangi")
    assert project.progress()["percent"] == 50
    item.refresh_from_db()
    assert item.status == ActionItemStatus.DIKERJAKAN


# --- Tutup dan batalkan -----------------------------------------------------------------------


def test_close_project(project, sa, sb, sc, aom1, owner):
    item = _add(project, aom1, sc)
    with pytest.raises(ValidationError, match="Masih ada task yang belum selesai."):
        ps.close_project(project, actor=aom1)
    for denied in (sa, sb, sc):
        with pytest.raises(PermissionDenied):
            ps.close_project(project, actor=denied)
    ts.submit_assignment(item.task_assignments.get(), user=sc)
    ps.close_project(project, actor=owner, note="Beres")
    project.refresh_from_db()
    assert project.status == ProjectStatus.SELESAI and project.closed_by == owner and project.closed_at
    assert project.close_note == "Beres"
    with pytest.raises(ValidationError):
        ps.close_project(project, actor=aom1)  # sudah ditutup


def test_close_project_ok_with_only_cancelled_or_no_tasks(project, aom1, sb):
    item = _add(project, aom1, sb)
    ps.cancel_project_task(item, actor=aom1, reason="x")
    ps.close_project(project, actor=aom1)
    assert project.status == ProjectStatus.SELESAI


def test_cancel_project_cancels_open_tasks_and_needs_note(project, sa, sb, sc, aom1, owner):
    open_item = _add(project, aom1, sb, title="Terbuka")
    done_item = _add(project, aom1, sc, title="Selesai")
    ts.submit_assignment(done_item.task_assignments.get(), user=sc)
    with pytest.raises(ValidationError):
        ps.cancel_project(project, actor=aom1, note=" ")
    for denied in (sa, sb, sc):
        with pytest.raises(PermissionDenied):
            ps.cancel_project(project, actor=denied, note="x")
    ps.cancel_project(project, actor=owner, note="Anggaran dipotong")  # Owner bukan pembuat, bukan pemberi task
    project.refresh_from_db()
    open_item.refresh_from_db()
    done_item.refresh_from_db()
    assert project.status == ProjectStatus.DIBATALKAN and project.close_note == "Anggaran dipotong"
    assert open_item.status == ActionItemStatus.BATAL
    assert open_item.task_assignments.get().status == TaskAssignmentStatus.CANCELLED
    assert done_item.status == ActionItemStatus.SELESAI  # yang sudah selesai tetap


def test_project_helpers(project, aom1, sb):
    item = _add(project, aom1, sb)
    assert ps.is_project_item(item) and ps.project_for_item(item) == project
    plain = ActionItem.objects.create(clinic=item.clinic, title="Biasa", source_type="manual", created_by=aom1)
    assert not ps.is_project_item(plain) and ps.project_for_item(plain) is None
    lost = ActionItem.objects.create(clinic=item.clinic, title="Yatim", source_type="proyek", source_id=99999,
                                     created_by=aom1)
    assert ps.project_for_item(lost) is None


# --- Lampiran bukti ----------------------------------------------------------------------------


def _evidence(assignment, uploader):
    att = Attachment(entity_type="taskassignment", entity_id=assignment.pk, original_name="bukti.jpg",
                     mime_type="image/jpeg", size_bytes=3, uploaded_by=uploader)
    att.file.save("bukti.jpg", ContentFile(b"abc"), save=False)
    att.save()
    return att


def test_leader_staff_can_view_project_task_evidence(project, sa, sb, sc, aom1, spv, clinic):
    other = _user(clinic, "staf_d", Role.STAF)
    item = _add(project, aom1, sc)
    a = item.task_assignments.get()
    att = _evidence(a, sc)
    assert can_view_attachment(sc, att)  # penerima
    assert can_view_attachment(sa, att)  # leader staf
    assert can_view_attachment(sb, att)  # co-leader staf
    assert can_view_attachment(aom1, att)
    assert not can_view_attachment(other, att)
    event = ts.add_task_comment(item, actor=sa, note="Cek")
    ev_att = Attachment(entity_type="taskevent", entity_id=event.pk, original_name="x.pdf",
                        mime_type="application/pdf", size_bytes=3, uploaded_by=sa)
    ev_att.file.save("x.pdf", ContentFile(b"%PDF-"), save=False)
    ev_att.save()
    assert can_view_attachment(sb, ev_att)
    assert not can_view_attachment(other, ev_att)


def test_non_project_evidence_not_opened_to_project_leader(project, sa, aom1, sb, clinic):
    item = ts.create_task(clinic=clinic, actor=aom1, title="Biasa", audience_type=TaskAudienceType.USER,
                          user_ids=[sb.pk])
    att = _evidence(item.task_assignments.get(), sb)
    assert not can_view_attachment(sa, att)


# --- Penerima dicabut ----------------------------------------------------------------------------


def test_recipient_removed_after_other_confirmed_finishes_item(project, sb, sc, aom1):
    item = _add(project, aom1, sb, sc)
    ts.submit_assignment(item.task_assignments.get(assignee=sb), user=sb)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.DIKERJAKAN
    with pytest.raises(ValidationError):
        ps.close_project(project, actor=aom1)
    ts.cancel_assignment(item.task_assignments.get(assignee=sc), actor=aom1, reason="Keluar")
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI
    ps.close_project(project, actor=aom1)
    assert project.status == ProjectStatus.SELESAI


def test_non_project_individual_cancelled_plus_confirmed_finishes(clinic, aom1, sb, sc):
    item = ts.create_task(clinic=clinic, actor=aom1, title="Dua orang", audience_type=TaskAudienceType.USERS,
                          user_ids=[sb.pk, sc.pk])
    ts.cancel_assignment(item.task_assignments.get(assignee=sc), actor=aom1, reason="Keluar")
    item.refresh_from_db()
    assert item.status != ActionItemStatus.SELESAI  # belum ada yang dikonfirmasi
    a = item.task_assignments.get(assignee=sb)
    ts.submit_assignment(a, user=sb)
    ts.confirm_assignment(a, reviewer=aom1, rating=5)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI


def test_cancel_task_still_ends_batal(clinic, aom1, sb, sc):
    item = ts.create_task(clinic=clinic, actor=aom1, title="Batal", audience_type=TaskAudienceType.USERS,
                          user_ids=[sb.pk, sc.pk])
    a = item.task_assignments.get(assignee=sb)
    ts.submit_assignment(a, user=sb)
    ts.confirm_assignment(a, reviewer=aom1, rating=5)
    ts.cancel_task(item, actor=aom1, reason="Tidak jadi")
    item.refresh_from_db()
    assert item.status == ActionItemStatus.BATAL


def test_reopen_rejected_on_cancelled_task(project, sb, aom1):
    item = _add(project, aom1, sb)
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=sb)
    item.status = ActionItemStatus.BATAL
    item.save()
    with pytest.raises(ValidationError):
        ps.reopen_assignment(a, actor=aom1, note="x")


def test_add_task_rejects_non_numeric_recipient(project, aom1):
    with pytest.raises(ValidationError, match="Penerima tidak dikenali."):
        ps.add_task(project, actor=aom1, title="X", user_ids=["abc"])
