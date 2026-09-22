"""Regression tests untuk seed checklist yang bersumber dari PDF operasional."""
from __future__ import annotations

import pytest
from django.core.management import call_command
from django.urls import reverse

from accounts.models import Role, UserRole
from checklists.models import ChecklistRun, ChecklistTemplate
from core.models import Clinic
from core.services import get_or_create_day

pytestmark = pytest.mark.django_db


def test_seed_demo_creates_role_specific_pdf_templates(capsys):
    call_command("seed_demo")
    clinic = Clinic.objects.get(code="jemur-andayani")
    templates = ChecklistTemplate.objects.filter(clinic=clinic, active=True)

    assert templates.count() == 9
    assert templates.filter(audience_key="KSR_OPENING", session="OPENING").exists()
    assert templates.filter(audience_key="APT_OPENING", target_roles=[Role.APOTEKER]).exists()
    assert templates.filter(audience_key="PRW_CONSULT", session="ANYTIME").exists()
    assert templates.filter(audience_key="PRW_TREATMENT", session="ANYTIME").exists()
    kasir = clinic.user_roles.filter(user__username="kasir1", role=Role.FRONT_DESK).first()
    assert kasir.role == Role.FRONT_DESK
    assert UserRole.objects.filter(user=kasir.user, clinic=clinic, role=Role.PIC).exists()


def test_pdf_template_runs_are_separate_and_snapshot_roles(capsys):
    call_command("seed_demo")
    clinic = Clinic.objects.get(code="jemur-andayani")
    supervisor = clinic.user_roles.get(user__username="supervisor").user
    day, _ = get_or_create_day(clinic, user=supervisor)

    runs = ChecklistRun.objects.filter(operational_day=day)
    assert runs.count() == 9
    kasir_run = runs.get(template__audience_key="KSR_OPENING")
    response = kasir_run.responses.get(label__contains="modal")
    assert response.performer_roles == [Role.FRONT_DESK]
    assert response.verifier_roles == [Role.SUPERVISOR]
    assert kasir_run.template_snapshot["audience_key"] == "KSR_OPENING"


def test_pdf_run_visibility_is_role_scoped(client, capsys):
    call_command("seed_demo")
    clinic = Clinic.objects.get(code="jemur-andayani")
    supervisor = clinic.user_roles.get(user__username="supervisor", role=Role.SUPERVISOR).user
    day, _ = get_or_create_day(clinic, user=supervisor)
    apoteker_run = ChecklistRun.objects.get(operational_day=day, template__audience_key="APT_OPENING")

    client.login(username="kasir1", password="JoDermaDemo2026!")
    assert client.get(reverse("checklists:run", args=[apoteker_run.pk])).status_code == 403

    client.login(username="apoteker1", password="JoDermaDemo2026!")
    assert client.get(reverse("checklists:run", args=[apoteker_run.pk])).status_code == 200
