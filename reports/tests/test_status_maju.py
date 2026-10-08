"""Status catatan staf maju otomatis saat semua task hasil pilah selesai (PO 7 Okt 2026)."""
from __future__ import annotations

import pytest

from accounts.models import Role, User, UserRole
from core.models import ActionItem, ActionItemStatus, Clinic
from core.task_services import cancel_task, close_task, confirm_assignment, submit_assignment
from issues.models import Issue, IssueStatus, IssueType, IssueUpdate
from issues.services import change_status, create_issue
from notifications.models import Notification
from reports import triage
from reports.followup import NOTE, advance_source_from_tasks
from reports.inbox import find_row
from reports.models import Laporan, LaporanUpdate, ReportStatus
from reports.services import create_laporan

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="JC", name="Joderma Citraland")


@pytest.fixture
def people(jemur, citraland):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM),
        "yohanes": _user(jemur, "yohanes", Role.OWNER),
        "heni": _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT, Role.STAF),
        "yani": _user(jemur, "yani", Role.PERAWAT, Role.STAF),
        "regita": _user(citraland, "regita", Role.SUPERVISOR, Role.STAF),
    }


def _issue(clinic, reporter, issue_type, title="Waktu tunggu lama"):
    return create_issue(clinic=clinic, issue_type=issue_type, title=title, user=reporter,
                        description="Uraian.", reporter_source="PASIEN")


def _assign(people, clinic, source_type, source, title="Perbaiki alur", who="yani"):
    h = people["hansen"]
    t = triage.assign(find_row(h, source_type, source.pk), actor=h, clinic=clinic, title=title,
                      target=f"user:{people[who].pk}")
    return t.task


def _finish(task, people, who="yani", note="Sudah beres di lapangan."):
    a = task.task_assignments.get()
    submit_assignment(a, user=people[who], note=note)
    confirm_assignment(a, reviewer=people["hansen"], rating=5)


def _responses(user, type_code="ISSUE_RESPONSE"):
    return list(Notification.objects.filter(user=user, type_code=type_code))


def _two_branch_issue(people, jemur, citraland, title="Musik"):
    from direktur.views import branch_targets

    h = people["hansen"]
    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN, title)
    pairs = branch_targets({"cabang": "semua", f"penerima_{jemur.pk}": f"user:{people['yani'].pk}",
                            f"penerima_{citraland.pk}": f"user:{people['regita'].pk}"}, [jemur, citraland])
    triage.assign(find_row(h, "issue", issue.pk), actor=h, title="Pasang musik", targets=pairs)
    first, second = ActionItem.objects.filter(source_type="issue", source_id=issue.pk).order_by("clinic_id")
    return issue, first, second


