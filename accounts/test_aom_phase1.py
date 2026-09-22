from __future__ import annotations

from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from accounts.models import Capability, Role, User, UserCapability, UserRole
from core.models import ActionItem
from core.permissions import can_access_clinic, can_view_restricted_issue, user_clinic_queryset
from issues.models import IssueType
from issues.services import assign_issue, create_issue

pytestmark = pytest.mark.django_db


def test_role_branch_matrix_fixture_is_anonymous_and_cross_branch(role_branch_matrix):
    cabang_a = role_branch_matrix["cabang_a"]
    cabang_b = role_branch_matrix["cabang_b"]

    assert cabang_a["clinic"].code == "test-cabang"
    assert cabang_b["clinic"].code == "test-cabang-b"
    assert cabang_a["staf"].username == "a_staf"
    assert cabang_b["staf"].username == "b_staf"


def test_aom_and_pic_roles_are_available():
    assert Role.AOM in Role
    assert Role.PIC in Role


def test_user_clinic_queryset_limits_regular_staff(role_branch_matrix):
    user = role_branch_matrix["cabang_a"]["staf"]

    assert list(user_clinic_queryset(user)) == [role_branch_matrix["cabang_a"]["clinic"]]
    assert can_access_clinic(user, role_branch_matrix["cabang_a"]["clinic"]) is True
    assert can_access_clinic(user, role_branch_matrix["cabang_b"]["clinic"]) is False


def test_aom_role_can_scope_across_branches(role_branch_matrix):
    user = role_branch_matrix["cabang_a"]["supervisor"]
    UserRole.objects.create(user=user, clinic=role_branch_matrix["cabang_a"]["clinic"], role=Role.AOM)

    assert set(user_clinic_queryset(user)) == {
        role_branch_matrix["cabang_a"]["clinic"],
        role_branch_matrix["cabang_b"]["clinic"],
    }
    assert can_access_clinic(user, role_branch_matrix["cabang_b"]["clinic"]) is True


def test_cross_branch_issue_detail_is_blocked(client, role_branch_matrix):
    issue = create_issue(
        clinic=role_branch_matrix["cabang_b"]["clinic"],
        issue_type=IssueType.MASUKAN,
        title="Masukan cabang B",
        user=role_branch_matrix["cabang_b"]["staf"],
    )

    client.login(username="a_staf", password="TestPassword123!")

    assert client.get(reverse("issues:detail", args=[issue.pk])).status_code == 403


def test_cross_branch_action_item_update_is_blocked(client, role_branch_matrix):
    item = ActionItem.objects.create(
        clinic=role_branch_matrix["cabang_b"]["clinic"],
        title="Tugas cabang B",
        source_type="test",
        owner=role_branch_matrix["cabang_b"]["staf"],
    )

    client.login(username="a_supervisor", password="TestPassword123!")

    response = client.post(
        reverse("core:action_item_update", args=[item.pk]),
        {"status": "SELESAI", "catatan": "paksa dari cabang A"},
    )
    assert response.status_code == 403


def test_admin_teknis_cannot_view_confidential_report_without_capability(
    clinic, kasir, admin_teknis
):
    issue = create_issue(
        clinic=clinic,
        issue_type=IssueType.KOMPLAIN,
        title="Laporan rahasia",
        user=kasir,
        is_restricted=True,
    )

    assert can_view_restricted_issue(admin_teknis, issue) is False


def test_confidential_report_capability_is_explicit(clinic, kasir, admin_teknis):
    issue = create_issue(
        clinic=clinic,
        issue_type=IssueType.KOMPLAIN,
        title="Laporan rahasia",
        user=kasir,
        is_restricted=True,
    )

    UserCapability.objects.create(
        user=admin_teknis, capability=Capability.REPORT_VIEW_CONFIDENTIAL
    )

    assert can_view_restricted_issue(admin_teknis, issue) is True


def test_issue_assignee_must_be_in_same_branch(role_branch_matrix):
    issue = create_issue(
        clinic=role_branch_matrix["cabang_a"]["clinic"],
        issue_type=IssueType.KOMPLAIN,
        title="Komplain cabang A",
        user=role_branch_matrix["cabang_a"]["staf"],
    )

    with pytest.raises(ValidationError, match="Penanggung jawab harus berasal dari cabang catatan"):
        assign_issue(
            issue,
            supervisor=role_branch_matrix["cabang_a"]["supervisor"],
            assignee=role_branch_matrix["cabang_b"]["staf"],
        )


def test_preview_aom_seed_does_not_create_accounts():
    before = User.objects.count()
    out = StringIO()

    call_command("preview_aom_seed", stdout=out)

    text = out.getvalue()
    assert User.objects.count() == before
    assert "JoDerma Citraland" in text
    assert "dr Hansen Sudarma" in text
    assert "tidak membuat akun" in text
