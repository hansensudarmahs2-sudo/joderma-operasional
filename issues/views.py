"""View issue: komplain, masukan, kerusakan (PRD 8.7-8.9)."""
from __future__ import annotations

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from audit.models import AuditAction
from audit.services import log_event
from core.models import Attachment, Priority
from core.permissions import (
    can_access_clinic,
    can_assign_issue,
    can_view_restricted_issue,
    clinic_member_q,
    is_aom,
    is_owner,
    is_supervisor,
    require,
)
from core.peran import OWNER, persona
from core.photos import save_optional_photo, save_photo
from core.services import active_clinic

from .forms import AttachmentForm, IssueForm
from .models import Asset, Issue, IssueStatus, IssueType, OPEN_STATUSES
from .services import (
    add_update,
    assign_issue,
    change_status,
    create_issue,
    issue_counters,
    mark_asset_do_not_use,
    record_repair,
)


TYPE_LABELS = {
    IssueType.KOMPLAIN: ("Komplain", "Catat keluhan dari pasien, keluarga, atau staf."),
    IssueType.MASUKAN: ("Masukan/saran", "Usulan perbaikan cara kerja atau fasilitas."),
    IssueType.KERUSAKAN: (
        "Laporan kerusakan",
        "Fasilitas, alat medis, IT, listrik, air, furnitur, atau keselamatan.",
    ),
}


def _visible_issues(user, clinic):
    """Catatan terbatas hanya terlihat pembuat, assignee, supervisor, owner. `clinic` boleh daftar cabang."""
    clinics = clinic if isinstance(clinic, (list, tuple)) else [clinic]
    qs = Issue.objects.filter(clinic__in=clinics).select_related("created_by", "asset", "clinic")
    if is_supervisor(user) or is_owner(user) or is_aom(user):
        return qs
    return qs.filter(
        Q(is_restricted=False)
        | Q(created_by=user)
        | Q(assignments__assignee=user, assignments__active=True)
    ).distinct()


@login_required
def list_view(request):
    from core.services import list_branch_scope

    branch = list_branch_scope(request)
    qs = _visible_issues(request.user, branch["scope"])

    issue_type = request.GET.get("tipe") or ""
    status = request.GET.get("status") or ""
    q = request.GET.get("q") or ""
    only_open = request.GET.get("terbuka") == "1"

    if issue_type:
        qs = qs.filter(issue_type=issue_type)
    if status:
        qs = qs.filter(status=status)
    if only_open:
        qs = qs.filter(status__in=OPEN_STATUSES)
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q) | Q(location__icontains=q))

    heading, subtitle = TYPE_LABELS.get(
        issue_type, ("Komplain, masukan, dan kerusakan", "Semua catatan operasional klinik.")
    )
    return render(
        request,
        "issues/list.html",
        {
            "issues": qs[:200],
            "counters": issue_counters(branch["scope"]),
            **branch,
            "types": IssueType.choices,
            "statuses": IssueStatus.choices,
            "filters": {"tipe": issue_type, "status": status, "q": q, "terbuka": only_open},
            "heading": heading,
            "subtitle": subtitle,
            "active_type": issue_type,
            "see_reporter": is_supervisor(request.user) or is_owner(request.user) or is_aom(request.user),
        },
    )


@login_required
def create(request):
    clinic = active_clinic(request.user)
    initial_type = request.GET.get("tipe") or ""
    form = IssueForm(request.POST or None, clinic=clinic, initial_type=initial_type)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            with transaction.atomic():
                issue = create_issue(
                    clinic=clinic,
                    issue_type=data["issue_type"],
                    title=data["title"],
                    user=request.user,
                    description=data.get("description", ""),
                    severity=data.get("severity") or Priority.SEDANG,
                    category=data.get("category", ""),
                    is_restricted=data.get("is_restricted", False),
                    is_anonymous=data.get("is_anonymous", False),
                    reporter_source=data.get("reporter_source", ""),
                    reporter_contact=data.get("reporter_contact", ""),
                    channel=data.get("channel", ""),
                    occurred_at=data.get("occurred_at"),
                    followup_preference=data.get("followup_preference", ""),
                    benefit=data.get("benefit", ""),
                    location=data.get("location", ""),
                    asset=data.get("asset"),
                    impact=data.get("impact", ""),
                )
                save_optional_photo(request, entity_type="issue", entity_id=issue.pk,
                                    sensitive=issue.is_restricted)
            messages.success(request, f"Catatan {issue.number} dibuat.")
            return redirect("issues:detail", pk=issue.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))

    heading, subtitle = TYPE_LABELS.get(initial_type, ("Catatan baru", ""))
    return render(
        request,
        "issues/form.html",
        {
            "form": form,
            "heading": heading,
            "subtitle": subtitle,
            "initial_type": initial_type,
            "type_field_map": json.dumps(form.type_field_map()),
        },
    )


@login_required
def detail(request, pk: int):
    issue = get_object_or_404(Issue, pk=pk)
    if not can_view_restricted_issue(request.user, issue):
        raise PermissionDenied("Catatan ini terbatas dan tidak dapat Anda akses.")
    if issue.is_restricted:
        log_event(
            action=AuditAction.VIEW_RESTRICTED,
            entity_type="issue",
            entity_id=issue.pk,
            entity_label=issue.number,
            actor=request.user,
            request=request,
        )
    attachments = Attachment.objects.filter(entity_type="issue", entity_id=issue.pk)
    return render(
        request,
        "issues/detail.html",
        {
            "issue": issue,
            "updates": issue.updates.select_related("author"),
            "attachments": attachments,
            "read_only": persona(request.user) == OWNER,
            "see_reporter": is_supervisor(request.user) or is_owner(request.user) or is_aom(request.user),
            "photos": [a for a in attachments if (a.mime_type or "").startswith("image/")],
            "next_statuses": sorted(
                (s, dict(IssueStatus.choices).get(s, s)) for s in issue.allowed_next_statuses()
            ),
            "can_assign": can_assign_issue(request.user),
            "users": User.objects.filter(clinic_member_q(issue.clinic), is_active=True)
            .distinct()
            .order_by("username"),
            "attachment_form": AttachmentForm(),
        },
    )


