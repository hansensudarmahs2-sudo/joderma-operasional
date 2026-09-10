"""Test konkurensi, privasi tampilan, dan lampiran (PRD 21, 15.2)."""
import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from cash.models import CashSessionType
from cash.services import get_or_create_session, save_count
from checklists.models import ChecklistResponse, ResponseResult
from checklists.services import record_response
from core.models import Attachment
from issues.models import IssueType
from issues.services import create_issue
from queueing.models import VisitType
from queueing.services import create_entry

pytestmark = pytest.mark.django_db


def test_concurrent_checklist_edit_rejects_stale_version(day, kasir, perawat):
    """Dua petugas mengubah item yang sama; yang kedua ditolak (optimistic locking)."""
    r1 = ChecklistResponse.objects.get(run__operational_day=day, label="Alat lengkap")
    r2 = ChecklistResponse.objects.get(pk=r1.pk)  # salinan versi lama, seperti tab kedua

    record_response(r1, user=kasir, result=ResponseResult.OK, expected_version=r1.version)
    with pytest.raises(ValidationError):
        record_response(
            r2, user=perawat, result=ResponseResult.RUSAK, note="rusak", expected_version=r2.version
        )


def test_concurrent_cash_edit_rejects_stale_version(day, kasir, kasir2):
    s1 = get_or_create_session(day, CashSessionType.OPENING, user=kasir)
    s2 = type(s1).objects.get(pk=s1.pk)

    save_count(s1, user=kasir, quantities={100000: 1}, expected_total=100000, expected_version=s1.version)
    with pytest.raises(ValidationError):
        save_count(
            s2, user=kasir2, quantities={100000: 9}, expected_total=100000,
            note="beda", expected_version=s2.version,
        )


def test_concurrent_queue_status_change_rejects_stale(day, kasir, kasir2):
    from queueing.services import change_queue_status
    from queueing.models import QueueStatus

    e1 = create_entry(day, user=kasir, display_name="Pasien", visit_type=VisitType.KONSULTASI)
    e2 = type(e1).objects.get(pk=e1.pk)

    change_queue_status(e1, user=kasir, to_status=QueueStatus.CHECK_IN, expected_version=e1.version)
    with pytest.raises(ValidationError):
        change_queue_status(
            e2, user=kasir2, to_status=QueueStatus.CHECK_IN, expected_version=e2.version
        )


def test_public_board_hides_identity_and_payment(client, clinic, day, kasir, staf):
    create_entry(day, user=kasir, display_name="Budi Santoso", visit_type=VisitType.KONSULTASI)
    client.login(username="staf", password="TestPassword123!")
    body = client.get(reverse("queueing:public_board")).content.decode()
    assert "Budi Santoso" not in body
    assert "B*** S." in body
    assert "Sudah bayar" not in body


def test_work_board_hides_payment_from_general_staff(client, clinic, day, kasir, staf):
    create_entry(day, user=kasir, display_name="Budi Santoso", visit_type=VisitType.KONSULTASI)
    client.login(username="staf", password="TestPassword123!")
    body = client.get(reverse("queueing:board")).content.decode()
    assert "Budi Santoso" not in body
    assert "Belum bayar" not in body


def test_patient_detail_blocked_for_general_staff(client, clinic, day, kasir, staf):
    entry = create_entry(day, user=kasir, display_name="Budi", visit_type=VisitType.KONSULTASI)
    client.login(username="staf", password="TestPassword123!")
    assert client.get(reverse("queueing:detail", args=[entry.pk])).status_code == 403


def test_restricted_issue_detail_blocked(client, clinic, kasir, staf):
    issue = create_issue(
        clinic=clinic,
        issue_type=IssueType.KOMPLAIN,
        title="Komplain sensitif",
        user=kasir,
        is_restricted=True,
        reporter_source="PASIEN",
    )
    client.login(username="staf", password="TestPassword123!")
    assert client.get(reverse("issues:detail", args=[issue.pk])).status_code == 403


def test_attachment_requires_authentication(client, clinic, kasir):
    issue = create_issue(
        clinic=clinic, issue_type=IssueType.KERUSAKAN, title="AC rusak", user=kasir
    )
    from django.core.files.uploadedfile import SimpleUploadedFile

    attachment = Attachment.objects.create(
        entity_type="issue",
        entity_id=issue.pk,
        file=SimpleUploadedFile("bukti.png", b"fakepng", content_type="image/png"),
        original_name="bukti.png",
        mime_type="image/png",
        size_bytes=7,
        uploaded_by=kasir,
    )
    response = client.get(reverse("core:attachment", args=[attachment.pk]))
    assert response.status_code == 302 and "/akun/login" in response["Location"]


def test_attachment_download_is_audited(client, clinic, kasir):
    from audit.models import AuditAction, AuditEvent
    from django.core.files.uploadedfile import SimpleUploadedFile

    issue = create_issue(
        clinic=clinic, issue_type=IssueType.KERUSAKAN, title="AC rusak", user=kasir
    )
    attachment = Attachment.objects.create(
        entity_type="issue",
        entity_id=issue.pk,
        file=SimpleUploadedFile("bukti.png", b"fakepng", content_type="image/png"),
        original_name="bukti.png",
        mime_type="image/png",
        size_bytes=7,
        uploaded_by=kasir,
    )
    client.login(username="kasir", password="TestPassword123!")
    assert client.get(reverse("core:attachment", args=[attachment.pk])).status_code == 200
    assert AuditEvent.objects.filter(action=AuditAction.DOWNLOAD_ATTACHMENT).exists()


def test_attachment_storage_key_is_randomised(clinic, kasir):
    from django.core.files.uploadedfile import SimpleUploadedFile

    issue = create_issue(clinic=clinic, issue_type=IssueType.KERUSAKAN, title="X", user=kasir)
    attachment = Attachment.objects.create(
        entity_type="issue",
        entity_id=issue.pk,
        file=SimpleUploadedFile("rahasia-pasien.png", b"fakepng", content_type="image/png"),
        original_name="rahasia-pasien.png",
        mime_type="image/png",
        size_bytes=7,
        uploaded_by=kasir,
    )
    assert "rahasia-pasien" not in attachment.file.name
    assert attachment.original_name == "rahasia-pasien.png"


def test_health_endpoint_has_no_sensitive_data(client):
    response = client.get(reverse("health"))
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"status", "time"}
