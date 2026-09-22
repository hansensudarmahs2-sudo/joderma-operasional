"""Service checklist: instantiate snapshot, catat respons, review pengecualian."""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_event, log_update, snapshot
from core.locking import assert_current_version

from .models import (
    ChecklistFollowup,
    ChecklistResponse,
    ChecklistRun,
    ChecklistSession,
    ChecklistTemplate,
    ChecklistTemplateItem,
    InputType,
    PROBLEM_RESULTS,
    ResponseResult,
    RunStatus,
)


def _assert_checklist_access(user, run: ChecklistRun, *, review: bool = False) -> None:
    """Pastikan service checklist tidak dapat dipanggil lintas cabang.

    View tetap melakukan pemeriksaan untuk memberi respons HTTP yang tepat, tetapi
    service juga harus aman bila dipanggil dari command, task, atau endpoint lain.
    """
    from core.permissions import can_access_checklist_run, can_fill_checklist, can_review_checklist

    allowed = can_review_checklist(user) if review else can_fill_checklist(user)
    if not allowed or not can_access_checklist_run(user, run):
        raise PermissionDenied("Anda tidak memiliki akses ke checklist cabang ini.")


def active_template(clinic, area: str, session: str = ChecklistSession.OPENING) -> ChecklistTemplate | None:
    return (
        ChecklistTemplate.objects.filter(clinic=clinic, area=area, session=session, active=True)
        .order_by("-version")
        .first()
    )


@transaction.atomic
def instantiate_runs_for_day(day, user=None) -> list[ChecklistRun]:
    """Salin versi template aktif menjadi checklist run (PRD 20.2).

    Setiap kombinasi area x sesi yang memiliki template aktif akan
    diinstansiasi satu kali per hari operasional (PRD 8.1).
    """
    runs: list[ChecklistRun] = []
    templates = ChecklistTemplate.objects.filter(
        clinic=day.clinic, active=True
    ).prefetch_related("items")
    for template in templates:
        if ChecklistRun.objects.filter(operational_day=day, template=template).exists():
            continue
        items = list(template.items.all())
        run = ChecklistRun.objects.create(
            operational_day=day,
            template=template,
            area=template.area,
            session=template.session,
            template_snapshot={
                "template_id": template.pk,
                "name": template.name,
                "version": template.version,
                "audience_key": template.audience_key,
                "target_roles": list(template.target_roles or []),
                "session": template.session,
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
                    options=list(i.options or []),
                    photo_required=i.photo_required,
                    sort_order=i.sort_order,
                    performer_roles=list(i.performer_roles or []),
                    verifier_roles=list(i.verifier_roles or []),
                )
                for i in items
            ]
        )
        runs.append(run)
    return runs


@transaction.atomic
def create_template_version(
    *,
    clinic,
    area: str,
    session: str = ChecklistSession.OPENING,
    name: str,
    items: list[dict],
    user=None,
    target_pic_function: str = "",
    target_role: str = "",
    target_roles: list[str] | None = None,
    audience_key: str = "",
    assignment_mode: str | None = None,
) -> ChecklistTemplate:
    """Buat versi template baru tanpa mengubah versi/riwayat lama (PRD 8.1).

    Versi lama tetap ada di database dan tetap dirujuk oleh
    `ChecklistRun.template_snapshot` yang sudah dibuat sebelumnya. Fungsi ini
    hanya menonaktifkan versi lama dan membuat baris versi baru; tidak pernah
    memutasi baris `ChecklistTemplate`/`ChecklistTemplateItem` yang sudah ada.
    """
    from core.models import TaskAssignmentMode

    previous = (
        ChecklistTemplate.objects.filter(
            clinic=clinic, area=area, session=session, audience_key=audience_key
        )
        .order_by("-version")
        .first()
    )
    next_version = (previous.version + 1) if previous else 1

    template = ChecklistTemplate.objects.create(
        clinic=clinic,
        name=name,
        area=area,
        session=session,
        version=next_version,
        audience_key=audience_key,
        active=True,
        target_pic_function=target_pic_function,
        target_role=target_role,
        target_roles=target_roles or ([target_role] if target_role else []),
        assignment_mode=assignment_mode or TaskAssignmentMode.INDIVIDUAL,
        created_by=user,
    )
    ChecklistTemplateItem.objects.bulk_create(
        [
            ChecklistTemplateItem(
                template=template,
                label=item["label"],
                category=item.get("category", ""),
                required=item.get("required", True),
                input_type=item.get("input_type", InputType.CEKLIS),
                unit=item.get("unit", ""),
                min_quantity=item.get("min_quantity"),
                photo_required=item.get("photo_required", False),
                sort_order=item.get("sort_order", index),
                help_text=item.get("help_text", ""),
                performer_roles=item.get("performer_roles", []),
                verifier_roles=item.get("verifier_roles", []),
            )
            for index, item in enumerate(items, start=1)
        ]
    )
    if previous is not None and previous.active:
        previous.active = False
        previous.save(update_fields=["active"])
    log_event(
        action=AuditAction.CREATE,
        entity_type="checklisttemplate",
        entity_id=template.pk,
        entity_label=str(template),
        actor=user,
        after=snapshot(template),
    )
    return template


