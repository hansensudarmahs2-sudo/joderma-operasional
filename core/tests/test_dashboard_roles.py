"""Fase 5: dashboard berbeda per role (plan 13 Fase 5, 14).

Staf melihat dashboard standar. AOM melihat konfirmasi tertunda lintas
cabang + shortcut laporan rahasia/masukan. PIC melihat task delegasinya
sendiri yang menunggu konfirmasi + fungsi PIC aktifnya. Admin melihat
shortcut pengelolaan user/template.
"""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import PicAssignment, PicFunction, Role, User, UserRole
from core.task_services import create_task, submit_assignment
from core.models import TaskAudienceType

pytestmark = pytest.mark.django_db


def test_staf_dashboard_has_no_role_specific_sections(client, role_branch_matrix):
    client.login(username="a_staf", password="TestPassword123!")
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Ringkasan Direktur Operasional" not in body
    assert "Ringkasan PIC" not in body
    assert "Ringkasan Admin" not in body


def test_aom_dashboard_shows_pending_confirmations_across_clinics(client, role_branch_matrix):
    clinic_b = role_branch_matrix["cabang_b"]["clinic"]
    assignee = role_branch_matrix["cabang_b"]["staf"]
    reviewer = role_branch_matrix["cabang_b"]["supervisor"]
    item = create_task(
        clinic=clinic_b,
        actor=reviewer,
        title="Task lintas cabang untuk AOM",
        audience_type=TaskAudienceType.USER,
        user_ids=[assignee.pk],
    )
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=assignee)

    aom_user = User.objects.create_user(username="aom_dash", password="TestPassword123!")
    UserRole.objects.create(user=aom_user, clinic=role_branch_matrix["cabang_a"]["clinic"], role=Role.AOM)

    client.login(username="aom_dash", password="TestPassword123!")
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Ringkasan Direktur Operasional" in body
    assert "Task lintas cabang untuk AOM" in body


def test_pic_dashboard_shows_own_delegated_pending_confirmation(client, role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    pic_user = User.objects.create_user(username="pic_dash", password="TestPassword123!")
    UserRole.objects.create(user=pic_user, clinic=clinic, role=Role.PIC)
    PicAssignment.objects.create(
        user=pic_user, clinic=clinic, function=PicFunction.CASHIER, starts_on="2026-09-20", active=True
    )
    staf = role_branch_matrix["cabang_a"]["staf"]
    item = create_task(
        clinic=clinic,
        actor=pic_user,
        title="Delegasi PIC menunggu konfirmasi",
        audience_type=TaskAudienceType.USER,
        user_ids=[staf.pk],
    )
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=staf)

    client.login(username="pic_dash", password="TestPassword123!")
    response = client.get(reverse("core:dashboard"))
    body = response.content.decode()
    assert "Ringkasan PIC" in body
    assert "Delegasi PIC menunggu konfirmasi" in body
    assert "CASHIER" in body


def test_admin_dashboard_shows_management_shortcuts(client, role_branch_matrix):
    clinic = role_branch_matrix["cabang_a"]["clinic"]
    admin_user = User.objects.create_user(username="admin_dash", password="TestPassword123!")
    UserRole.objects.create(user=admin_user, clinic=clinic, role=Role.ADMIN)

    client.login(username="admin_dash", password="TestPassword123!")
    # Admin sistem mendarat di Pengguna dan tidak membuka Hari Ini (tampilan per peran).
    assert client.get(reverse("home"))["Location"] == reverse("accounts:user_list")
    assert client.get(reverse("core:dashboard")).status_code == 403
    body = client.get(reverse("accounts:user_list")).content.decode()
    assert reverse("accounts:role_reset") in body and reverse("core:config") in body


def test_dashboard_requires_login(client):
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302
