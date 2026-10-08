"""Fase 5: view layer untuk aksi task/delegasi (bahasa tindakan jelas, PRD 13/14).

Menguji bahwa 'Ajukan selesai' (submit_assignment) dan 'Konfirmasi selesai'/
'Minta revisi' (confirm_assignment/request_revision) adalah view terpisah
dengan proteksi server-side yang sama seperti di core.task_services, dan
bahwa direct-URL access oleh pihak yang tidak berwenang menghasilkan 403.
"""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, UserRole
from core.models import TaskAssignmentStatus
from core.task_services import create_task, submit_assignment
from core.models import TaskAudienceType

pytestmark = pytest.mark.django_db


def test_assignee_can_submit_via_view(client, role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Ajukan via view",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()

    client.login(username="a_staf", password="TestPassword123!")
    response = client.post(
        reverse("core:assignment_submit", args=[assignment.pk]), {"catatan": "Selesai dikerjakan"}
    )
    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED


def test_assignee_cannot_confirm_own_submission_via_view(client, role_branch_matrix):
    """Bahasa tindakan jelas: tombol 'Konfirmasi selesai' tidak boleh dipakai penerima sendiri."""
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Tidak boleh konfirmasi sendiri",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=assignee)

    client.login(username="a_staf", password="TestPassword123!")
    response = client.post(reverse("core:assignment_confirm", args=[assignment.pk]))
    # confirm_assignment melempar PermissionDenied -> 403 (bukan pesan flash biasa).
    assert response.status_code == 403
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED


def test_reviewer_can_confirm_via_view(client, role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Konfirmasi via view",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=assignee)

    client.login(username="a_supervisor", password="TestPassword123!")
    response = client.post(reverse("core:assignment_confirm", args=[assignment.pk]), {"bintang": "5"})
    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.CONFIRMED


def test_reviewer_can_request_revision_via_view(client, role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Revisi via view",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=assignee)

    client.login(username="a_supervisor", password="TestPassword123!")
    response = client.post(
        reverse("core:assignment_revision", args=[assignment.pk]), {"catatan": "Lengkapi foto"}
    )
    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.REVISION_REQUIRED
    assert assignment.revision_note == "Lengkapi foto"


def test_cross_clinic_user_cannot_submit_assignment_via_direct_url(client, role_branch_matrix):
    """Direct URL access aman: user cabang lain tidak dapat mengakses assignment cabang lain."""
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Lintas cabang",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()

    client.login(username="b_staf", password="TestPassword123!")
    response = client.post(reverse("core:assignment_submit", args=[assignment.pk]))
    assert response.status_code == 403
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.OPEN


def test_unauthenticated_cannot_submit_assignment(client, role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Tanpa login",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()
    response = client.post(reverse("core:assignment_submit", args=[assignment.pk]))
    assert response.status_code == 302  # redirect ke login, bukan 200/leak


def test_action_items_page_shows_distinct_submit_and_confirm_labels(client, role_branch_matrix):
    """Gate Fase 5: 'Ajukan selesai' dan 'Konfirmasi selesai' tampil terpisah, tidak tertukar."""
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Cek label tombol",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()

    client.login(username="a_staf", password="TestPassword123!")
    response = client.get(reverse("core:action_items"))
    assert response.status_code == 200
    assert "Ajukan selesai" in response.content.decode()
    assert "Konfirmasi selesai" not in response.content.decode()

    submit_assignment(assignment, user=assignee)
    client.login(username="a_supervisor", password="TestPassword123!")
    response = client.get(reverse("core:action_items"))
    body = response.content.decode()
    assert "Konfirmasi selesai" in body
    assert "Minta revisi" in body