@login_required
@require_POST
def change_status_view(request, pk: int):
    issue = get_object_or_404(Issue, pk=pk)
    if not can_view_restricted_issue(request.user, issue):
        raise PermissionDenied("Akses ditolak.")
    try:
        change_status(
            issue,
            user=request.user,
            to_status=request.POST.get("status", ""),
            note=request.POST.get("catatan", ""),
            resolution_summary=request.POST.get("ringkasan", ""),
            reason=request.POST.get("alasan", ""),
            expected_version=int(request.POST.get("versi") or issue.version),
        )
        messages.success(request, "Status catatan diperbarui.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError:
        messages.error(request, "Versi data tidak valid. Muat ulang halaman.")
    return redirect("issues:detail", pk=issue.pk)


@login_required
@require(can_assign_issue)
@require_POST
def assign_view(request, pk: int):
    issue = get_object_or_404(Issue, pk=pk)
    if not can_view_restricted_issue(request.user, issue):
        raise PermissionDenied("Akses ditolak.")
    assignee = get_object_or_404(User, pk=request.POST.get("penanggung_jawab"))
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone as tz

    due_raw = request.POST.get("target")
    due_at = parse_datetime(due_raw) if due_raw else None
    if due_at and tz.is_naive(due_at):
        due_at = tz.make_aware(due_at, tz.get_current_timezone())
    try:
        assign_issue(issue, supervisor=request.user, assignee=assignee, due_at=due_at)
        messages.success(request, f"Ditugaskan kepada {assignee}.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("issues:detail", pk=issue.pk)


@login_required
@require_POST
def add_note(request, pk: int):
    issue = get_object_or_404(Issue, pk=pk)
    if not can_view_restricted_issue(request.user, issue):
        raise PermissionDenied("Akses ditolak.")
    try:
        add_update(issue, user=request.user, note=request.POST.get("catatan", ""))
        messages.success(request, "Catatan ditambahkan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("issues:detail", pk=issue.pk)


@login_required
@require_POST
def repair(request, pk: int):
    issue = get_object_or_404(Issue, pk=pk)
    if not can_view_restricted_issue(request.user, issue):
        raise PermissionDenied("Akses ditolak.")
    try:
        cost = request.POST.get("biaya")
        record_repair(
            issue,
            user=request.user,
            repair_action=request.POST.get("tindakan", ""),
            vendor=request.POST.get("vendor", ""),
            cost=int(cost) if cost else None,
        )
        messages.success(request, "Data perbaikan tersimpan.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except ValueError:
        messages.error(request, "Biaya harus berupa angka.")
    return redirect("issues:detail", pk=issue.pk)


@login_required
@require_POST
def upload_attachment(request, pk: int):
    issue = get_object_or_404(Issue, pk=pk)
    if not can_view_restricted_issue(request.user, issue):
        raise PermissionDenied("Akses ditolak.")
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        upload = form.cleaned_data["file"]
        if (upload.content_type or "").startswith("image/"):
            # Foto: dikompres (maks. 20 MB sebelum kompresi), EXIF/GPS dibuang.
            try:
                save_photo(upload, entity_type="issue", entity_id=issue.pk, user=request.user,
                           sensitive=issue.is_restricted)
                messages.success(request, "Foto diunggah.")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        elif upload.size > settings.ATTACHMENT_MAX_BYTES:
            messages.error(request, "Ukuran berkas melebihi batas 5 MB.")
        elif upload.content_type not in settings.ATTACHMENT_ALLOWED_MIME:
            messages.error(request, "Format berkas harus JPG, PNG, atau PDF.")
        else:
            attachment = Attachment.objects.create(
                entity_type="issue",
                entity_id=issue.pk,
                file=upload,
                original_name=upload.name[:255],
                mime_type=upload.content_type,
                size_bytes=upload.size,
                sensitive=issue.is_restricted,
                uploaded_by=request.user,
            )
            log_event(
                action=AuditAction.CREATE,
                entity_type="attachment",
                entity_id=attachment.pk,
                entity_label=attachment.original_name,
                actor=request.user,
            )
            messages.success(request, "Lampiran diunggah.")
    else:
        messages.error(request, "Berkas tidak valid.")
    return redirect("issues:detail", pk=issue.pk)


@login_required
def asset_list(request):
    clinic = active_clinic(request.user)
    return render(
        request,
        "issues/assets.html",
        {
            "assets": Asset.objects.filter(clinic=clinic),
            "can_manage": is_supervisor(request.user),
        },
    )


@login_required
@require(is_supervisor)
@require_POST
def asset_block(request, pk: int):
    asset = get_object_or_404(Asset, pk=pk)
    if not can_access_clinic(request.user, asset.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke aset cabang ini.")
    try:
        mark_asset_do_not_use(asset, supervisor=request.user, reason=request.POST.get("alasan", ""))
        messages.warning(request, f"{asset.name} ditandai 'Jangan digunakan'.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("issues:assets")
