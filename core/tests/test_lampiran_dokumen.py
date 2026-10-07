"""Lampiran dokumen (PDF, DOCX) pada Lapor progres dan Ajukan selesai (7 Okt 2026)."""
from __future__ import annotations

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core import photos
from core import task_services as ts
from core.models import Attachment, Clinic, TaskAssignmentStatus, TaskAudienceType, TaskEvent, TaskEventType

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _docx_bytes(with_document=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        if with_document:
            z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.STAF, display_name="Desy")


@pytest.fixture
def budi(db):
    other = Clinic.objects.create(code="klinik-lain", name="Klinik Lain", open_time="08:00", close_time="16:00")
    return _user(other, "budi", Role.STAF, display_name="Budi")


@pytest.fixture
def rekan(jemur):
    return _user(jemur, "rekan", Role.STAF, display_name="Rekan")


@pytest.fixture
def setup(jemur, hansen, desy):
    item = ts.create_task(clinic=jemur, actor=hansen, title="Rapikan arsip", audience_type=TaskAudienceType.USER,
                          user_ids=[desy.pk])
    return item, item.task_assignments.get()


def _login(client, user):
    client.login(username=user.username, password="TestPassword123!")


def _msgs(response):
    return [str(m) for m in response.context["messages"]] if response.context else []


def test_progress_with_pdf(client, desy, setup):
    item, a = setup
    _login(client, desy)
    f = SimpleUploadedFile("Laporan Mingguan.pdf", PDF, content_type="application/pdf")
    client.post(reverse("core:assignment_progress", args=[a.pk]), {"catatan": "Draft siap", "foto": f})
    event = TaskEvent.objects.get(action_item=item, event_type=TaskEventType.PROGRESS)
    att = Attachment.objects.get(entity_type="taskevent", entity_id=event.pk)
    assert att.mime_type == "application/pdf" and att.original_name == "Laporan Mingguan.pdf"
    assert att.file.read() == PDF


def test_submit_with_docx(client, desy, setup):
    item, a = setup
    _login(client, desy)
    f = SimpleUploadedFile("bukti.DOCX", _docx_bytes(), content_type="application/octet-stream")
    client.post(reverse("core:assignment_submit", args=[a.pk]), {"catatan": "Selesai", "foto": f})
    a.refresh_from_db()
    assert a.status != TaskAssignmentStatus.OPEN
    att = Attachment.objects.get(entity_type="taskassignment", entity_id=a.pk)
    assert att.mime_type == DOCX_MIME and att.original_name == "bukti.DOCX"


def test_fake_pdf_rejected_atomically(client, desy, setup):
    item, a = setup
    _login(client, desy)
    f = SimpleUploadedFile("palsu.pdf", b"hanya teks", content_type="application/pdf")
    r = client.post(reverse("core:assignment_progress", args=[a.pk]), {"catatan": "Draft", "foto": f}, follow=True)
    assert "Berkas bukan PDF atau DOCX yang sah." in _msgs(r)
    assert not Attachment.objects.exists()
    assert not TaskEvent.objects.filter(action_item=item, event_type=TaskEventType.PROGRESS).exists()


def test_docx_without_document_xml_rejected(client, desy, setup):
    item, a = setup
    _login(client, desy)
    f = SimpleUploadedFile("x.docx", _docx_bytes(with_document=False))
    r = client.post(reverse("core:assignment_submit", args=[a.pk]), {"catatan": "Selesai", "foto": f}, follow=True)
    assert "Berkas bukan PDF atau DOCX yang sah." in _msgs(r)
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.OPEN and not Attachment.objects.exists()


def test_exe_rejected(client, desy, setup):
    item, a = setup
    _login(client, desy)
    f = SimpleUploadedFile("virus.exe", b"MZ\x90\x00")
    r = client.post(reverse("core:assignment_progress", args=[a.pk]), {"catatan": "Draft", "foto": f}, follow=True)
    assert "Lampiran harus foto, PDF, atau DOCX." in _msgs(r)
    assert not Attachment.objects.exists()


def test_big_pdf_rejected(client, desy, setup, monkeypatch):
    item, a = setup
    monkeypatch.setattr(photos, "DOC_MAX_UPLOAD", 20)
    _login(client, desy)
    f = SimpleUploadedFile("besar.pdf", PDF + b"x" * 50)
    r = client.post(reverse("core:assignment_progress", args=[a.pk]), {"catatan": "Draft", "foto": f}, follow=True)
    assert "Dokumen terlalu besar (maks. 10 MB)." in _msgs(r)
    assert not Attachment.objects.exists()


def test_photo_still_compressed_to_jpeg(client, desy, setup):
    from PIL import Image

    item, a = setup
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, format="PNG")
    _login(client, desy)
    f = SimpleUploadedFile("foto.png", buf.getvalue(), content_type="image/png")
    client.post(reverse("core:assignment_progress", args=[a.pk]), {"catatan": "Foto", "foto": f})
    att = Attachment.objects.get()
    assert att.mime_type == "image/jpeg" and att.original_name == "foto.jpg"


def test_documents_visible_and_downloadable(client, desy, hansen, budi, rekan, setup):
    item, a = setup
    _login(client, desy)
    client.post(reverse("core:assignment_progress", args=[a.pk]),
                {"catatan": "Draft", "foto": SimpleUploadedFile("progres.pdf", PDF)})
    client.post(reverse("core:assignment_submit", args=[a.pk]),
                {"catatan": "Selesai", "foto": SimpleUploadedFile("bukti.docx", _docx_bytes())})
    # kartu staf: Percakapan menampilkan dokumen progres; bukti tampil di kartu bila masih tampil
    r = client.get(reverse("core:today"))
    assert "progres.pdf" in r.content.decode()
    # unduhan oleh penerima
    att = Attachment.objects.get(original_name="progres.pdf")
    r = client.get(reverse("core:attachment", args=[att.pk]))
    assert r.status_code == 200 and "attachment" in r["Content-Disposition"]
    # Direktur
    client.logout()
    _login(client, hansen)
    html = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "progres.pdf" in html and "bukti.docx" in html
    # staf lain yang tidak terkait
    client.logout()
    _login(client, budi)
    assert client.get(reverse("core:attachment", args=[att.pk])).status_code == 403
    # staf sekabang yang bukan penerima maupun pembuat
    client.logout()
    _login(client, rekan)
    assert client.get(reverse("core:attachment", args=[att.pk])).status_code == 403


def test_control_chars_stripped_from_name(client, desy, setup):
    item, a = setup
    _login(client, desy)
    f = SimpleUploadedFile("a\nb.pdf", PDF)
    client.post(reverse("core:assignment_progress", args=[a.pk]), {"catatan": "Draft", "foto": f})
    att = Attachment.objects.get()
    assert "\n" not in att.original_name and att.original_name.endswith(".pdf")
    r = client.get(reverse("core:attachment", args=[att.pk]))
    assert r.status_code == 200
