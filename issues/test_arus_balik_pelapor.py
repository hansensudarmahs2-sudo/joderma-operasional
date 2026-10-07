"""Tahap 3b: pelapor diberi tahu bila catatannya (Komplain/Masukan/Kerusakan) ditanggapi."""
import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from issues.models import IssueStatus, IssueType
from issues.services import add_update, change_status, create_issue
from notifications.models import Notification
from notifications.services import notify_reporter
from reports import triage
from reports.inbox import find_row

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _issue(clinic, reporter, **kw):
    return create_issue(clinic=clinic, issue_type=IssueType.KOMPLAIN, title="Waktu tunggu terlalu lama",
                        user=reporter, description="Menunggu lebih dari satu jam.",
                        reporter_source="PASIEN", **kw)


def _notifs(user):
    return Notification.objects.filter(user=user, type_code="ISSUE_RESPONSE")


def test_status_change_notifies_reporter(clinic, kasir, supervisor):
    issue = _issue(clinic, kasir)
    change_status(issue, user=supervisor, to_status=IssueStatus.DITINJAU)
    n = _notifs(kasir)
    assert n.count() == 1
    notif = n.get()
    assert notif.url == reverse("issues:detail", args=[issue.pk])
    assert issue.title in notif.title
    assert "Ditinjau" in notif.body
    assert notif.entity_ref == f"issue#{issue.pk}"


def test_note_notifies_reporter_but_not_self(clinic, kasir, supervisor):
    issue = _issue(clinic, kasir)
    add_update(issue, user=kasir, note="Tambahan dari saya sendiri")
    assert _notifs(kasir).count() == 0
    add_update(issue, user=supervisor, note="Sudah kami cek ke bagian pendaftaran")
    notif = _notifs(kasir).get()
    assert "Sudah kami cek" in notif.body


@pytest.mark.parametrize("flag", ["is_anonymous", "is_restricted"])
def test_anonymous_or_restricted_has_no_content(clinic, kasir, supervisor, flag):
    issue = _issue(clinic, kasir, **{flag: True})
    change_status(issue, user=supervisor, to_status=IssueStatus.DITINJAU, note="rahasia internal")
    notif = _notifs(kasir).get()
    assert notif.title == "Ada tanggapan pada catatan Anda"
    assert notif.body == ""
    assert notif.url == reverse("issues:detail", args=[issue.pk])


def test_inactive_or_missing_reporter_is_silent(clinic, kasir, supervisor):
    issue = _issue(clinic, kasir)
    kasir.is_active = False
    kasir.save()
    change_status(issue, user=supervisor, to_status=IssueStatus.DITINJAU)
    assert _notifs(kasir).count() == 0
    other = _issue(clinic, supervisor)
    other.created_by = None
    other.save()
    add_update(other, user=supervisor, note="tanpa pelapor")
    assert Notification.objects.filter(type_code="ISSUE_RESPONSE").count() == 0


def test_triage_gives_single_notification(clinic, kasir):
    hansen = User.objects.create_user(username="hansen1", password=PASSWORD, display_name="Hansen")
    UserRole.objects.create(user=hansen, clinic=clinic, role=Role.AOM)
    issue = _issue(clinic, kasir)
    triage.dismiss(find_row(hansen, "issue", issue.pk), actor=hansen, reason="sudah normal")
    assert _notifs(kasir).count() == 1
    assert "sudah normal" in _notifs(kasir).get().body


def test_timeline_shows_status_labels(client, clinic, kasir, supervisor):
    issue = _issue(clinic, kasir)
    change_status(issue, user=supervisor, to_status=IssueStatus.DITINJAU)
    client.login(username=supervisor.username, password=PASSWORD)
    html = client.get(reverse("issues:detail", args=[issue.pk])).content.decode()
    timeline = html.split("<h3>Timeline</h3>", 1)[1].split("</ul>", 1)[0]
    assert "Baru → <strong>Ditinjau</strong>" in timeline
    assert "DITINJAU" not in timeline


def test_notify_reporter_skips_actor(kasir):
    assert notify_reporter(kasir, actor=kasir, private=False, type_code="ISSUE_RESPONSE", subject="x",
                           entity_ref="issue#1", url_name="issues:detail", url_args=[1]) is None
    assert notify_reporter(None, actor=None, private=False, type_code="ISSUE_RESPONSE", subject="x",
                           entity_ref="issue#1", url_name="issues:detail", url_args=[1]) is None


def test_assign_notifies_reporter(clinic, kasir, supervisor):
    from issues.services import assign_issue

    issue = _issue(clinic, kasir)
    change_status(issue, user=supervisor, to_status=IssueStatus.DITINJAU)
    worker = User.objects.create_user(username="yani", password=PASSWORD, display_name="Yani")
    UserRole.objects.create(user=worker, clinic=clinic, role=Role.STAF)
    issue.refresh_from_db()
    assign_issue(issue, supervisor=supervisor, assignee=worker)
    notif = _notifs(kasir).get()  # digabung dengan notifikasi ubah status (dedupe)
    assert "Ditugaskan" in notif.body and "Yani" in notif.body


def test_mark_duplicate_notifies_reporter(clinic, kasir, supervisor):
    from issues.services import mark_duplicate

    original = _issue(clinic, supervisor)
    issue = _issue(clinic, kasir)
    mark_duplicate(issue, user=supervisor, original=original, reason="sudah dilaporkan")
    notif = _notifs(kasir).get()
    assert original.number in notif.body and "sudah dilaporkan" in notif.body
