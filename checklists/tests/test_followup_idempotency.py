"""Fase 3: tindak lanjut checklist bermasalah, idempoten (PRD 8.1, 13)."""
from __future__ import annotations

import threading
import time

import pytest
from django.core.exceptions import ValidationError
from django.db import OperationalError, connections

from accounts.models import PicAssignment, PicFunction, Role, UserRole
from checklists.models import ChecklistFollowup, ChecklistResponse, ResponseResult
from checklists.services import create_action_item_from_response, record_response
from core.models import ActionItem, TaskAssignment

pytestmark = pytest.mark.django_db


def _get(day, label):
    return ChecklistResponse.objects.get(run__operational_day=day, label=label)


def test_followup_created_from_problem_response(day, kasir):
    r = _get(day, "Sarung tangan")
    record_response(r, user=kasir, result=ResponseResult.TIDAK_LENGKAP, quantity=3, note="sisa 3")
    item = create_action_item_from_response(r, kasir)

    assert ActionItem.objects.filter(pk=item.pk, source_type="checklistresponse").exists()
    assert item.source_id == r.pk
    assert ChecklistFollowup.objects.filter(response=r, action_item=item).exists()
    assert TaskAssignment.objects.filter(action_item=item).exists()


def test_followup_rejected_for_ok_response(day, kasir):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.OK)
    with pytest.raises(ValidationError):
        create_action_item_from_response(r, kasir)


def test_repeated_followup_call_does_not_duplicate_task(day, kasir):
    """Double submit/retry tidak boleh menggandakan task (gate Fase 3)."""
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.RUSAK, note="lampu mati")

    item1 = create_action_item_from_response(r, kasir)
    item2 = create_action_item_from_response(r, kasir)
    item3 = create_action_item_from_response(r, kasir)

    assert item1.pk == item2.pk == item3.pk
    assert ChecklistFollowup.objects.filter(response=r).count() == 1
    assert ActionItem.objects.filter(source_type="checklistresponse", source_id=r.pk).count() == 1
    assert TaskAssignment.objects.filter(action_item=item1).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_followup_calls_create_single_task(day, kasir):
    """Simulasi dua request bersamaan untuk respons bermasalah yang sama."""
    r = _get(day, "Sarung tangan")
    record_response(r, user=kasir, result=ResponseResult.TIDAK_LENGKAP, quantity=1, note="kosong")

    results: list = []
    errors: list = []
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait(timeout=5)
            last_exc = None
            item = None
            for _ in range(10):
                try:
                    item = create_action_item_from_response(r, kasir)
                    break
                except OperationalError as exc:
                    last_exc = exc
                    time.sleep(0.05)
            if item is None:
                raise last_exc
            results.append(item.pk)
        except Exception as exc:  # pragma: no cover - defensif
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, errors
    assert len(results) == 2
    assert len(set(results)) == 1
    assert ChecklistFollowup.objects.filter(response=r).count() == 1
    assert ActionItem.objects.filter(source_type="checklistresponse", source_id=r.pk).count() == 1


def test_followup_targets_pic_function_when_template_configured(clinic, supervisor, kasir):
    from checklists.models import ChecklistArea, ChecklistSession
    from checklists.services import create_template_version, instantiate_runs_for_day
    from core.models import TaskAudienceType
    from core.services import get_or_create_day

    UserRole.objects.create(user=kasir, clinic=clinic, role=Role.PIC)
    PicAssignment.objects.create(
        user=kasir, clinic=clinic, function=PicFunction.CASHIER, starts_on="2026-09-20", active=True
    )
    create_template_version(
        clinic=clinic,
        area=ChecklistArea.AKSES_UMUM,
        session=ChecklistSession.OPENING,
        name="Akses umum",
        items=[{"label": "Cek pintu"}],
        user=supervisor,
        target_pic_function=PicFunction.CASHIER,
    )
    day, _ = get_or_create_day(clinic, date="2026-09-23", user=supervisor)
    response = ChecklistResponse.objects.get(
        run__operational_day=day, run__area=ChecklistArea.AKSES_UMUM, label="Cek pintu"
    )
    record_response(response, user=supervisor, result=ResponseResult.RUSAK, note="engsel patah")

    item = create_action_item_from_response(response, supervisor)

    assert item.audience_snapshot.audience_type == TaskAudienceType.PIC_FUNCTION
    assert TaskAssignment.objects.filter(action_item=item, assignee=kasir).exists()


def test_followup_falls_back_to_checker_without_template_target(day, kasir):
    from core.models import TaskAudienceType

    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.RUSAK, note="dermatoskop mati")

    item = create_action_item_from_response(r, kasir)

    assert item.audience_snapshot.audience_type == TaskAudienceType.USER
    assert TaskAssignment.objects.filter(action_item=item, assignee=kasir).exists()
