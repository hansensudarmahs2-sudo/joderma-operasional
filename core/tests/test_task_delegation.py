from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import PicAssignment, PicFunction, Role, UserRole
from core.models import ActionItemStatus, TaskAssignmentMode, TaskAssignmentStatus, TaskAudienceType
from core.task_services import (
    confirm_assignment,
    create_task,
    request_revision,
    send_task,
    submit_assignment,
)

pytestmark = pytest.mark.django_db


def test_create_task_to_multiple_users_snapshots_recipients(role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    a_staf = role_branch_matrix["cabang_a"]["staf"]
    a_perawat = role_branch_matrix["cabang_a"]["perawat"]

    item = create_task(
        clinic=clinic,
        actor=role_branch_matrix["cabang_a"]["supervisor"],
        title="Cek area tunggu",
        audience_type=TaskAudienceType.USERS,
        user_ids=[a_staf.pk, a_perawat.pk],
    )

    assert item.task_assignments.count() == 2
    assert item.audience_snapshot.audience_type == TaskAudienceType.USERS
    assert {r["username"] for r in item.audience_snapshot.recipients} == {"a_staf", "a_perawat"}


def test_resending_task_does_not_duplicate_assignments(role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    user = role_branch_matrix["cabang_a"]["staf"]
    item = create_task(
        clinic=clinic,
        actor=role_branch_matrix["cabang_a"]["supervisor"],
        title="Cek display",
        audience_type=TaskAudienceType.USER,
        user_ids=[user.pk],
    )

    send_task(
        item,
        actor=role_branch_matrix["cabang_a"]["supervisor"],
        audience_type=TaskAudienceType.USER,
        user_ids=[user.pk],
    )

    assert item.task_assignments.count() == 1


def test_task_to_empty_pic_function_fails_safely(role_branch_matrix):
    clinic = role_branch_matrix["cabang_b"]["clinic"]

    with pytest.raises(ValidationError, match="tidak ada penerima"):
        create_task(
            clinic=clinic,
            actor=role_branch_matrix["cabang_b"]["supervisor"],
            title="Cek closing",
            audience_type=TaskAudienceType.PIC_FUNCTION,
            pic_function=PicFunction.CASHIER,
        )


def test_task_to_pic_function_uses_active_assignment(role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    pic = role_branch_matrix["cabang_a"]["supervisor"]
    UserRole.objects.create(user=pic, clinic=clinic, role=Role.PIC)
    PicAssignment.objects.create(
        user=pic,
        clinic=clinic,
        function=PicFunction.CASHIER,
        starts_on="2026-09-20",
        active=True,
    )

    item = create_task(
        clinic=clinic,
        actor=role_branch_matrix["cabang_a"]["supervisor"],
        title="Cek kasir",
        audience_type=TaskAudienceType.PIC_FUNCTION,
        pic_function=PicFunction.CASHIER,
    )

    assert list(item.task_assignments.values_list("assignee__username", flat=True)) == [
        "a_supervisor"
    ]


def test_assignee_cannot_confirm_own_task(role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    item = create_task(
        clinic=clinic,
        actor=role_branch_matrix["cabang_a"]["supervisor"],
        title="Foto stok",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()

    submit_assignment(assignment, user=assignee)

    with pytest.raises(PermissionDenied, match="mengonfirmasi task sendiri"):
        confirm_assignment(assignment, reviewer=assignee, rating=5)


def test_creator_can_confirm_submitted_task(role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Rapikan etalase",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()

    submit_assignment(assignment, user=assignee)
    confirm_assignment(assignment, reviewer=reviewer, rating=5)
    item.refresh_from_db()

    assert assignment.status == TaskAssignmentStatus.CONFIRMED
    assert item.status == ActionItemStatus.SELESAI


def test_revision_requires_note(role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Lengkapi label",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )

    with pytest.raises(ValidationError, match="Catatan revisi wajib"):
        request_revision(item.task_assignments.get(), reviewer=reviewer, note="")


def test_audience_snapshot_does_not_follow_later_role_changes(role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    extra = role_branch_matrix["cabang_a"]["owner"]
    item = create_task(
        clinic=clinic,
        actor=role_branch_matrix["cabang_a"]["supervisor"],
        title="Briefing staf",
        audience_type=TaskAudienceType.ROLE,
        role=Role.STAF,
    )

    UserRole.objects.create(user=extra, clinic=clinic, role=Role.STAF)

    assert "a_owner" not in {r["username"] for r in item.audience_snapshot.recipients}
    assert not item.task_assignments.filter(assignee=extra).exists()


def test_shared_task_can_be_sent_to_branch(role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    item = create_task(
        clinic=clinic,
        actor=role_branch_matrix["cabang_a"]["supervisor"],
        title="Bersihkan area tunggu",
        audience_type=TaskAudienceType.CLINIC,
        mode=TaskAssignmentMode.BERSAMA,
    )

    assert item.assignment_mode == TaskAssignmentMode.BERSAMA
    assert item.task_assignments.count() >= 5


def test_completed_task_stays_visible_in_history_filter(client, role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    assignee = role_branch_matrix["cabang_a"]["staf"]
    reviewer = role_branch_matrix["cabang_a"]["supervisor"]
    item = create_task(
        clinic=clinic,
        actor=reviewer,
        title="Tugas selesai tetap terlihat",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=assignee)
    confirm_assignment(assignment, reviewer=reviewer, rating=5)

    client.login(username="a_staf", password="TestPassword123!")
    response = client.get(reverse("core:action_items"), {"status": ActionItemStatus.SELESAI})

    assert response.status_code == 200
    assert "Tugas selesai tetap terlihat" in response.content.decode()
