"""View inti: dashboard, action item, lampiran privat, admin konfigurasi."""
from __future__ import annotations

import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.models import AuditAction
from audit.services import log_event
from breaks.services import upcoming_breaks
from cash.services import cash_summary
from issues.services import issue_counters
from nurses.models import Availability, NurseRosterEntry

from .models import (
    ActionItem,
    ActionItemStatus,
    Attachment,
    ClinicConfig,
    DEFAULT_CONFIG,
    OperationalDay,
    TaskAssignment,
    TaskAssignmentStatus,
    local_today,
)
from .photos import save_optional_photo, task_photos
from .permissions import (
    can_access_clinic,
    can_close_day,
    can_manage_config,
    can_manage_templates,
    can_manage_users,
    can_view_cash_amounts,
    is_admin,
    is_aom,
    is_owner,
    is_pic,
    is_supervisor,
    require,
    user_clinic_queryset,
)
from .services import (
    active_clinic,
    close_day,
    closing_blockers,
    get_or_create_day,
    mark_ready,
    open_day,
    opening_progress,
    reopen_day,
    start_closing,
)
from .task_services import (
    can_review_assignment,
    cancel_assignment,
    claim_shared_task,
    confirm_assignment,
    request_revision,
    submit_assignment,
)


def health(request):
    """Health endpoint privat tanpa data sensitif (PRD 15.5)."""
    return JsonResponse({"status": "ok", "time": timezone.now().isoformat()})


def permission_denied(request, exception=None):
    return render(request, "403.html", {"message": str(exception) or "Akses ditolak."}, status=403)


@login_required
def home(request):
    """Halaman pertama sesudah login mengikuti tampilan peran."""
    from .peran import home_url

    return redirect(home_url(request.user))


@login_required
def dashboard(request):
    clinic = active_clinic(request.user)
    user = request.user

    date_str = request.GET.get("tanggal")
    day = None
    if date_str and (is_supervisor(user) or is_owner(user)):
        day = OperationalDay.objects.filter(clinic=clinic, date=date_str).first()
    if day is None:
        day = OperationalDay.today_for(clinic)

    if day is None and request.GET.get("buat") == "1":
        day, _ = get_or_create_day(clinic, user=user)
        messages.success(request, "Sesi hari operasional dibuat.")
        return redirect("core:dashboard")

    from .task_services import my_tasks

    tasks_mine = my_tasks(user)

    context = {
        "clinic": clinic,
        "day": day,
        "today": local_today(),
        # Tugas saya tampil walau sesi hari operasional belum dibuat.
        "my_tasks": tasks_mine,
        "task_photos": task_photos([t["item"] for t in tasks_mine]),
        "my_issues": user.issue_assignments.filter(active=True).select_related("issue")[:10],
        "can_view_cash": can_view_cash_amounts(user),
        "can_close": can_close_day(user),
        "is_supervisor": is_supervisor(user),
        "is_aom": is_aom(user),
        "is_pic": is_pic(user),
        "is_admin": is_admin(user),
        "can_manage_users": can_manage_users(user),
        "can_manage_templates": can_manage_templates(user),
    }
    from . import peran

    # Fase 7: staf membuka Hari Ini untuk aksi hari; tautan tim diganti halaman "saya", Kas hanya hari kasir.
    context["staff_view"] = peran.persona(user) == peran.STAF
    if context["staff_view"]:
        from jadwal.services import is_cashier_today

        context["can_view_cash"] = context["can_view_cash"] and is_cashier_today(user)

    if is_aom(user):
        from .models import TaskAssignmentStatus as _TAS

        context["aom_pending_confirmations"] = (
            TaskAssignment.objects.filter(status=_TAS.SUBMITTED)
            .select_related("action_item", "action_item__clinic", "assignee")
            .order_by("submitted_at")[:10]
        )
        from reports.models import Laporan, ReportStatus, ReportVisibility
        from reports.models import Masukan

        context["aom_confidential_laporan_count"] = Laporan.objects.filter(
            visibility=ReportVisibility.RAHASIA_AOM
        ).exclude(status=ReportStatus.ARCHIVED).count()
        context["aom_masukan_pending_count"] = Masukan.objects.filter(
            archived_at__isnull=True
        ).count()
        from cash.services import pending_verification

        context["aom_pending_cash"] = pending_verification(user, limit=10)

    if is_pic(user):
        from .models import TaskAssignmentStatus as _TAS

        context["pic_pending_confirmations"] = (
            TaskAssignment.objects.filter(
                status=_TAS.SUBMITTED, action_item__created_by=user
            )
            .select_related("action_item", "assignee")
            .order_by("submitted_at")[:10]
        )
        from accounts.models import PicAssignment
        from checklists.models import ChecklistTemplate

        pic_functions = list(
            PicAssignment.objects.filter(user=user, clinic=clinic, active=True).values_list(
                "function", flat=True
            )
        )
        context["pic_functions"] = pic_functions
        context["pic_checklist_templates"] = ChecklistTemplate.objects.filter(
            clinic=clinic, active=True, target_pic_function__in=pic_functions
        ) if pic_functions else ChecklistTemplate.objects.none()

    if day:
        context.update(
            {
                "progress": opening_progress(day),
                "cash": cash_summary(day) if context["can_view_cash"] else None,
                "next_nurse": NurseRosterEntry.objects.filter(
                    operational_day=day, availability=Availability.TERSEDIA
                )
                .select_related("nurse")
                .order_by("position")
                .first(),
                "breaks_soon": upcoming_breaks(clinic, timezone.now(), 60)[:8],
                "issues": issue_counters(clinic),
                "closing_blockers": closing_blockers(day) if can_close_day(user) else [],
            }
        )
    return render(request, "core/dashboard.html", context)