def test_komplain_selesai_with_summary_notes_and_single_notification(people, jemur):
    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN)
    task = _assign(people, jemur, "issue", issue)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITUGASKAN
    _finish(task, people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI
    assert 'task "Perbaiki alur"' in issue.resolution_summary
    assert "Yani" in issue.resolution_summary and "Sudah beres di lapangan." in issue.resolution_summary
    auto = list(IssueUpdate.objects.filter(issue=issue, note=NOTE))
    assert [u.status for u in auto] == [IssueStatus.DALAM_PROSES, IssueStatus.SELESAI]
    assert all(u.author == people["hansen"] for u in auto)
    notes = _responses(people["heni"])
    assert len(notes) == 1 and "Selesai" in notes[0].body


def test_kerusakan_goes_to_selesai_not_diverifikasi(people, jemur):
    issue = _issue(jemur, people["heni"], IssueType.KERUSAKAN, "AC bocor")
    _finish(_assign(people, jemur, "issue", issue), people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI
    assert issue.resolution_summary


def test_masukan_issue_goes_to_diterapkan(people, jemur):
    issue = _issue(jemur, people["heni"], IssueType.MASUKAN, "Musik ruang tunggu")
    task = _assign(people, jemur, "issue", issue)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DIPERTIMBANGKAN
    _finish(task, people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITERAPKAN
    assert [u.status for u in IssueUpdate.objects.filter(issue=issue, note=NOTE)] == [
        IssueStatus.DIRENCANAKAN, IssueStatus.DITERAPKAN]
    assert issue.resolution_summary == ""


def test_laporan_goes_to_resolved(people, jemur):
    laporan = create_laporan(clinic=jemur, user=people["heni"], title="Tissue habis", description="Usul.")
    _finish(_assign(people, jemur, "laporan", laporan), people)
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.RESOLVED
    assert LaporanUpdate.objects.filter(laporan=laporan, note=NOTE, status=ReportStatus.RESOLVED).exists()
    notes = _responses(people["heni"], "LAPORAN_RESPONSE")
    assert len(notes) == 1 and "Selesai" in notes[0].body


def test_two_branches_advance_only_when_last_done(people, jemur, citraland):
    issue, first, second = _two_branch_issue(people, jemur, citraland)
    _finish(first, people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITUGASKAN
    _finish(second, people, who="regita")
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI
    assert issue.resolution_summary.count("Diselesaikan lewat task") == 2


def test_close_task_path(people, jemur):
    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN)
    task = _assign(people, jemur, "issue", issue)
    close_task(task, actor=people["hansen"], note="ditangani langsung", rating=5)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI
    assert "ditangani langsung" in issue.resolution_summary


def test_cancel_remaining_task_advances_but_all_cancelled_does_not(people, jemur, citraland):
    h = people["hansen"]
    issue, first, second = _two_branch_issue(people, jemur, citraland)
    _finish(first, people)
    cancel_task(second, actor=h, reason="tidak perlu di cabang ini")
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI

    other = _issue(jemur, people["heni"], IssueType.KOMPLAIN, "Lain")
    task = _assign(people, jemur, "issue", other)
    cancel_task(task, actor=h, reason="batal")
    other.refresh_from_db()
    assert other.status == IssueStatus.DITUGASKAN


def test_existing_resolution_summary_is_kept(people, jemur):
    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN)
    issue.resolution_summary = "Ringkasan manual."
    issue.save()
    _finish(_assign(people, jemur, "issue", issue), people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI and issue.resolution_summary == "Ringkasan manual."


def test_already_closed_or_past_target_is_untouched(people, jemur):
    h = people["hansen"]
    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN)
    task = _assign(people, jemur, "issue", issue)
    Issue.objects.filter(pk=issue.pk).update(resolution_summary="Manual.")
    issue.refresh_from_db()
    for status in (IssueStatus.DALAM_PROSES, IssueStatus.SELESAI, IssueStatus.DITUTUP):
        change_status(issue, user=h, to_status=status, reason="selesai")
    before = IssueUpdate.objects.filter(issue=issue).count()
    _finish(task, people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITUTUP
    assert IssueUpdate.objects.filter(issue=issue).count() == before

    laporan = create_laporan(clinic=jemur, user=people["heni"], title="Tissue", description="x")
    ltask = _assign(people, jemur, "laporan", laporan)
    Laporan.objects.filter(pk=laporan.pk).update(status=ReportStatus.CLOSED)
    _finish(ltask, people)
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.CLOSED


def test_owner_confirming_directors_task_still_advances(people, jemur):
    h, y = people["hansen"], people["yohanes"]
    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN)
    task = triage.assign(find_row(h, "issue", issue.pk), actor=h, clinic=jemur, title="Telepon pasien",
                         target=f"user:{h.pk}").task
    a = task.task_assignments.get()
    submit_assignment(a, user=h, note="Pasien sudah ditelepon.")
    confirm_assignment(a, reviewer=y, rating=5)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI
    assert "Pasien sudah ditelepon." in issue.resolution_summary
    assert IssueUpdate.objects.filter(issue=issue, note=NOTE, author=y).exists()


def test_task_without_source_or_missing_source_does_nothing(people, jemur):
    h = people["hansen"]
    plain = ActionItem.objects.create(clinic=jemur, title="Tanpa sumber", status=ActionItemStatus.SELESAI)
    advance_source_from_tasks(plain, actor=h)
    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN)
    task = _assign(people, jemur, "issue", issue)
    Issue.objects.filter(pk=issue.pk).delete()
    _finish(task, people)  # tidak boleh error
    assert not Issue.objects.filter(pk=issue.pk).exists()
    assert Laporan.objects.count() == 0


def test_already_selesai_komplain_and_resolved_laporan_stay(people, jemur):
    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN)
    task = _assign(people, jemur, "issue", issue)
    Issue.objects.filter(pk=issue.pk).update(status=IssueStatus.SELESAI, resolution_summary="Manual.")
    before = IssueUpdate.objects.filter(issue=issue).count()
    _finish(task, people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI
    assert IssueUpdate.objects.filter(issue=issue).count() == before

    laporan = create_laporan(clinic=jemur, user=people["heni"], title="Tissue", description="x")
    ltask = _assign(people, jemur, "laporan", laporan)
    Laporan.objects.filter(pk=laporan.pk).update(status=ReportStatus.RESOLVED)
    before = LaporanUpdate.objects.filter(laporan=laporan).count()
    _finish(ltask, people)
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.RESOLVED
    assert LaporanUpdate.objects.filter(laporan=laporan).count() == before


@pytest.mark.parametrize("start", [IssueStatus.DITRIASE, IssueStatus.MENUNGGU_VENDOR])
def test_kerusakan_reaches_selesai_from_other_starting_points(people, jemur, start):
    issue = _issue(jemur, people["heni"], IssueType.KERUSAKAN, "AC bocor")
    task = _assign(people, jemur, "issue", issue)
    Issue.objects.filter(pk=issue.pk).update(status=start)
    _finish(task, people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI


@pytest.mark.parametrize("flag", ["is_anonymous", "is_restricted"])
def test_private_komplain_advances_with_content_free_notification(people, jemur, flag):
    issue = create_issue(clinic=jemur, issue_type=IssueType.KOMPLAIN, title="Rahasia", user=people["heni"],
                         description="Uraian.", reporter_source="PASIEN", **{flag: True})
    _finish(_assign(people, jemur, "issue", issue), people)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.SELESAI
    (notif,) = _responses(people["heni"])
    assert notif.title == "Ada tanggapan pada catatan Anda" and notif.body == ""


def test_validation_error_mid_walk_does_not_break_confirmation(people, jemur, monkeypatch):
    from django.core.exceptions import ValidationError

    import issues.services as issue_services
    from core.models import TaskAssignmentStatus

    def boom(*args, **kwargs):
        raise ValidationError("gagal")

    issue = _issue(jemur, people["heni"], IssueType.KOMPLAIN)
    task = _assign(people, jemur, "issue", issue)
    monkeypatch.setattr(issue_services, "_apply_status", boom)
    _finish(task, people)
    task.refresh_from_db()
    assert task.status == ActionItemStatus.SELESAI
    assert task.task_assignments.get().status == TaskAssignmentStatus.CONFIRMED
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITUGASKAN
