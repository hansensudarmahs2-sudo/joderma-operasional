"""Test issue: penomoran, workflow, SLA, penutupan, kerahasiaan (PRD 20.7)."""
import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from audit.models import AuditAction, AuditEvent
from core.models import Priority
from core.permissions import can_view_restricted_issue
from issues.models import Asset, Issue, IssueStatus, IssueType
from issues.services import (
    add_update,
    assign_issue,
    change_status,
    create_issue,
    issue_counters,
    mark_asset_do_not_use,
    record_repair,
)
from notifications.models import Notification

pytestmark = pytest.mark.django_db


def _complaint(clinic, user, **kw):
    return create_issue(
        clinic=clinic,
        issue_type=IssueType.KOMPLAIN,
        title=kw.pop("title", "Waktu tunggu terlalu lama"),
        user=user,
        description="Pasien menunggu lebih dari satu jam.",
        reporter_source="PASIEN",
        **kw,
    )


def test_number_format_and_uniqueness(clinic, kasir):
    a = _complaint(clinic, kasir)
    b = _complaint(clinic, kasir, title="Ruang tunggu panas")
    today = timezone.localtime(timezone.now()).strftime("%Y%m%d")
    assert a.number == f"CMP-{today}-001"
    assert b.number == f"CMP-{today}-002"

    damage = create_issue(
        clinic=clinic, issue_type=IssueType.KERUSAKAN, title="AC bocor", user=kasir
    )
    assert damage.number.startswith(f"DMG-{today}-")


def test_title_required(clinic, kasir):
    with pytest.raises(ValidationError):
        create_issue(clinic=clinic, issue_type=IssueType.KOMPLAIN, title="   ", user=kasir)


def test_sla_targets_applied(clinic, kasir):
    critical = create_issue(
        clinic=clinic,
        issue_type=IssueType.KERUSAKAN,
        title="Kabel listrik terbuka",
        user=kasir,
        severity=Priority.KRITIS,
    )
    delta = critical.due_at - critical.created_at
    assert 7.5 < delta.total_seconds() / 3600 < 8.5


def test_critical_issue_notifies_supervisor(clinic, kasir, supervisor):
    create_issue(
        clinic=clinic,
        issue_type=IssueType.KERUSAKAN,
        title="Risiko keselamatan",
        user=kasir,
        severity=Priority.KRITIS,
    )
    assert Notification.objects.filter(user=supervisor, type_code="ISSUE_CRITICAL").exists()


def test_invalid_workflow_transition_blocked(clinic, kasir, supervisor):
    issue = _complaint(clinic, kasir)
    with pytest.raises(ValidationError):
        change_status(issue, user=supervisor, to_status=IssueStatus.DITUTUP)


def test_complaint_full_workflow_requires_resolution(clinic, kasir, supervisor):
    issue = _complaint(clinic, kasir)
    change_status(issue, user=supervisor, to_status=IssueStatus.DITINJAU)
    assign_issue(issue, supervisor=supervisor, assignee=kasir)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITUGASKAN
    assert Notification.objects.filter(user=kasir, type_code="ISSUE_ASSIGNED").exists()

    change_status(issue, user=kasir, to_status=IssueStatus.DALAM_PROSES)
    with pytest.raises(ValidationError) as exc:
        change_status(issue, user=kasir, to_status=IssueStatus.SELESAI)
    assert "ringkasan penyelesaian" in " ".join(exc.value.messages).lower()

    change_status(
        issue,
        user=kasir,
        to_status=IssueStatus.SELESAI,
        resolution_summary="Alur antrean diperbaiki dan pasien diberi penjelasan.",
    )
    change_status(issue, user=supervisor, to_status=IssueStatus.DITUTUP, reason="Selesai ditindaklanjuti")
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITUTUP and issue.closed_at is not None
    assert AuditEvent.objects.filter(entity_type="issue", action=AuditAction.CLOSE).exists()


def test_damage_workflow_with_verification(clinic, kasir, supervisor):
    issue = create_issue(
        clinic=clinic,
        issue_type=IssueType.KERUSAKAN,
        title="Printer front desk mati",
        user=kasir,
        severity=Priority.TINGGI,
        location="Front desk",
    )
    change_status(issue, user=supervisor, to_status=IssueStatus.DITRIASE)
    assign_issue(issue, supervisor=supervisor, assignee=kasir)
    change_status(issue, user=kasir, to_status=IssueStatus.DALAM_PERBAIKAN)
    record_repair(issue, user=kasir, repair_action="Ganti kabel daya")
    change_status(issue, user=kasir, to_status=IssueStatus.SELESAI)
    change_status(issue, user=supervisor, to_status=IssueStatus.DIVERIFIKASI)
    issue.refresh_from_db()
    assert issue.verified_by == supervisor and issue.verified_at is not None
    assert issue.repair_action == "Ganti kabel daya"