@transaction.atomic
def record_response(
    response: ChecklistResponse,
    *,
    user,
    result: str,
    quantity=None,
    selection: str = "",
    note: str = "",
    expected_version: int | None = None,
    reason: str = "",
) -> ChecklistResponse:
    day = response.run.operational_day
    _assert_checklist_access(user, response.run)
    from core.permissions import can_edit_checklist_response
    if not can_edit_checklist_response(user, response):
        raise PermissionDenied("Anda bukan pelaksana atau verifikator item checklist ini.")
    day.assert_editable()

    assert_current_version(response, expected_version)

    result = (result or "").strip()
    if result not in dict(ResponseResult.choices):
        raise ValidationError("Status pemeriksaan tidak dikenali.")

    note = (note or "").strip()
    selection = (selection or "").strip()
    if response.input_type == InputType.PILIHAN:
        allowed = set(response.options or [])
        if result == ResponseResult.OK and selection not in allowed:
            raise ValidationError("Pilihan wajib dipilih.")
    if result != ResponseResult.OK and result != ResponseResult.BELUM and not note:
        raise ValidationError("Catatan wajib diisi bila hasil bukan OK.")

    # PRD 8.1: koreksi setelah dicek (result != BELUM) wajib beralasan agar
    # hasil yang sudah dicatat tidak tertimpa diam-diam. Pengisian pertama
    # kali (dari BELUM) tidak membutuhkan alasan.
    is_correction = response.result != ResponseResult.BELUM
    reason = (reason or "").strip()
    if is_correction and not reason:
        raise ValidationError(
            "Alasan wajib diisi untuk mengoreksi hasil checklist yang sudah pernah dicek."
        )

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
    response.selection = selection
    response.note = note
    response.checked_by = user
    response.checked_at = timezone.now()
    response.version += 1
    response.save()
    log_update(
        response,
        before,
        actor=user,
        reason=reason if is_correction else "",
        action=AuditAction.CORRECTION if is_correction else AuditAction.UPDATE,
        label=f"{response.run.get_area_display()} · {response.label}",
    )
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
        "pending": total - done,
        "percent": round(done * 100 / total) if total else 0,
    }


@transaction.atomic
def review_run(run: ChecklistRun, user, *, accept_with_exception: bool = False, reason: str = ""):
    """Supervisor menerima kondisi; pengecualian wajib beralasan (PRD 8.2)."""
    _assert_checklist_access(user, run, review=True)
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

    _assert_checklist_access(user, response.run)

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


def resolve_followup_audience(response: ChecklistResponse, fallback_user=None) -> dict:
    """Tentukan target penerima tindak lanjut checklist (PRD 8.1).

    Urutan prioritas: fungsi PIC target template, lalu role/tier target
    template, lalu pengguna yang mencatat hasil (checked_by), lalu
    `fallback_user`.
    """
    from core.models import TaskAudienceType

    template = response.run.template
    if template.target_pic_function:
        return {
            "audience_type": TaskAudienceType.PIC_FUNCTION,
            "pic_function": template.target_pic_function,
        }
    if template.target_role:
        return {"audience_type": TaskAudienceType.ROLE, "role": template.target_role}
    recipient = response.checked_by_id or (fallback_user.pk if fallback_user else None)
    if not recipient:
        raise ValidationError(
            "Tindak lanjut tidak dapat ditentukan penerimanya: tidak ada fungsi PIC/role "
            "target pada template dan item belum dicek oleh siapa pun."
        )
    return {"audience_type": TaskAudienceType.USER, "user_ids": [recipient]}


@transaction.atomic
def create_action_item_from_response(response: ChecklistResponse, user, *, due_at=None):
    """Tindak lanjut checklist bermasalah, idempoten (PRD 8.1).

    Dipicu ulang untuk respons yang sama (double submit/retry) tidak akan
    menggandakan `ActionItem`/`TaskAssignment` — ditandai dengan
    `ChecklistFollowup` unik per respons.
    """
    from core.models import Priority
    from core.task_services import create_task

    _assert_checklist_access(user, response.run)

    if response.result not in PROBLEM_RESULTS:
        raise ValidationError(
            "Tindak lanjut hanya dapat dibuat dari item bermasalah (Tidak lengkap/Rusak)."
        )

    # Kunci baris respons agar dua transaksi yang berjalan bersamaan untuk
    # respons yang sama diserialkan; SQLite tetap menyerialkan penulisan
    # lewat penguncian database meski select_for_update tidak berefek nyata.
    locked_response = ChecklistResponse.objects.select_for_update().get(pk=response.pk)

    existing = ChecklistFollowup.objects.filter(response=locked_response).select_related(
        "action_item"
    ).first()
    if existing is not None:
        return existing.action_item

    template = locked_response.run.template
    audience = resolve_followup_audience(locked_response, fallback_user=user)

    item = create_task(
        clinic=locked_response.run.operational_day.clinic,
        actor=user,
        title=f"Lengkapi: {locked_response.label}",
        description=locked_response.note,
        priority=Priority.SEDANG,
        due_at=due_at,
        mode=template.assignment_mode,
        **audience,
    )
    item.source_type = "checklistresponse"
    item.source_id = locked_response.pk
    item.source_label = locked_response.run.get_area_display()
    item.save(update_fields=["source_type", "source_id", "source_label", "updated_at"])

    ChecklistFollowup.objects.create(response=locked_response, action_item=item, created_by=user)

    log_event(
        action=AuditAction.CREATE,
        entity_type="actionitem",
        entity_id=item.pk,
        entity_label=item.title,
        actor=user,
        reason=f"Tindak lanjut checklist respons #{locked_response.pk}",
    )
    return item