@login_required
def today(request):
    """Tugas hari ini (fase 7, halaman pertama staf): butir checklist porsinya, task, dan kas bila kasir."""
    from breaks.models import BreakSchedule, BreakStatus
    from checklists.models import ChecklistResponse, ResponseResult
    from jadwal.services import cashier_assignments, duty_of, my_assignments

    from .task_services import my_tasks

    from .models import operational_date

    user = request.user
    clinic = active_clinic(user)
    date = operational_date(clinic) if clinic else local_today()
    day = OperationalDay.today_for(clinic) if clinic else None
    if day is None and clinic and request.GET.get("buat") == "1":
        get_or_create_day(clinic, user=user)
        messages.success(request, "Sesi hari operasional dibuat.")
        return redirect("core:today")

    duties = []
    assignments = list(my_assignments(user, date))
    responses = []
    if day:
        responses = list(
            ChecklistResponse.objects.filter(run__operational_day=day)
            .exclude(portion="").select_related("run__template")
        )
    for a in assignments:
        items = [r for r in responses if r.portion == a.portion.code and a.clinic_id == day.clinic_id] if day else []
        runs = {}
        for r in items:
            row = runs.setdefault(r.run_id, {"run": r.run, "total": 0, "done": 0})
            row["total"] += 1
            row["done"] += r.result != ResponseResult.BELUM
        done = sum(1 for r in items if r.result != ResponseResult.BELUM)
        duties.append({
            "assignment": a, "total": len(items), "done": done,
            "runs": sorted(runs.values(), key=lambda x: ({"OPENING": 0, "ANYTIME": 1, "CLOSING": 2}.get(x["run"].session, 3),
                                                        x["run"].pk)),
        })

    tasks_mine = my_tasks(user)
    cashier = list(cashier_assignments(user, date))
    breaks_today = BreakSchedule.objects.filter(user=user, date=date).exclude(
        status=BreakStatus.BATAL).order_by("start_at")
    return render(request, "core/today.html", {
        "clinic": clinic,
        "day": day,
        "today": date,
        "duty": duty_of(user, date),
        "duties": duties,
        "duties_total": sum(d["total"] for d in duties),
        "duties_done": sum(d["done"] for d in duties),
        "my_tasks": tasks_mine,
        "task_photos": task_photos([t["item"] for t in tasks_mine]),
        "my_issues": user.issue_assignments.filter(active=True).select_related("issue")[:10],
        "cashier": cashier,
        "cash": cash_summary(day) if day and cashier else None,
        "breaks_today": breaks_today,
    })


