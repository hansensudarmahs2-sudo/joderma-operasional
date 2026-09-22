"""Fase 3: sesi opening/closing, target fungsi/tier, dan template berversi.

PRD 8.1, 13 Fase 3. Sesuai gate: perubahan template tidak mengubah histori.
"""
from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from accounts.models import PicFunction, Role
from checklists.models import (
    ChecklistArea,
    ChecklistRun,
    ChecklistSession,
    ChecklistTemplate,
    ChecklistTemplateItem,
)
from checklists.services import active_template, create_template_version, instantiate_runs_for_day
from core.models import TaskAssignmentMode
from core.services import get_or_create_day

pytestmark = pytest.mark.django_db


def test_template_session_defaults_to_opening(template):
    assert template.session == ChecklistSession.OPENING


def test_closing_template_versioned_independently_of_opening(clinic, supervisor):
    opening = create_template_version(
        clinic=clinic,
        area=ChecklistArea.AKSES_UMUM,
        session=ChecklistSession.OPENING,
        name="Akses umum - opening",
        items=[{"label": "Pintu dibuka"}],
        user=supervisor,
    )
    closing = create_template_version(
        clinic=clinic,
        area=ChecklistArea.AKSES_UMUM,
        session=ChecklistSession.CLOSING,
        name="Akses umum - closing",
        items=[{"label": "Pintu dikunci"}],
        user=supervisor,
    )
    assert opening.version == 1
    assert closing.version == 1
    assert opening.pk != closing.pk
    assert ChecklistTemplate.objects.filter(
        clinic=clinic, area=ChecklistArea.AKSES_UMUM
    ).count() == 2


def test_instantiate_runs_creates_one_run_per_area_session(clinic, supervisor):
    create_template_version(
        clinic=clinic,
        area=ChecklistArea.AKSES_UMUM,
        session=ChecklistSession.OPENING,
        name="Akses umum - opening",
        items=[{"label": "Pintu dibuka"}],
        user=supervisor,
    )
    create_template_version(
        clinic=clinic,
        area=ChecklistArea.AKSES_UMUM,
        session=ChecklistSession.CLOSING,
        name="Akses umum - closing",
        items=[{"label": "Pintu dikunci"}],
        user=supervisor,
    )

    day, _ = get_or_create_day(clinic, date="2026-09-21", user=supervisor)

    runs = ChecklistRun.objects.filter(operational_day=day, area=ChecklistArea.AKSES_UMUM)
    assert runs.count() == 2
    assert set(runs.values_list("session", flat=True)) == {
        ChecklistSession.OPENING,
        ChecklistSession.CLOSING,
    }


def test_template_edit_does_not_alter_existing_run_snapshot(clinic, supervisor):
    """Gate Fase 3: perubahan template tidak mengubah histori (PRD 13)."""
    v1 = create_template_version(
        clinic=clinic,
        area=ChecklistArea.KOMPUTER_SISTEM,
        session=ChecklistSession.OPENING,
        name="Komputer v1",
        items=[{"label": "Cek komputer"}],
        user=supervisor,
    )
    day, _ = get_or_create_day(clinic, date="2026-09-22", user=supervisor)
    run = ChecklistRun.objects.get(
        operational_day=day, area=ChecklistArea.KOMPUTER_SISTEM, session=ChecklistSession.OPENING
    )
    original_snapshot = run.template_snapshot
    assert original_snapshot["version"] == 1
    assert original_snapshot["items"][0]["label"] == "Cek komputer"

    v2 = create_template_version(
        clinic=clinic,
        area=ChecklistArea.KOMPUTER_SISTEM,
        session=ChecklistSession.OPENING,
        name="Komputer v2",
        items=[{"label": "Cek komputer dan printer"}],
        user=supervisor,
    )

    run.refresh_from_db()
    assert run.template_snapshot == original_snapshot
    assert run.template_snapshot["items"][0]["label"] == "Cek komputer"
    assert run.template_id == v1.pk
    assert v2.version == 2
    v1.refresh_from_db()
    assert v1.active is False
    assert v2.active is True
    # Item lama tidak dihapus/diedit.
    assert ChecklistTemplateItem.objects.filter(
        template=v1, label="Cek komputer"
    ).exists()


def test_active_template_returns_latest_active_version_per_session(clinic, supervisor):
    create_template_version(
        clinic=clinic,
        area=ChecklistArea.RUANG_TINDAKAN,
        session=ChecklistSession.OPENING,
        name="Tindakan opening",
        items=[{"label": "Cek alat"}],
        user=supervisor,
    )
    v2 = create_template_version(
        clinic=clinic,
        area=ChecklistArea.RUANG_TINDAKAN,
        session=ChecklistSession.OPENING,
        name="Tindakan opening v2",
        items=[{"label": "Cek alat dan bahan"}],
        user=supervisor,
    )
    resolved = active_template(clinic, ChecklistArea.RUANG_TINDAKAN, ChecklistSession.OPENING)
    assert resolved.pk == v2.pk


def test_template_can_target_pic_function_and_role(clinic, supervisor):
    template = create_template_version(
        clinic=clinic,
        area=ChecklistArea.RUANG_KONSULTASI,
        session=ChecklistSession.CLOSING,
        name="Konsultasi closing",
        items=[{"label": "Cek meja"}],
        user=supervisor,
        target_pic_function=PicFunction.SHIFT_COORDINATOR,
        target_role=Role.PIC,
        assignment_mode=TaskAssignmentMode.BERSAMA,
    )
    assert template.target_pic_function == PicFunction.SHIFT_COORDINATOR
    assert template.target_role == Role.PIC
    assert template.assignment_mode == TaskAssignmentMode.BERSAMA


def test_template_assignment_mode_defaults_individual(clinic, supervisor):
    template = create_template_version(
        clinic=clinic,
        area=ChecklistArea.RUANG_TINDAKAN,
        session=ChecklistSession.CLOSING,
        name="Tindakan closing",
        items=[{"label": "Cek AC"}],
        user=supervisor,
    )
    assert template.assignment_mode == TaskAssignmentMode.INDIVIDUAL
