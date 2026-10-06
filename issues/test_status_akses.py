"""Siapa yang boleh mengubah status Komplain/Masukan/Kerusakan (7 Okt 2026).

Supervisor, PIC, dan Direktur Operasional di cabang itu; staf hanya pada catatan yang sedang
ditugaskan kepadanya. Staf lain, pelapor, dan Owner tidak — supaya catatan tidak keluar dari
"Belum dipilah" Inbox Direktur sebelum ditangani orang yang berwenang.
"""
import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from accounts.models import Role, User, UserRole
from issues.models import IssueStatus, IssueType
from issues.services import assign_issue, change_status, create_issue

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _complaint(clinic, user, issue_type=IssueType.KOMPLAIN):
    return create_issue(clinic=clinic, issue_type=issue_type, title="Waktu tunggu terlalu lama", user=user,
                        description="Pasien menunggu lebih dari satu jam.", reporter_source="PASIEN")


@pytest.mark.parametrize("who", ["pelapor", "staf_lain", "owner"])
def test_staff_reporter_and_owner_cannot_change_status(clinic, kasir, who):
    issue = _complaint(clinic, kasir)
    actor = {"pelapor": kasir, "staf_lain": _user(clinic, "yani", Role.STAF),
             "owner": _user(clinic, "yohanes", Role.OWNER)}[who]
    with pytest.raises(PermissionDenied):
        change_status(issue, user=actor, to_status=IssueStatus.DITINJAU)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.BARU


@pytest.mark.parametrize("roles", [(Role.SUPERVISOR,), (Role.PIC, Role.FRONT_DESK), (Role.AOM,)])
def test_supervisor_pic_and_director_can_change_status(clinic, kasir, roles):
    issue = _complaint(clinic, kasir)
    change_status(issue, user=_user(clinic, "penangan", *roles), to_status=IssueStatus.DITINJAU)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITINJAU


def test_handler_of_other_branch_cannot_change_status(clinic, clinic_b, kasir):
    issue = _complaint(clinic, kasir)
    with pytest.raises(PermissionDenied):
        change_status(issue, user=_user(clinic_b, "sup_b", Role.SUPERVISOR), to_status=IssueStatus.DITINJAU)


def test_assigned_staff_can_work_only_their_own_issue(clinic, kasir, supervisor):
    mine = _complaint(clinic, kasir)
    change_status(mine, user=supervisor, to_status=IssueStatus.DITINJAU)
    worker = _user(clinic, "yani", Role.STAF)
    assign_issue(mine, supervisor=supervisor, assignee=worker)
    mine.refresh_from_db()
    change_status(mine, user=worker, to_status=IssueStatus.DALAM_PROSES)
    change_status(mine, user=worker, to_status=IssueStatus.SELESAI, resolution_summary="Alur antrean dirapikan.")
    mine.refresh_from_db()
    assert mine.status == IssueStatus.SELESAI

    other = _complaint(clinic, kasir)
    change_status(other, user=supervisor, to_status=IssueStatus.DITINJAU)
    with pytest.raises(PermissionDenied):
        change_status(other, user=worker, to_status=IssueStatus.DITUTUP, reason="bukan tugas saya")


def test_status_post_by_plain_staff_is_forbidden_and_stays_untriaged(client, clinic, kasir):
    from reports.inbox import inbox_rows

    issue = _complaint(clinic, kasir, issue_type=IssueType.KERUSAKAN)
    director = _user(clinic, "hansen1", Role.AOM)
    client.force_login(_user(clinic, "yani", Role.STAF))
    response = client.post(reverse("issues:status", args=[issue.pk]),
                           {"status": IssueStatus.DITRIASE, "versi": issue.version})
    assert response.status_code == 403
    issue.refresh_from_db()
    assert issue.status == IssueStatus.BARU
    untriaged = [r for r in inbox_rows(director, state="belum") if r["source_id"] == issue.pk]
    assert len(untriaged) == 1


def test_status_form_hidden_from_plain_staff(client, clinic, kasir, supervisor):
    issue = _complaint(clinic, kasir)
    client.force_login(kasir)
    assert "Ubah status" not in client.get(reverse("issues:detail", args=[issue.pk])).content.decode()
    client.force_login(supervisor)
    assert "Ubah status" in client.get(reverse("issues:detail", args=[issue.pk])).content.decode()
