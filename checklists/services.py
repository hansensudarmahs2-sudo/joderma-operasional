"""Service checklist: instantiate snapshot, catat respons, review pengecualian."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event, log_update, snapshot
from core.locking import assert_current_version

from .models import (
    ChecklistArea,
    ChecklistResponse,
    ChecklistRun,
    ChecklistTemplate,
    InputType,
    PROBLEM_RESULTS,
    ResponseResult,
    RunStatus,
)


def active_template(clinic, area: str) -> ChecklistTemplate | None:
    return (
        ChecklistTemplate.objects.filter(clinic=clinic, area=area, active=True)
        .order_by("-version")
        .first()
    )


@transaction.atomic
def instantiate_runs_for_day(day, user=None) -> list[ChecklistRun]:
    """Salin versi template aktif menjadi checklist run (PRD 20.2)."""
    runs: list[ChecklistRun] = []
    for area, _label in ChecklistArea.choices:
        template = active_template(day.clinic, area)
        if template is None:
            continue
        if ChecklistRun.objects.filter(operational_day=day, area=area).exists():
            continue
        items = list(template.items.all())
        run = ChecklistRun.objects.create(
            operational_day=day,
            template=template,
            area=area,
            template_snapshot={
                "template_id": template.pk,
                "name": template.name,
                "version": template.version,
                "items": [i.to_snapshot() for i in items],
            },
        )
        ChecklistResponse.objects.bulk_create(
            [
                ChecklistResponse(
                    run=run,
                    item_snapshot=i.to_snapshot(),
                    label=i.label,
                    category=i.category,
                    required=i.required,
                    input_type=i.input_type,
                    unit=i.unit,
                    min_quantity=i.min_quantity,
                    photo_required=i.photo_required,
                    sort_order=i.sort_order,
                )
                for i in items
            ]
        )
        runs.append(run)
    return runs


@transaction.atomic
def record_response(
    response: ChecklistResponse,
    *,
    user,
    result: str,
    quantity=None,
    note: str = "",
    expected_version: int | None = None,
) -> ChecklistResponse:
    day = response.run.operational_day
    day.assert_editable()

    assert_current_version(response, expected_version)

    result = (result or "").strip()
    if result not in dict(ResponseResult.choices):
        raise ValidationError("Status pemeriksaan tidak dikenali.")

    note = (note or "").strip()
    if result != ResponseResult.OK and result != ResponseResult.BELUM and not note:
        raise ValidationError("Catatan wajib diisi bila hasil bukan OK.")

    if response.input_type == InputType.KUANTITAS and result not in {
        ResponseResult.BELUM,
        ResponseResult.TIDAK_BERLAKU,
    }:
        if quantity in (None, ""):
            raise ValidationError("Jumlah aktual wajib diisi untuk item bertipe kuantitas.")
        quantity = int(quantity)
        if quantity < 0:
            raise ValidationError("Jumlah tidak boleh negatif.")
    else:
        quantity = None if quantity in (None, "") else int(quantity)

    before = snapshot(response)
    response.result = result
    response.quantity = quantity
    response.note = note
    response.checked_by = user
    response.checked_at = timezone.now()
    response.version += 1
    response.save()
    log_update(response, before, actor=user, label=f"{response.run.get_area_display()} · {response.label}")
    return response


def run_progress(run: ChecklistRun) -> dict:
    responses = list(run.responses.all())
    total = len(responses)
    done = sum(1 for r in responses if r.result != ResponseResult.BELUM)
    problems = [r for r in responses if r.result in PROBLEM_RESULTS]
    required_pending = [
        r
        for r in responses
        if r.required and r.result not in {ResponseResult.OK, ResponseResult.TIDAK_BERLAKU}
    ]
    return {
        "total": total,
        "done": done,
        "problems": problems,
        "required_pending": required_pending,
        "percent": round(done * 100 / total) if total else 0,
    }


@transaction.atomic
def review_run(run: ChecklistRun, user, *, accept_with_exception: bool = False, reason: str = ""):
    """Supervisor menerima kondisi; pengecualian wajib beralasan (PRD 8.2)."""
    run.operational_day.assert_editable()
    before = snapshot(run)
    progress = run_progress(run)

    if accept_with_exception:
        if not reason.strip():
            raise ValidationError("Alasan wajib diisi untuk menerima dengan pengecualian.")
        run.status = RunStatus.DITERIMA_DENGAN_CATATAN
        run.exception_reason = reason.strip()
    else:
        if progress["required_pending"]:
            raise ValidationError(
                f"{len(progress['required_pending'])} item wajib belum OK. "
                "Gunakan 'Terima dengan pengecualian' bila kondisi diterima."
            )
        run.status = RunStatus.SELESAI
    run.reviewed_by = user
    run.reviewed_at = timezone.now()
    run.save()
    log_update(
        run,
        before,
        actor=user,
        reason=reason,
        action=AuditAction.OVERRIDE if accept_with_exception else AuditAction.APPROVE,
    )
    return run


@transaction.atomic
def create_damage_from_response(response: ChecklistResponse, user, *, urgency=None):
    """Buat laporan kerusakan dari item checklist bertanda Rusak (PRD 8.9)."""
    from core.models import Priority
    from issues.models import ImpactLevel, IssueType
    from issues.services import create_issue

    if response.result != ResponseResult.RUSAK:
        raise ValidationError("Laporan kerusakan hanya dapat dibuat dari item berstatus Rusak.")

    issue = create_issue(
        clinic=response.run.operational_day.clinic,
        issue_type=IssueType.KERUSAKAN,
        title=f"Kerusakan: {response.label}",
        description=response.note or "Ditemukan saat checklist pembukaan.",
        user=user,
        severity=urgency or Priority.SEDANG,
        category=response.run.get_area_display(),
        location=response.run.get_area_display(),
        impact=ImpactLevel.TERBATAS,
        source_ref=f"checklistresponse#{response.pk}",
    )
    log_event(
        action=AuditAction.CREATE,
        entity_type="issue",
        entity_id=issue.pk,
        entity_label=issue.number,
        actor=user,
        reason=f"Dibuat dari item checklist #{response.pk}",
    )
    return issue


@transaction.atomic
def create_action_item_from_response(response: ChecklistResponse, user, *, due_at=None):
    """Tindak lanjut kekurangan dari item Tidak lengkap (PRD 8.2)."""
    from core.models import ActionItem, Priority

    if response.result != ResponseResult.TIDAK_LENGKAP:
        raise ValidationError("Tindak lanjut hanya dapat dibuat dari item Tidak lengkap.")

    item = ActionItem.objects.create(
        clinic=response.run.operational_day.clinic,
        title=f"Lengkapi: {response.label}",
        description=response.note,
        source_type="checklistresponse",
        source_id=response.pk,
        source_label=response.run.get_area_display(),
        priority=Priority.SEDANG,
        due_at=due_at,
        created_by=user,
    )
    log_event(
        action=AuditAction.CREATE,
        entity_type="actionitem",
        entity_id=item.pk,
        entity_label=item.title,
        actor=user,
    )
    return item
