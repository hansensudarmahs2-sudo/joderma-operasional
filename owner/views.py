"""Tampilan Owner / Direktur Utama: Dashboard, Permintaan, Summary Harian, Jadwal.

Menu Owner dibangun di `core/peran.py`; halaman di luar tampilan ini ditolak oleh
`core.middleware.PersonaAccessMiddleware`. Angka ringkasan memakai fungsi yang sama dengan
Ringkasan Direktur (`direktur.dashboard`), supaya keduanya tidak pernah berbeda.
"""
from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import Clinic, local_today
from core.photos import photos_for, save_optional_photo
from core.permissions import is_aom, is_owner, require, user_clinic_queryset
from direktur import dashboard
from direktur.models import DailySummary

from . import services, usulan
from .models import OwnerRequest, Usulan, UsulanKind, UsulanStatus

DAYS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _date(raw: str | None, default: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        return default


def _day_label(day: dt.date) -> str:
    return f"{DAYS[day.weekday()]}, {day:%d/%m/%Y}"


def _inbox_counts(user):
    from reports.inbox import can_view_inbox, open_counts

    return open_counts(user) if can_view_inbox(user) else None


@login_required
@require(dashboard.can_view_overview)
def dashboard_page(request):
    user = request.user
    return render(
        request,
        "owner/dashboard.html",
        {
            "inbox": _inbox_counts(request.user),
            "bird": dashboard.bird_view(user),
            "matrix": dashboard.eisenhower(user, limit=1),
            "counts": dashboard.headline_counts(user),
            "agenda": dashboard.meeting_agenda(user),
            "awaiting": services.decisions_awaiting(user),
            "usulan": usulan.usulan_awaiting(user),
            "requests": services.request_rows(user),
            "verify": services.verification_queue(user),
            "achievements": services.recent_achievements(user),
            "can_create": services.can_create_request(user),
            "today": local_today(),
        },
    )


@login_required
@require(services.can_create_request)
def request_new(request):
    from core.permissions import user_clinic_queryset

    from .models import RequestKind

    form = {"judul": "", "rincian": "", "target": "", "cabang": "", "mendesak": ""}
    temuan = (request.POST.get("jenis") or request.GET.get("jenis")) == RequestKind.TEMUAN
    clinics = list(user_clinic_queryset(request.user).order_by("id"))
    if request.method == "POST":
        form = {k: request.POST.get(k, "") for k in form}
        clinic = next((c for c in clinics if form["cabang"].isascii() and form["cabang"].isdigit() and c.pk == int(form["cabang"])), None)
        try:
            with transaction.atomic():
                req = services.create_request(
                    actor=request.user,
                    kind=RequestKind.TEMUAN if temuan else RequestKind.PERMINTAAN,
                    title=form["judul"],
                    description=form["rincian"],
                    target_date=None if temuan else services.parse_target(form["target"]),
                    clinic=clinic,
                    urgent=form["mendesak"] == "1",
                )
                save_optional_photo(request, entity_type="ownerrequest", entity_id=req.pk)
            messages.success(request, ("Temuan" if temuan else "Permintaan") + " dikirim ke Direktur Operasional.")
            return redirect("owner:request_detail", pk=req.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return render(request, "owner/request_form.html",
                  {"form": form, "today": local_today(), "temuan": temuan, "clinics": clinics})


@login_required
@require(services.can_view_requests)
def request_detail(request, pk: int):
    req = get_object_or_404(OwnerRequest.objects.select_related("created_by", "clinic"), pk=pk)
    if request.method == "POST" and request.POST.get("aksi") in ("rencana", "selesai"):
        return _finding_action(request, req)
    if request.method == "POST" and request.POST.get("aksi") == "task":
        return _request_task(request, req)
    if request.method == "POST" and request.POST.get("aksi") in ("usul_target", "setujui_target", "tolak_target"):
        return _target_action(request, req)
    if request.method == "POST":
        try:
            with transaction.atomic():
                note = services.add_note(req, actor=request.user, body=request.POST.get("catatan", ""))
                save_optional_photo(request, entity_type="ownerrequestnote", entity_id=note.pk)
            messages.success(request, "Catatan disimpan.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("owner:request_detail", pk=req.pk)
    notes = list(req.notes.select_related("author"))
    cap = services.deadline_cap(req)
    task_form = {}
    if is_aom(request.user):
        from direktur.views import branch_context

        from core.models import Priority
        from core.permissions import user_clinic_queryset

        task_form = {**branch_context(request, user_clinic_queryset(request.user).order_by("id"),
                                      default=req.clinic_id), "priorities": Priority.choices}
    from reports.models import InboxTriage

    triage = InboxTriage.objects.filter(source_type="permintaan_owner", source_id=req.pk).select_related(
        "triaged_by", "decision").first()
    return render(
        request,
        "owner/request_detail.html",
        {
            "row": services.progress(req),
            "notes": notes,
            "photos": photos_for("ownerrequest", [req.pk]).get(req.pk, []),
            "note_photos": photos_for("ownerrequestnote", [n.pk for n in notes]),
            "is_director": is_aom(request.user),
            "task_form": task_form,
            "triage": triage,
            "subtasks": services.subtask_rows(req) if req.kind == "TEMUAN" else [],
            "cap": cap,
            "plan_max": max(filter(None, [cap, req.target_date]), default=None),
            "pending_target": services.has_pending_target(req),
            "is_owner": is_owner(request.user),
            "today": local_today(),
        },
    )


def _target_action(request, req):
    """Direktur mengusulkan target baru; Owner menyetujui atau menolaknya."""
    aksi = request.POST.get("aksi")
    try:
        with transaction.atomic():
            if aksi == "usul_target":
                if not is_aom(request.user):
                    raise PermissionDenied("Hanya Direktur Operasional yang mengusulkan target.")
                try:
                    day = dt.date.fromisoformat((request.POST.get("target_baru") or "").strip())
                except ValueError:
                    raise ValidationError("Tanggal tidak valid.")
                services.propose_target(req, actor=request.user, target_date=day,
                                        reason=request.POST.get("alasan", ""))
                messages.success(request, "Usulan target dikirim ke Owner.")
            else:
                approve = aksi == "setujui_target"
                services.decide_target(req, actor=request.user, approve=approve, note=request.POST.get("catatan", ""),
                                        expected=request.POST.get("usulan") or None)
                messages.success(request, "Target baru disetujui; Direktur Operasional diberi tahu." if approve
                                 else "Usulan target ditolak; Direktur Operasional diberi tahu.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("owner:request_detail", pk=req.pk)


def _finding_action(request, req):
    """Direktur: simpan rencana penanganan temuan, atau nyatakan temuan selesai & terverifikasi."""
    try:
        with transaction.atomic():
            if request.POST.get("aksi") == "rencana":
                services.set_plan(
                    req, actor=request.user, plan_title=request.POST.get("rencana", ""),
                    target_date=services.parse_target(request.POST.get("target", ""), required=False),
                )
                messages.success(request, "Rencana penanganan disimpan.")
            else:
                services.complete_finding(req, actor=request.user)
                messages.success(request, "Temuan dinyatakan selesai & terverifikasi.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("owner:request_detail", pk=req.pk)


def _request_task(request, req):
    """Direktur menambah task untuk permintaan/temuan ini (langkah kedua dst., atau semua cabang)."""
    from direktur import services as direktur
    from direktur.views import branch_targets

    from core.permissions import user_clinic_queryset

    if not is_aom(request.user):
        raise PermissionDenied("Hanya Direktur Operasional yang memecah permintaan menjadi task.")
    try:
        pairs = branch_targets(request.POST, user_clinic_queryset(request.user).order_by("id"))
        with transaction.atomic():
            items = [
                direktur.create_task_from_source(
                    actor=request.user, clinic=clinic, title=request.POST.get("judul", ""), target=who,
                    description=request.POST.get("uraian", ""),
                    priority=request.POST.get("prioritas", "SEDANG"),
                    due_at=direktur.parse_due(request.POST.get("batas", "")),
                    source_type="permintaan_owner", source_id=req.pk,
                    source_label=f"{req.get_kind_display()} P-{req.pk}",
                )
                for clinic, who in pairs
            ]
        where = f" untuk {len(items)} cabang" if len(items) > 1 else ""
        messages.success(request, f"Task ditambahkan{where}: {items[0].title}.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("owner:request_detail", pk=req.pk)


@login_required
@require(services.can_view_requests)
def decision_page(request, pk: int):
    """Permintaan keputusan Direktur untuk Owner (7 Okt 2026). Direktur boleh membaca; hanya Owner memutuskan."""
    from direktur.dashboard import decisions_for
    from direktur.models import DecisionStatus
    from direktur.services import is_owner_decision

    decision = get_object_or_404(decisions_for(request.user).select_related("created_by", "decided_by"), pk=pk)
    if request.method == "POST":
        try:
            services.decide(decision, actor=request.user, verdict=request.POST.get("aksi", ""),
                            note=request.POST.get("catatan", ""))
            if request.POST.get("aksi", "") == "rapat":
                messages.success(request, "Dibawa ke rapat Kamis; Direktur Operasional sudah diberi tahu.")
            else:
                messages.success(request, "Keputusan dikirim ke Direktur Operasional.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("owner:decision", pk=pk)
    return render(request, "owner/decision.html", {
        "decision": decision,
        "tasks": list(decision.waiting_tasks.select_related("clinic").prefetch_related("task_assignments__assignee")),
        "can_decide": is_owner(request.user) and decision.status == DecisionStatus.MENUNGGU
        and is_owner_decision(decision),
    })


@login_required
@require(services.can_view_summary)
def summary(request):
    today = local_today()
    day = _date(request.GET.get("tanggal") or request.POST.get("tanggal"), today)
    item = DailySummary.objects.filter(date=day).select_related("sent_by").first()
    if request.method == "POST":
        if item is None:
            messages.error(request, "Belum ada summary untuk tanggal ini.")
        else:
            try:
                services.add_summary_note(item, actor=request.user, body=request.POST.get("isi", ""))
                messages.success(request, "Tanggapan dikirim.")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        return redirect(reverse("owner:summary") + f"?tanggal={day:%Y-%m-%d}")
    services.record_summary_read(item, request.user)
    recent = list(DailySummary.objects.select_related("sent_by").annotate(n_notes=Count("notes")).order_by("-date")[:14])
    for r in recent:
        r.is_read = services.summary_is_read(r)
    return render(
        request,
        "owner/summary.html",
        {
            "day": day,
            "day_label": _day_label(day),
            "summary": item,
            "reads": services.summary_reads(item) if item else [],
            "notes": list(item.notes.select_related("author")) if item else [],
            "prev": day - dt.timedelta(days=1),
            "next": day + dt.timedelta(days=1) if day < today else None,
            "today": today,
            "recent": recent,
        },
    )


@login_required
@require(services.can_view_summary)
def summary_pdf(request):
    """Unduh Summary Harian satu tanggal sebagai PDF (5 Okt 2026)."""
    from django.http import Http404, HttpResponse

    from .summary_pdf import build

    day = _date(request.GET.get("tanggal"), local_today())
    item = DailySummary.objects.filter(date=day).select_related("sent_by").first()
    if item is None:
        raise Http404("Belum ada summary untuk tanggal ini.")
    response = HttpResponse(build(item), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="summary-harian-{day:%Y-%m-%d}.pdf"'
    return response


@login_required
@require(dashboard.can_view_overview)
def jadwal(request):
    clinics = list(user_clinic_queryset(request.user).order_by("id"))
    if not clinics:
        raise PermissionDenied("Tidak ada cabang yang dapat Anda lihat.")
    clinic = next((c for c in clinics if str(c.pk) == request.GET.get("cabang")), clinics[0])
    today = local_today()
    day = _date(request.GET.get("tanggal"), today)
    return render(
        request,
        "owner/jadwal.html",
        {
            "clinics": clinics,
            "clinic": clinic,
            "day": day,
            "day_label": _day_label(day),
            "today": today,
            "prev": day - dt.timedelta(days=1),
            "next": day + dt.timedelta(days=1),
            "duty": services.duty_today(clinic, day),
        },
    )


# --- Usulan Direktur ke Owner (tahap 4) -------------------------------------------------

NOMINAL_MAX = 999_999_999_999


@login_required
@require(usulan.can_view_usulan)
def usulan_list(request):
    semua = request.GET.get("semua") == "1"
    rows = Usulan.objects.select_related("created_by", "clinic")
    if not semua:
        rows = rows.filter(status__in=(UsulanStatus.MENUNGGU, UsulanStatus.TERKIRIM))
    return render(request, "owner/usulan_list.html", {
        "rows": rows, "semua": semua, "can_create": is_aom(request.user), "today": local_today(),
    })


@login_required
@require(usulan.can_view_usulan)
def usulan_new(request):
    if not is_aom(request.user):
        raise PermissionDenied("Usulan dibuat oleh Direktur Operasional.")
    form = {"jenis": UsulanKind.PERSETUJUAN, "judul": "", "uraian": "", "nominal": "", "cabang": "", "batas": ""}
    clinics = list(user_clinic_queryset(request.user).order_by("id"))
    if request.method == "POST":
        form = {k: request.POST.get(k, "") for k in form}
        clinic = next((c for c in clinics if form["cabang"].isascii() and form["cabang"].isdigit() and c.pk == int(form["cabang"])), None)
        try:
            amount = None
            raw = form["nominal"].replace(".", "").replace(" ", "")
            if raw:
                if not (raw.isascii() and raw.isdigit()):
                    raise ValidationError("Nominal harus angka.")
                amount = int(raw)
                if amount > NOMINAL_MAX:
                    raise ValidationError("Nominal terlalu besar.")
            needed_by = None
            if form["batas"]:
                try:
                    needed_by = dt.date.fromisoformat(form["batas"])
                except ValueError:
                    raise ValidationError("Tanggal tidak valid.")
            item = usulan.create_usulan(
                actor=request.user, kind=form["jenis"], title=form["judul"], description=form["uraian"],
                amount=amount, clinic=clinic, needed_by=needed_by,
            )
            messages.success(request, "Usulan dikirim ke Owner.")
            return redirect("owner:usulan_detail", pk=item.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return render(request, "owner/usulan_form.html", {
        "form": form, "clinics": clinics, "today": local_today(), "nominal_max": NOMINAL_MAX,
        "kinds": UsulanKind.choices,
    })


@login_required
@require(usulan.can_view_usulan)
def usulan_detail(request, pk: int):
    item = get_object_or_404(
        Usulan.objects.select_related("created_by", "clinic", "decided_by", "read_by", "cancelled_by", "decision"),
        pk=pk,
    )
    if request.method == "POST":
        aksi = request.POST.get("aksi", "")
        try:
            if aksi in usulan.VERDICTS:
                usulan.decide_usulan(item, actor=request.user, verdict=aksi, note=request.POST.get("catatan", ""))
                messages.success(request, "Dibawa ke rapat Kamis; Direktur Operasional sudah diberi tahu."
                                 if aksi == "rapat" else "Keputusan dikirim ke Direktur Operasional.")
            elif aksi == "dibaca":
                usulan.mark_read(item, actor=request.user)
                messages.success(request, "Ditandai sudah dibaca.")
            elif aksi == "catatan":
                usulan.add_usulan_note(item, actor=request.user, note=request.POST.get("catatan", ""))
                messages.success(request, "Catatan terkirim.")
            elif aksi == "batal":
                usulan.cancel_usulan(item, actor=request.user, reason=request.POST.get("alasan", ""))
                messages.success(request, "Usulan dibatalkan.")
            else:
                messages.error(request, "Aksi tidak dikenal.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("owner:usulan_detail", pk=item.pk)
    owner = is_owner(request.user)
    director = is_aom(request.user)
    return render(request, "owner/usulan_detail.html", {
        "u": item,
        "notes": list(item.notes.select_related("author")),
        "overdue": item.is_overdue(local_today()),
        "can_decide": owner and item.kind == UsulanKind.PERSETUJUAN and item.status == UsulanStatus.MENUNGGU,
        "can_mark_read": owner and item.kind == UsulanKind.LAPORAN and item.status == UsulanStatus.TERKIRIM,
        "can_cancel": director and item.is_open,
        "can_note": owner or director,
    })
