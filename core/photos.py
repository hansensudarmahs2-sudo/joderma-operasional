"""Foto lampiran (K-016: foto temuan opsional, dikompres).

Satu pintu untuk semua foto: butir checklist bermasalah, Komplain/Masukan/Kerusakan, temuan
Owner/Direktur, dan bukti task selesai. Foto dari kamera HP dikompres dua kali:

- di browser (lihat ``static/js`` di ``base.html``: ``input[data-photo]``) supaya unggahan lewat
  data seluler kecil;
- di server dengan Pillow: diputar sesuai EXIF, sisi terpanjang maks. ``PHOTO_MAX_SIDE`` px,
  disimpan sebagai JPEG kualitas ``PHOTO_QUALITY``. Metadata EXIF (termasuk lokasi GPS) dibuang.

Foto disimpan sebagai `core.Attachment` (di luar folder publik) dan hanya bisa dibuka lewat
`core:attachment`, yang memeriksa izin per jenis entitas (`can_view_attachment`).
"""
from __future__ import annotations

import io
import os
import re
import zipfile

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile

from audit.models import AuditAction
from audit.services import log_event

from .models import Attachment

PHOTO_MAX_SIDE = 1600
PHOTO_QUALITY = 75
PHOTO_MAX_UPLOAD = 20 * 1024 * 1024  # sebelum kompresi; foto HP modern 3–12 MB
DOC_MAX_UPLOAD = 10 * 1024 * 1024
DOC_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def compress_photo(upload) -> tuple[bytes, int, int]:
    """Kembalikan (jpeg_bytes, lebar, tinggi). Menolak berkas yang bukan gambar."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if upload.size > PHOTO_MAX_UPLOAD:
        raise ValidationError("Foto terlalu besar (maks. 20 MB sebelum dikompres).")
    try:
        upload.seek(0)
        image = Image.open(upload)
        image.load()
    except (UnidentifiedImageError, OSError):
        raise ValidationError("Berkas bukan foto yang dapat dibaca (pakai JPG atau PNG).")
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        background = Image.new("RGB", image.size, "white")
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1])
            image = background
        else:
            image = image.convert("RGB")
    image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=PHOTO_QUALITY, optimize=True)
    return out.getvalue(), image.width, image.height


def save_photo(upload, *, entity_type: str, entity_id: int, user, sensitive: bool = False) -> Attachment:
    data, _, _ = compress_photo(upload)
    base = (getattr(upload, "name", "") or "foto").rsplit(".", 1)[0][:200] or "foto"
    attachment = Attachment(
        entity_type=entity_type,
        entity_id=entity_id,
        original_name=f"{base}.jpg",
        mime_type="image/jpeg",
        size_bytes=len(data),
        sensitive=sensitive,
        uploaded_by=user,
    )
    attachment.file.save("foto.jpg", ContentFile(data), save=False)
    attachment.save()
    log_event(action=AuditAction.CREATE, entity_type="attachment", entity_id=attachment.pk,
              entity_label=f"foto {entity_type}#{entity_id}", actor=user)
    return attachment


def save_optional_photo(request, field: str = "foto", **kwargs) -> Attachment | None:
    """Simpan foto dari ``request.FILES[field]`` bila ada. ValidationError diteruskan ke pemanggil."""
    upload = request.FILES.get(field)
    if not upload:
        return None
    return save_photo(upload, user=request.user, **kwargs)


def _doc_ext(upload) -> str:
    return os.path.splitext(getattr(upload, "name", "") or "")[1].lower()


def save_document(upload, *, entity_type: str, entity_id: int, user) -> Attachment:
    """Simpan PDF atau DOCX apa adanya (tanpa kompresi) setelah memeriksa ekstensi, ukuran, dan isi."""
    ext = _doc_ext(upload)
    if ext not in DOC_TYPES:
        raise ValidationError("Berkas bukan PDF atau DOCX yang sah.")
    if upload.size > DOC_MAX_UPLOAD:
        raise ValidationError("Dokumen terlalu besar (maks. 10 MB).")
    upload.seek(0)
    data = upload.read()
    valid = False
    if ext == ".pdf":
        valid = data.startswith(b"%PDF-")
    else:
        buf = io.BytesIO(data)
        if zipfile.is_zipfile(buf):
            try:
                with zipfile.ZipFile(buf) as z:
                    valid = "word/document.xml" in z.namelist()
            except zipfile.BadZipFile:
                valid = False
    if not valid:
        raise ValidationError("Berkas bukan PDF atau DOCX yang sah.")
    name = os.path.basename((getattr(upload, "name", "") or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    base, clean_ext = os.path.splitext(name)
    clean_ext = clean_ext.lower() or ext
    if not base.strip():
        name = "dokumen" + clean_ext
    elif len(name) > 200:
        name = base[: 200 - len(clean_ext)] + clean_ext
    attachment = Attachment(
        entity_type=entity_type,
        entity_id=entity_id,
        original_name=name,
        mime_type=DOC_TYPES[ext],
        size_bytes=len(data),
        uploaded_by=user,
    )
    attachment.file.save("dokumen" + ext, ContentFile(data), save=False)
    attachment.save()
    log_event(action=AuditAction.CREATE, entity_type="attachment", entity_id=attachment.pk,
              entity_label=f"dokumen {entity_type}#{entity_id}", actor=user)
    return attachment


def save_optional_attachment(request, field: str = "foto", **kwargs) -> Attachment | None:
    """Foto (dikompres) atau dokumen PDF/DOCX dari ``request.FILES[field]``. ValidationError diteruskan."""
    upload = request.FILES.get(field)
    if not upload:
        return None
    if _doc_ext(upload) in DOC_TYPES:
        return save_document(upload, user=request.user, **kwargs)
    try:
        return save_photo(upload, user=request.user, **kwargs)
    except ValidationError as exc:
        if "terlalu besar" in " ".join(exc.messages):
            raise
        raise ValidationError("Lampiran harus foto, PDF, atau DOCX.")


def documents_for(entity_type: str, entity_ids) -> dict[int, list[Attachment]]:
    """Dokumen (PDF/DOCX) per entitas, untuk ditampilkan sebagai tautan unduh."""
    out: dict[int, list[Attachment]] = {}
    ids = list(entity_ids)
    if not ids:
        return out
    for a in Attachment.objects.filter(entity_type=entity_type, entity_id__in=ids,
                                       mime_type__in=DOC_TYPES.values()).order_by("uploaded_at"):
        out.setdefault(a.entity_id, []).append(a)
    return out


def photos_for(entity_type: str, entity_ids) -> dict[int, list[Attachment]]:
    """Foto per entitas, untuk ditampilkan sebagai gambar kecil."""
    out: dict[int, list[Attachment]] = {}
    ids = list(entity_ids)
    if not ids:
        return out
    for a in Attachment.objects.filter(entity_type=entity_type, entity_id__in=ids,
                                       mime_type__startswith="image/").order_by("uploaded_at"):
        out.setdefault(a.entity_id, []).append(a)
    return out


# Sumber task (ActionItem.source_type) -> jenis entitas foto. Foto pada sumber ikut terlihat
# oleh penerima task tindak lanjutnya, supaya ia tahu apa yang harus dibereskan.
SOURCE_PHOTO_ENTITY = {
    "audit_direktur": "auditcheck",
    "checklistresponse": "checklistresponse",
    "permintaan_owner": "ownerrequest",
}


def _can_view_task(user, item) -> bool:
    from .permissions import can_access_clinic, is_aom, is_owner, is_supervisor

    if is_aom(user) or is_owner(user):
        return True
    if item.created_by_id == user.pk or item.owner_id == user.pk:
        return True
    if item.task_assignments.filter(assignee=user).exists():
        return True
    return is_supervisor(user) and can_access_clinic(user, item.clinic)


def _visible_through_task(user, entity_type: str, pk: int) -> bool:
    from .models import ActionItem

    sources = [s for s, e in SOURCE_PHOTO_ENTITY.items() if e == entity_type]
    items = ActionItem.objects.filter(source_type__in=sources, source_id=pk).select_related("clinic")
    return any(_can_view_task(user, item) for item in items)


def task_photos(items) -> dict[int, list[Attachment]]:
    """Foto untuk daftar task: foto sumber temuan + foto bukti dari penerima."""
    from .models import TaskAssignment

    items = list(items)
    out: dict[int, list[Attachment]] = {item.pk: [] for item in items}
    by_entity: dict[str, dict[int, list[int]]] = {}
    for item in items:
        entity = SOURCE_PHOTO_ENTITY.get(item.source_type)
        if entity and item.source_id:
            by_entity.setdefault(entity, {}).setdefault(item.source_id, []).append(item.pk)
    for entity, sources in by_entity.items():
        for source_id, photos in photos_for(entity, sources.keys()).items():
            for item_id in sources[source_id]:
                out[item_id].extend(photos)
    assignment_items = dict(
        TaskAssignment.objects.filter(action_item_id__in=out.keys()).values_list("pk", "action_item_id")
    )
    for assignment_id, photos in photos_for("taskassignment", assignment_items.keys()).items():
        out[assignment_items[assignment_id]].extend(photos)
    return out


def can_view_attachment(user, attachment: Attachment) -> bool:
    """Izin membuka lampiran mengikuti izin membuka entitas induknya."""
    from .permissions import is_aom, is_owner

    kind, pk = attachment.entity_type, attachment.entity_id
    if kind == "issue":
        from issues.models import Issue

        from .permissions import can_view_restricted_issue

        issue = Issue.objects.filter(pk=pk).first()
        return bool(issue and can_view_restricted_issue(user, issue))
    if kind == "checklistresponse":
        from checklists.models import ChecklistResponse

        from .permissions import can_access_checklist_run

        response = ChecklistResponse.objects.select_related("run__operational_day__clinic").filter(pk=pk).first()
        if response and can_access_checklist_run(user, response.run):
            return True
        return _visible_through_task(user, kind, pk)
    if kind == "taskassignment":
        from .models import TaskAssignment

        a = TaskAssignment.objects.select_related("action_item__clinic").filter(pk=pk).first()
        return bool(a and (a.assignee_id == user.pk or _can_view_task(user, a.action_item)))
    if kind == "taskevent":
        from .models import TaskEvent

        e = TaskEvent.objects.select_related("action_item__clinic").filter(pk=pk).first()
        return bool(e and (e.actor_id == user.pk or _can_view_task(user, e.action_item)))
    if kind in ("auditcheck", "ownerrequest"):
        return is_aom(user) or is_owner(user) or _visible_through_task(user, kind, pk)
    if kind == "ownerrequestnote":
        return is_aom(user) or is_owner(user)
    return is_aom(user)


def assert_can_view(user, attachment: Attachment) -> None:
    if not can_view_attachment(user, attachment):
        raise PermissionDenied("Anda tidak memiliki akses ke lampiran ini.")
