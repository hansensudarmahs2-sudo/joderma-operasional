"""Negative tests: checklist tidak boleh diakses lintas cabang melalui ID langsung."""
from __future__ import annotations

import pytest
from django.urls import reverse

from checklists.models import ChecklistArea, ChecklistRun, ChecklistTemplate, ChecklistTemplateItem
from checklists.services import instantiate_runs_for_day
from core.services import get_or_create_day

pytestmark = pytest.mark.django_db


def _branch_b_run(clinic_b, role_branch_matrix):
    owner = role_branch_matrix["cabang_b"]["supervisor"]
    template = ChecklistTemplate.objects.create(
        clinic=clinic_b,
        name="Checklist B",
        area=ChecklistArea.RUANG_KONSULTASI,
        version=1,
    )
    ChecklistTemplateItem.objects.create(template=template, label="Cek B", sort_order=1)
    day, _ = get_or_create_day(clinic_b, user=owner)
    instantiate_runs_for_day(day)
    run = ChecklistRun.objects.get(operational_day=day, area=ChecklistArea.RUANG_KONSULTASI)
    return run, run.responses.get()


def test_other_branch_cannot_read_run_or_response_direct_url(client, clinic_b, role_branch_matrix):
    run, response = _branch_b_run(clinic_b, role_branch_matrix)
    user_a = role_branch_matrix["cabang_a"]["staf"]
    client.force_login(user_a)

    assert client.get(reverse("checklists:run", args=[run.pk])).status_code == 403
    assert client.post(
        reverse("checklists:save_response", args=[response.pk]),
        {"hasil": "OK", "versi": response.version},
    ).status_code == 403


def test_other_branch_cannot_create_damage_or_followup(client, clinic_b, role_branch_matrix):
    run, response = _branch_b_run(clinic_b, role_branch_matrix)
    user_a = role_branch_matrix["cabang_a"]["staf"]
    client.force_login(user_a)

    assert client.post(reverse("checklists:make_damage", args=[response.pk])).status_code == 403
    assert client.post(reverse("checklists:make_action", args=[response.pk])).status_code == 403


def test_supervisor_other_branch_cannot_review_run(client, clinic_b, role_branch_matrix):
    run, _response = _branch_b_run(clinic_b, role_branch_matrix)
    user_a = role_branch_matrix["cabang_a"]["supervisor"]
    client.force_login(user_a)

    assert client.post(reverse("checklists:review_action", args=[run.pk])).status_code == 403


def test_non_supervisor_cannot_open_review_page(client, clinic, staf):
    client.force_login(staf)
    assert client.get(reverse("checklists:review")).status_code == 403