def test_suggestion_rejection_requires_reason(clinic, staf, supervisor):
    idea = create_issue(
        clinic=clinic, issue_type=IssueType.MASUKAN, title="Tambah dispenser air", user=staf
    )
    assert idea.number.startswith("SUG-")
    with pytest.raises(ValidationError):
        change_status(idea, user=supervisor, to_status=IssueStatus.DITOLAK, reason="", note="")
    change_status(idea, user=supervisor, to_status=IssueStatus.DITOLAK, reason="Anggaran belum tersedia")
    idea.refresh_from_db()
    assert idea.closed_reason


def test_restricted_issue_visibility(clinic, kasir, staf, supervisor, perawat):
    issue = _complaint(clinic, kasir, is_restricted=True)
    assert can_view_restricted_issue(kasir, issue) is True       # pembuat
    assert can_view_restricted_issue(supervisor, issue) is True  # supervisor
    assert can_view_restricted_issue(staf, issue) is False       # di luar cakupan

    assign_issue(issue, supervisor=supervisor, assignee=perawat)
    assert can_view_restricted_issue(perawat, issue) is True     # assignee


def test_asset_do_not_use_requires_reason(clinic, supervisor):
    asset = Asset.objects.create(clinic=clinic, code="AST-9", name="Laser")
    with pytest.raises(ValidationError):
        mark_asset_do_not_use(asset, supervisor=supervisor, reason="")
    mark_asset_do_not_use(asset, supervisor=supervisor, reason="Menunggu kalibrasi vendor")
    asset.refresh_from_db()
    assert asset.do_not_use is True


def test_timeline_note_cannot_be_empty(clinic, kasir):
    issue = _complaint(clinic, kasir)
    with pytest.raises(ValidationError):
        add_update(issue, user=kasir, note="  ")
    add_update(issue, user=kasir, note="Sudah dihubungi pasien")
    assert issue.updates.count() == 2


def test_create_form_preselects_type_from_menu(client, clinic, kasir):
    """Dari menu Masukan, tipe harus terpilih otomatis — bukan kosong."""
    from django.urls import reverse

    client.login(username="kasir", password="TestPassword123!")
    body = client.get(reverse("issues:create") + "?tipe=MASUKAN").content.decode()
    assert 'value="MASUKAN" selected' in body
    assert "Masukan/saran" in body


def test_create_form_shows_contextual_heading(client, clinic, kasir):
    from django.urls import reverse

    client.login(username="kasir", password="TestPassword123!")
    for tipe, judul in [
        ("KOMPLAIN", "Komplain"),
        ("MASUKAN", "Masukan/saran"),
        ("KERUSAKAN", "Laporan kerusakan"),
    ]:
        body = client.get(reverse("issues:create") + f"?tipe={tipe}").content.decode()
        assert f"<h1>{judul}</h1>" in body


def test_list_page_has_contextual_create_button(client, clinic, kasir):
    """Tombol input harus jelas menyebut aksinya, bukan tersembunyi di antara filter."""
    from django.urls import reverse

    client.login(username="kasir", password="TestPassword123!")
    body = client.get(reverse("issues:list") + "?tipe=KERUSAKAN").content.decode()
    assert "Laporkan kerusakan" in body
    assert "tipe=KERUSAKAN" in body


def test_form_exposes_field_map_for_progressive_disclosure(client, clinic, kasir):
    """Field spesifik per tipe harus dikirim ke browser agar bisa disembunyikan."""
    from django.urls import reverse

    client.login(username="kasir", password="TestPassword123!")
    body = client.get(reverse("issues:create") + "?tipe=MASUKAN").content.decode()
    assert "benefit" in body
    assert "reporter_source" in body  # ada di DOM, disembunyikan oleh script
    assert 'data-field="location"' in body


def test_issue_counters(clinic, kasir):
    _complaint(clinic, kasir)
    create_issue(clinic=clinic, issue_type=IssueType.KERUSAKAN, title="AC rusak", user=kasir)
    counters = issue_counters(clinic)
    assert counters["komplain_open"] == 1 and counters["kerusakan_open"] == 1


def test_damage_detail_has_no_vendor_or_cost_fields(client, clinic, kasir, supervisor):
    """Keputusan 6 Okt 2026: pelaksana/vendor dan biaya perbaikan tidak dicatat."""
    from django.urls import reverse

    issue = create_issue(clinic=clinic, issue_type=IssueType.KERUSAKAN, title="AC ruang tunggu bocor", user=kasir)
    client.force_login(supervisor)
    resp = client.post(reverse("issues:repair", args=[issue.pk]), {"tindakan": "Ganti selang buangan", "vendor": "Toko AC", "biaya": "250000"})
    assert resp.status_code == 302
    issue.refresh_from_db()
    assert issue.repair_action == "Ganti selang buangan"
    assert not {"repair_vendor", "repair_cost"} & {f.name for f in Issue._meta.get_fields()}
    body = client.get(reverse("issues:detail", args=[issue.pk])).content.decode()
    assert 'name="vendor"' not in body and 'name="biaya"' not in body and "Biaya" not in body