@login_required
@require_POST
def day_action(request, pk: int):
    day = get_object_or_404(OperationalDay, pk=pk)
    if not can_access_clinic(request.user, day.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke cabang ini.")
    action = request.POST.get("aksi")
    reason = request.POST.get("alasan", "")
    user = request.user

    try:
        if action == "ready":
            mark_ready(day, user)
            messages.success(request, "Hari ditandai siap.")
        elif action == "ready_issues":
            if not is_supervisor(user):
                raise PermissionDenied("Hanya supervisor yang dapat menetapkan siap dengan catatan.")
            mark_ready(day, user, with_issues=True, reason=reason)
            messages.warning(request, "Hari ditandai siap dengan catatan.")
        elif action == "open":
            open_day(day, user)
            _stamp(request, "BUKA_HARI", clinic=day.clinic, entity=day)
            messages.success(request, "Klinik dibuka.")
        elif action == "closing":
            if not can_close_day(user):
                raise PermissionDenied("Hanya supervisor yang dapat memulai penutupan.")
            start_closing(day, user)
            messages.info(request, "Proses penutupan dimulai.")
        elif action == "close":
            if not can_close_day(user):
                raise PermissionDenied("Hanya supervisor yang dapat menutup hari.")
            close_day(day, user, override_reason=reason)
            _stamp(request, "TUTUP_HARI", clinic=day.clinic, entity=day)
            messages.success(request, "Hari operasional ditutup.")
        elif action == "reopen":
            if not can_close_day(user):
                raise PermissionDenied("Hanya supervisor yang dapat membuka kembali hari.")
            reopen_day(day, user, reason=reason)
            messages.warning(request, "Hari operasional dibuka kembali.")
        else:
            messages.error(request, "Aksi tidak dikenali.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("core:dashboard")


@login_required
def action_items(request):
    clinic = active_clinic(request.user)
    status = request.GET.get("status", "")
    qs = ActionItem.objects.select_related("owner", "clinic").prefetch_related(
        "task_assignments", "task_assignments__assignee"
    )
    if status:
        qs = qs.filter(status=status)
    if is_supervisor(request.user) or is_owner(request.user):
        qs = qs.filter(clinic=clinic)
    else:
        # Task milik sendiri dari semua cabang yang dapat diakses (mis. hari perbantuan).
        qs = qs.filter(clinic__in=user_clinic_queryset(request.user)).filter(
            Q(owner=request.user) | Q(task_assignments__assignee=request.user)
        ).distinct()

    user = request.user
    rows = []
    for item in qs[:200]:
        assignments = list(item.task_assignments.all())
        my_assignment = next(
            (a for a in assignments if a.assignee_id == user.pk or a.claimed_by_id == user.pk),
            None,
        )
        can_claim = bool(
            my_assignment
            and item.assignment_mode == "BERSAMA"
            and my_assignment.claimed_by_id is None
            and my_assignment.status == TaskAssignmentStatus.OPEN
        )
        can_submit = bool(
            my_assignment
            and my_assignment.status
            in {
                TaskAssignmentStatus.OPEN,
                TaskAssignmentStatus.IN_PROGRESS,
                TaskAssignmentStatus.REVISION_REQUIRED,
            }
            and (item.assignment_mode != "BERSAMA" or my_assignment.claimed_by_id == user.pk)
        )
        review_assignments = [
            a
            for a in assignments
            if a.status == TaskAssignmentStatus.SUBMITTED and can_review_assignment(a, user)
        ]
        rows.append(
            {
                "item": item,
                "my_assignment": my_assignment,
                "can_claim": can_claim,
                "can_submit": can_submit,
                "review_assignments": review_assignments,
            }
        )
    return render(
        request,
        "core/action_items.html",
        {"rows": rows, "status": status, "statuses": ActionItemStatus.choices,
         "task_photos": task_photos([r["item"] for r in rows])},
    )


@login_required
@require_POST
def action_item_update(request, pk: int):
    item = get_object_or_404(ActionItem, pk=pk)
    if not can_access_clinic(request.user, item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke action item cabang ini.")
    from .task_services import can_manage_task

    if not (is_supervisor(request.user) or item.owner_id == request.user.pk or can_manage_task(item, request.user)):
        raise PermissionDenied("Anda bukan penanggung jawab action item ini.")
    from audit.services import log_update, snapshot

    before = snapshot(item)
    item.status = request.POST.get("status", item.status)
    item.progress_note = request.POST.get("catatan", item.progress_note)
    item.save()
    log_update(item, before, actor=request.user)
    messages.success(request, "Action item diperbarui.")
    return redirect("core:action_items")


def _stamp(request, event: str, **kwargs):
    """Jejak kehadiran (tahap 3 paket E); tidak pernah menggagalkan aksi."""
    from jejak.services import stamp

    return stamp(request, event, **kwargs)


def _back(request, default: str):
    """Kembali ke halaman asal (mis. Hari Ini) bila `next` aman; selain itu ke `default`."""
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(default)


def _assignment_or_404(pk: int) -> TaskAssignment:
    return get_object_or_404(
        TaskAssignment.objects.select_related("action_item", "action_item__clinic"), pk=pk
    )


@login_required
@require_POST
def assignment_claim(request, pk: int):
    """Ambil task bersama (mode BERSAMA) — penerima lain tetap melihat siapa pelaksana."""
    assignment = _assignment_or_404(pk)
    if not can_access_clinic(request.user, assignment.action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    try:
        claim_shared_task(assignment, user=request.user)
        messages.success(request, "Task diambil.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back(request, "core:action_items")


@login_required
@require_POST
def assignment_submit(request, pk: int):
    """Penerima mengajukan task selesai ('Ajukan selesai') — belum final, menunggu konfirmasi."""
    assignment = _assignment_or_404(pk)
    if not can_access_clinic(request.user, assignment.action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    try:
        note = request.POST.get("catatan", "").strip()
        if not note:
            # Bukti wajib berupa catatan; foto opsional (keputusan 3 Okt 2026, tahap 2 paket C).
            raise ValidationError("Tulis catatan bukti: apa yang sudah dikerjakan.")
        with transaction.atomic():
            submit_assignment(assignment, user=request.user, note=note)
            save_optional_photo(request, entity_type="taskassignment", entity_id=assignment.pk)
        _stamp(request, "AJUKAN", clinic=assignment.action_item.clinic, entity=assignment)
        who = "Direktur Utama / Owner" if assignment.action_item.reviewed_by_dirut else "pemeriksa"
        messages.success(request, f"Task diajukan selesai, menunggu konfirmasi {who}.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back(request, "core:action_items")


@login_required
@require_POST
def assignment_progress(request, pk: int):
    """Penerima melaporkan kemajuan (teks wajib, foto opsional) tanpa mengajukan selesai."""
    from .task_services import report_progress

    assignment = _assignment_or_404(pk)
    if not can_access_clinic(request.user, assignment.action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    try:
        with transaction.atomic():
            event = report_progress(assignment, user=request.user, note=request.POST.get("catatan", ""))
            save_optional_photo(request, entity_type="taskevent", entity_id=event.pk)
        _stamp(request, "PROGRES", clinic=assignment.action_item.clinic, entity=assignment)
        messages.success(request, "Progres dicatat.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back(request, "core:action_items")


@login_required
@require_POST
def assignment_confirm(request, pk: int):
    """Reviewer mengonfirmasi task selesai ('Konfirmasi selesai') — final, bukan tombol yang sama dengan ajukan."""
    assignment = _assignment_or_404(pk)
    if not can_access_clinic(request.user, assignment.action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    try:
        confirm_assignment(assignment, reviewer=request.user, note=request.POST.get("catatan", ""))
        messages.success(request, "Task dikonfirmasi selesai.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("core:action_items")


@login_required
@require_POST
def assignment_revision(request, pk: int):
    """Reviewer meminta revisi ('Minta revisi') — task kembali ke penerima dengan catatan wajib."""
    assignment = _assignment_or_404(pk)
    if not can_access_clinic(request.user, assignment.action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    try:
        request_revision(assignment, reviewer=request.user, note=request.POST.get("catatan", ""))
        messages.warning(request, "Revisi diminta.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("core:action_items")


@login_required
@require_POST
def assignment_cancel(request, pk: int):
    """Pemberi tugas atau AOM membatalkan assignment — wajib alasan."""
    assignment = _assignment_or_404(pk)
    if not can_access_clinic(request.user, assignment.action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    try:
        cancel_assignment(assignment, actor=request.user, reason=request.POST.get("alasan", ""))
        messages.warning(request, "Task dibatalkan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("core:action_items")


@login_required
def attachment_download(request, pk: int):
    """Lampiran selalu melewati pemeriksaan izin aplikasi (PRD 9.3, 20.7)."""
    attachment = get_object_or_404(Attachment, pk=pk)
    from .photos import assert_can_view

    assert_can_view(request.user, attachment)

    log_event(
        action=AuditAction.DOWNLOAD_ATTACHMENT,
        entity_type="attachment",
        entity_id=attachment.pk,
        entity_label=attachment.original_name,
        actor=request.user,
        request=request,
    )
    content_type = attachment.mime_type or mimetypes.guess_type(attachment.original_name)[0]
    # Foto dibuka langsung di browser (?lihat=1); berkas lain selalu diunduh.
    inline = request.GET.get("lihat") == "1" and (content_type or "").startswith("image/")
    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=not inline,
        filename=attachment.original_name,
        content_type=content_type or "application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
@require(can_manage_config)
def config_page(request):
    clinic = active_clinic(request.user)
    if request.method == "POST":
        key = request.POST.get("kunci", "").strip()
        raw = request.POST.get("nilai", "").strip()
        if key:
            import json

            try:
                value = json.loads(raw)
            except ValueError:
                value = raw
            before = {"key": key, "value": ClinicConfig.get(clinic, key)}
            ClinicConfig.set(clinic, key, value, user=request.user)
            log_event(
                action=AuditAction.CONFIG_CHANGED,
                entity_type="clinicconfig",
                entity_id=key,
                entity_label=key,
                actor=request.user,
                before=before,
                after={"key": key, "value": value},
            )
            messages.success(request, f"Konfigurasi {key} disimpan.")
        return redirect("core:config")

    overrides = {c.key: c.value for c in ClinicConfig.objects.filter(clinic=clinic)}
    rows = []
    for key, default in DEFAULT_CONFIG.items():
        rows.append(
            {
                "key": key,
                "default": default,
                "value": overrides.get(key, default),
                "overridden": key in overrides,
            }
        )
    return render(request, "core/config.html", {"rows": rows, "clinic": clinic})


CLINIC_PROFILE_FIELDS = ("name", "address", "phone", "open_time", "close_time", "dpj_name", "apj_name",
                         "latitude", "longitude", "radius_m")


def _parse_clinic_form(post) -> dict:
    import datetime as dt

    data = {
        "name": post.get("nama", "").strip(),
        "address": post.get("alamat", "").strip(),
        "phone": post.get("hp", "").strip(),
        "dpj_name": post.get("dpj", "").strip(),
        "apj_name": post.get("apj", "").strip(),
    }
    if not data["name"]:
        raise ValidationError("Nama klinik wajib diisi.")
    try:
        data["open_time"] = dt.time.fromisoformat(post.get("buka", ""))
        data["close_time"] = dt.time.fromisoformat(post.get("tutup", ""))
    except ValueError:
        raise ValidationError("Jam buka dan jam tutup wajib diisi (JJ:MM).")
    if data["close_time"] <= data["open_time"]:
        raise ValidationError("Jam tutup harus sesudah jam buka.")
    data.update(_parse_coordinates(post))
    return data


def _parse_coordinates(post) -> dict:
    """Lintang/bujur cabang untuk jejak kehadiran; boleh kosong (belum diisi)."""
    from decimal import Decimal, InvalidOperation

    raw_lat, raw_lng = post.get("lintang", "").strip(), post.get("bujur", "").strip()
    if not raw_lat and not raw_lng:
        lat = lng = None
    else:
        try:
            lat, lng = Decimal(raw_lat.replace(",", ".")), Decimal(raw_lng.replace(",", "."))
        except (InvalidOperation, ValueError):
            raise ValidationError("Lintang dan bujur harus angka desimal, mis. -7.312345 dan 112.745678.")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValidationError("Lintang harus -90..90 dan bujur -180..180.")
        lat, lng = lat.quantize(Decimal("0.000001")), lng.quantize(Decimal("0.000001"))
    try:
        radius = int(post.get("radius") or 150)
    except ValueError:
        raise ValidationError("Radius harus angka meter.")
    if not 30 <= radius <= 2000:
        raise ValidationError("Radius antara 30 dan 2000 meter.")
    return {"latitude": lat, "longitude": lng, "radius_m": radius}


@login_required
def clinic_profile(request):
    """Pengaturan klinik: nama, alamat, nomor HP, jam buka/tutup, DPJ, APJ."""
    from audit.services import log_update, snapshot

    from .models import Clinic
    from .permissions import can_edit_clinic_profile, can_view_clinic_profile

    if not can_view_clinic_profile(request.user):
        raise PermissionDenied("Halaman ini untuk Admin, Direktur Operasional, dan Owner.")
    can_edit = can_edit_clinic_profile(request.user)
    clinics = Clinic.objects.order_by("id")
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied("Owner hanya dapat membaca pengaturan klinik.")
        clinic = get_object_or_404(Clinic, pk=request.POST.get("klinik"))
        try:
            data = _parse_clinic_form(request.POST)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("core:clinic_profile")
        before = snapshot(clinic, CLINIC_PROFILE_FIELDS)
        for field, value in data.items():
            setattr(clinic, field, value)
        clinic.save(update_fields=list(data))
        log_update(clinic, before, actor=request.user, action=AuditAction.CONFIG_CHANGED)
        messages.success(request, f"Pengaturan {clinic.name} disimpan.")
        return redirect("core:clinic_profile")
    return render(request, "core/clinic_profile.html", {"clinics": clinics, "can_edit": can_edit})
