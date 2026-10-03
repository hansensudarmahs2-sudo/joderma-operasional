"""Foto lampiran (keputusan 3 Oktober 2026): dikompres, opsional, di empat tempat.

1. Butir checklist bermasalah.
2. Komplain / Masukan / Kerusakan.
3. Temuan Owner dan Direktur.
4. Bukti task selesai.

Foto disimpan di luar folder publik dan hanya terbuka lewat `core:attachment`, yang memeriksa
izin entitas induknya.
"""
from __future__ import annotations

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from accounts.models import Role, User, UserRole
from checklists.models import ChecklistArea, ChecklistRun, ResponseResult
from checklists.services import instantiate_runs_for_day
from core.models import ActionItem, Attachment, Clinic, TaskAssignmentStatus, TaskAudienceType
from core.photos import PHOTO_MAX_SIDE, can_view_attachment, compress_photo, task_photos
from core.services import get_or_create_day
from core.task_services import create_task
from issues.models import Issue

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _png(w=3000, h=2000, mode="RGBA", name="kamera.png"):
    buf = io.BytesIO()
    Image.new(mode, (w, h), (200, 30, 30, 255) if mode == "RGBA" else (200, 30, 30)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _jpeg_with_gps():
    img = Image.new("RGB", (2400, 1200), (10, 120, 200))
    exif = Image.Exif()
    exif[0x8825] = {2: (7.0, 15.0, 0.0)}  # GPSInfo
    exif[0x0112] = 6  # Orientation: putar 90°
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return SimpleUploadedFile("hp.jpg", buf.getvalue(), content_type="image/jpeg")


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def other_clinic(db):
    return Clinic.objects.create(code="JJ", name="Jemur Andayani")


@pytest.fixture
def director(clinic):
    return _user(clinic, "hansen1", Role.AOM)


# --- Kompresi -------------------------------------------------------------------


def test_compress_resizes_converts_and_strips_exif():
    data, w, h = compress_photo(_png())
    assert max(w, h) == PHOTO_MAX_SIDE
    img = Image.open(io.BytesIO(data))
    assert img.format == "JPEG" and img.mode == "RGB"
    data, w, h = compress_photo(_jpeg_with_gps())
    img = Image.open(io.BytesIO(data))
    assert (w, h) == (800, 1600)  # diputar sesuai EXIF
    assert not img.getexif().get(0x8825)  # lokasi GPS dibuang


def test_compress_rejects_non_image():
    with pytest.raises(ValidationError):
        compress_photo(SimpleUploadedFile("x.png", b"bukan gambar", content_type="image/png"))


# --- 2. Komplain / Masukan / Kerusakan ------------------------------------------------


def test_issue_with_photo_and_permissions(client, clinic, other_clinic, kasir, director):
    client.force_login(kasir)
    response = client.post(reverse("issues:create") + "?tipe=KERUSAKAN", {
        "issue_type": "KERUSAKAN", "title": "AC ruang 2 bocor", "severity": "SEDANG",
        "description": "Menetes ke lantai", "location": "Ruang 2", "impact": "TERBATAS", "foto": _png(),
    })
    assert response.status_code == 302, response.content.decode()[:500]
    issue = Issue.objects.get(title="AC ruang 2 bocor")
    photo = Attachment.objects.get(entity_type="issue", entity_id=issue.pk)
    assert photo.mime_type == "image/jpeg" and photo.size_bytes < 300_000
    body = client.get(reverse("issues:detail", args=[issue.pk])).content.decode()
    assert f'{reverse("core:attachment", args=[photo.pk])}?lihat=1' in body
    inline = client.get(reverse("core:attachment", args=[photo.pk]) + "?lihat=1")
    assert inline.status_code == 200 and inline["Content-Disposition"].startswith("inline")
    assert inline["X-Content-Type-Options"] == "nosniff"
    download = client.get(reverse("core:attachment", args=[photo.pk]))
    assert download["Content-Disposition"].startswith("attachment")
    stranger = _user(other_clinic, "yani", Role.PERAWAT, Role.STAF)
    client.force_login(stranger)
    assert client.get(reverse("core:attachment", args=[photo.pk]) + "?lihat=1").status_code == 403
    client.force_login(director)
    assert client.get(reverse("core:attachment", args=[photo.pk]) + "?lihat=1").status_code == 200


def test_invalid_photo_does_not_create_issue(client, clinic, kasir):
    client.force_login(kasir)
    response = client.post(reverse("issues:create"), {
        "issue_type": "KERUSAKAN", "title": "Lampu mati", "severity": "SEDANG", "location": "Lobi",
        "impact": "NORMAL",
        "foto": SimpleUploadedFile("x.png", b"rusak", content_type="image/png"),
    })
    assert response.status_code == 200
    assert not Issue.objects.filter(title="Lampu mati").exists()
    assert "Berkas bukan foto" in response.content.decode()


def test_issue_detail_upload_compresses_images(client, clinic, kasir):
    from issues.models import IssueType
    from issues.services import create_issue

    issue = create_issue(clinic=clinic, issue_type=IssueType.KERUSAKAN, title="Kursi patah", user=kasir)
    client.force_login(kasir)
    client.post(reverse("issues:upload", args=[issue.pk]), {"file": _png(4000, 3000)})
    photo = Attachment.objects.get(entity_type="issue", entity_id=issue.pk)
    assert photo.mime_type == "image/jpeg"


# --- 1. Butir checklist bermasalah ---------------------------------------------------


@pytest.fixture
def run(clinic, template, supervisor):
    day, _ = get_or_create_day(clinic, user=supervisor)
    instantiate_runs_for_day(day)
    return ChecklistRun.objects.get(operational_day=day, area=ChecklistArea.RUANG_KONSULTASI)


def test_checklist_problem_with_photo(client, run, perawat, other_clinic):
    response_obj = run.responses.get(label="Alat lengkap")
    client.force_login(perawat)
    page = client.get(reverse("checklists:run", args=[run.pk])).content.decode()
    assert "Ada masalah?" in page and 'enctype="multipart/form-data"' in page
    client.post(reverse("checklists:save_response", args=[response_obj.pk]), {
        "hasil": "RUSAK", "catatan": "Lampu periksa mati", "versi": response_obj.version, "foto": _png(),
    })
    response_obj.refresh_from_db()
    assert response_obj.result == ResponseResult.RUSAK
    photo = Attachment.objects.get(entity_type="checklistresponse", entity_id=response_obj.pk)
    page = client.get(reverse("checklists:run", args=[run.pk])).content.decode()
    assert f'{reverse("core:attachment", args=[photo.pk])}?lihat=1' in page
    assert can_view_attachment(perawat, photo)
    assert not can_view_attachment(_user(other_clinic, "luar", Role.PERAWAT), photo)
    # Laporan kerusakan dari butir ini membawa fotonya.
    client.post(reverse("checklists:make_damage", args=[response_obj.pk]))
    issue = Issue.objects.get()
    assert Attachment.objects.filter(entity_type="issue", entity_id=issue.pk, file=photo.file.name).exists()


def test_checklist_problem_requires_note_and_keeps_no_photo(client, run, perawat):
    response_obj = run.responses.get(label="Alat lengkap")
    client.force_login(perawat)
    client.post(reverse("checklists:save_response", args=[response_obj.pk]), {
        "hasil": "TIDAK_LENGKAP", "catatan": "", "versi": response_obj.version, "foto": _png(),
    })
    response_obj.refresh_from_db()
    assert response_obj.result == ResponseResult.BELUM
    assert not Attachment.objects.exists()


# --- 3. Temuan Direktur dan Owner -----------------------------------------------------


def test_director_finding_photo_visible_to_assignee(client, clinic, director, perawat, staf):
    from direktur.models import AuditCheck, AuditItem

    item = AuditItem.objects.create(code="uji-foto", cadence="HARIAN", number=1, title="Kebersihan toilet",
                                    description="Lantai, wastafel")
    client.force_login(director)
    client.post(reverse("direktur:record", args=[item.pk]), {
        "cabang": clinic.pk, "hasil": "TEMUAN", "catatan": "Wastafel berkerak",
        "penerima": f"user:{perawat.pk}", "foto": _png(),
    })
    check = AuditCheck.objects.get()
    assert check.finding_id
    photo = Attachment.objects.get(entity_type="auditcheck", entity_id=check.pk)
    page = client.get(reverse("direktur:checklist") + f"?cabang={clinic.pk}").content.decode()
    assert f'{reverse("core:attachment", args=[photo.pk])}?lihat=1' in page
    detail = client.get(reverse("direktur:task_detail", args=[check.finding_id])).content.decode()
    assert "Foto dari sumber temuan" in detail
    assert can_view_attachment(perawat, photo)
    assert not can_view_attachment(staf, photo)
    # Penerima melihat fotonya di Hari Ini.
    client.force_login(perawat)
    card = client.get(reverse("core:dashboard")).content.decode().split('id="tugas-saya"', 1)[1]
    assert f'{reverse("core:attachment", args=[photo.pk])}?lihat=1' in card.split("</section>", 1)[0]


def test_owner_request_and_note_photos(client, clinic, director, staf):
    from owner.models import OwnerRequest, OwnerRequestNote

    owner = _user(clinic, "yohanes", Role.OWNER)
    client.force_login(owner)
    response = client.post(reverse("owner:request_new"), {
        "judul": "Rapikan gudang", "rincian": "Kardus menumpuk", "target": "2099-01-01", "foto": _png(),
    })
    req = OwnerRequest.objects.get()
    assert response["Location"] == reverse("owner:request_detail", args=[req.pk])
    photo = Attachment.objects.get(entity_type="ownerrequest", entity_id=req.pk)
    client.post(reverse("owner:request_detail", args=[req.pk]), {"catatan": "Sudah dicek", "foto": _png()})
    note = OwnerRequestNote.objects.get()
    note_photo = Attachment.objects.get(entity_type="ownerrequestnote", entity_id=note.pk)
    body = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert str(photo.pk) in body and f"/lampiran/{note_photo.pk}/" in body
    assert client.get(reverse("core:attachment", args=[photo.pk]) + "?lihat=1").status_code == 200
    assert can_view_attachment(director, photo)
    assert not can_view_attachment(staf, photo)


# --- 4. Bukti task selesai -------------------------------------------------------------


def test_task_evidence_photo_from_hari_ini(client, clinic, director, perawat, staf):
    item = create_task(clinic=clinic, actor=director, title="Pengolahan limbah",
                       audience_type=TaskAudienceType.USER, user_ids=[perawat.pk])
    assignment = item.task_assignments.get()
    client.force_login(perawat)
    card = client.get(reverse("core:dashboard")).content.decode().split('id="tugas-saya"', 1)[1]
    assert "Foto bukti (opsional)" in card.split("</section>", 1)[0]
    client.post(reverse("core:assignment_submit", args=[assignment.pk]),
                {"next": reverse("core:dashboard"), "catatan": "2,4 kg", "foto": _png()})
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED
    photo = Attachment.objects.get(entity_type="taskassignment", entity_id=assignment.pk)
    assert task_photos([item])[item.pk] == [photo]
    client.force_login(director)
    detail = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert f'{reverse("core:attachment", args=[photo.pk])}?lihat=1' in detail
    assert can_view_attachment(perawat, photo) and can_view_attachment(director, photo)
    assert not can_view_attachment(staf, photo)


def test_bad_evidence_photo_keeps_task_open(client, clinic, director, perawat):
    item = create_task(clinic=clinic, actor=director, title="Cek autoklaf",
                       audience_type=TaskAudienceType.USER, user_ids=[perawat.pk])
    assignment = item.task_assignments.get()
    client.force_login(perawat)
    client.post(reverse("core:assignment_submit", args=[assignment.pk]),
                {"catatan": "sudah dicek", "foto": SimpleUploadedFile("x.jpg", b"xx", content_type="image/jpeg")})
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.OPEN
    assert not ActionItem.objects.filter(pk=item.pk, status="SELESAI").exists()


def test_unknown_entity_only_director(clinic, director, kasir):
    photo = Attachment.objects.create(entity_type="lain", entity_id=1, file=_png(10, 10), original_name="a.png",
                                      mime_type="image/png", size_bytes=10, uploaded_by=kasir)
    assert can_view_attachment(director, photo)
    assert not can_view_attachment(kasir, photo)
