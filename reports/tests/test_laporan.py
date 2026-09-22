"""Fase 4: pembuatan laporan CABANG/RAHASIA_AOM, status, dan queryset (plan 9)."""
from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from accounts.models import Capability, Role, UserCapability, UserRole
from audit.models import AuditAction, AuditEvent
from reports.models import Laporan, ReportStatus, ReportVisibility
from reports.services import (
    archive_laporan,
    change_laporan_status,
    create_laporan,
    visible_laporan_queryset,
)

pytestmark = pytest.mark.django_db


def test_staf_can_create_cabang_report(clinic, staf):
    laporan = create_laporan(clinic=clinic, user=staf, title="Lantai licin", visibility=ReportVisibility.CABANG)

    assert laporan.status == ReportStatus.OPEN
    assert laporan.created_by == staf
    assert AuditEvent.objects.filter(entity_type="laporan", entity_id=str(laporan.pk), action=AuditAction.CREATE).exists()


def test_staf_can_create_confidential_report(clinic, staf):
    laporan = create_laporan(
        clinic=clinic, user=staf, title="Keluhan sensitif", visibility=ReportVisibility.RAHASIA_AOM
    )
    assert laporan.visibility == ReportVisibility.RAHASIA_AOM


def test_blank_title_is_rejected(clinic, staf):
    with pytest.raises(ValidationError):
        create_laporan(clinic=clinic, user=staf, title="   ")


def test_unknown_visibility_is_rejected(clinic, staf):
    with pytest.raises(ValidationError):
        create_laporan(clinic=clinic, user=staf, title="x", visibility="RAHASIA_LAIN")


def test_cannot_create_report_outside_own_clinic(clinic_b, staf):
    with pytest.raises(PermissionDenied):
        create_laporan(clinic=clinic_b, user=staf, title="Lintas cabang")


def test_status_transition_open_to_under_review(clinic, staf, supervisor):
    laporan = create_laporan(clinic=clinic, user=staf, title="Isu operasional")
    change_laporan_status(laporan, user=supervisor, to_status=ReportStatus.UNDER_REVIEW, note="ditinjau")
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.UNDER_REVIEW
    assert laporan.updates.filter(status=ReportStatus.UNDER_REVIEW).exists()


def test_illegal_status_transition_is_rejected(clinic, staf):
    laporan = create_laporan(clinic=clinic, user=staf, title="Isu operasional")
    with pytest.raises(ValidationError):
        change_laporan_status(laporan, user=staf, to_status=ReportStatus.ARCHIVED)


def test_closing_report_requires_reason(clinic, staf):
    laporan = create_laporan(clinic=clinic, user=staf, title="Isu operasional")
    with pytest.raises(ValidationError):
        change_laporan_status(laporan, user=staf, to_status=ReportStatus.CLOSED)


def test_closing_does_not_delete_report(clinic, staf):
    laporan = create_laporan(clinic=clinic, user=staf, title="Isu operasional")
    change_laporan_status(laporan, user=staf, to_status=ReportStatus.CLOSED, reason="selesai ditangani")
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.CLOSED
    assert Laporan.objects.filter(pk=laporan.pk).exists()


def test_archive_requires_capability(clinic, staf):
    laporan = create_laporan(clinic=clinic, user=staf, title="Isu operasional")
    with pytest.raises(PermissionDenied):
        archive_laporan(laporan, user=staf, reason="tidak relevan lagi")


def test_archive_requires_reason(clinic, staf):
    aom = UserRole.objects.create
    from accounts.models import User

    aom_user = User.objects.create_user(username="aom1", password="TestPassword123!")
    UserRole.objects.create(user=aom_user, clinic=clinic, role=Role.AOM)

    laporan = create_laporan(clinic=clinic, user=staf, title="Isu operasional")
    with pytest.raises(ValidationError):
        archive_laporan(laporan, user=aom_user, reason="   ")


def test_archive_with_reason_by_aom_creates_audit_event_and_keeps_data(clinic, staf):
    from accounts.models import User

    aom_user = User.objects.create_user(username="aom2", password="TestPassword123!")
    UserRole.objects.create(user=aom_user, clinic=clinic, role=Role.AOM)

    laporan = create_laporan(clinic=clinic, user=staf, title="Isu operasional")
    archive_laporan(laporan, user=aom_user, reason="Duplikat laporan lain.")
    laporan.refresh_from_db()

    assert laporan.status == ReportStatus.ARCHIVED
    assert laporan.archived_by == aom_user
    assert laporan.archive_reason == "Duplikat laporan lain."
    assert AuditEvent.objects.filter(
        entity_type="laporan", entity_id=str(laporan.pk), action=AuditAction.ARCHIVE
    ).exists()


def test_double_archive_is_rejected(clinic, staf):
    from accounts.models import User

    aom_user = User.objects.create_user(username="aom3", password="TestPassword123!")
    UserRole.objects.create(user=aom_user, clinic=clinic, role=Role.AOM)

    laporan = create_laporan(clinic=clinic, user=staf, title="Isu operasional")
    archive_laporan(laporan, user=aom_user, reason="Alasan pertama.")
    laporan.refresh_from_db()
    with pytest.raises(ValidationError):
        archive_laporan(laporan, user=aom_user, reason="Alasan kedua.")


# --- Visibility queryset (gate paling kritis: plan 15/16) ------------------


def test_cabang_report_visible_to_active_clinic_users(clinic, staf, kasir):
    create_laporan(clinic=clinic, user=staf, title="Umum satu cabang", visibility=ReportVisibility.CABANG)

    qs = visible_laporan_queryset(kasir, clinic)
    assert qs.count() == 1


def test_confidential_report_not_visible_via_list_to_other_clinic_user(clinic, staf, kasir):
    create_laporan(clinic=clinic, user=staf, title="Rahasia", visibility=ReportVisibility.RAHASIA_AOM)

    qs = visible_laporan_queryset(kasir, clinic)
    assert qs.count() == 0


def test_confidential_report_visible_to_own_creator(clinic, staf):
    laporan = create_laporan(clinic=clinic, user=staf, title="Rahasia", visibility=ReportVisibility.RAHASIA_AOM)

    qs = visible_laporan_queryset(staf, clinic)
    assert list(qs) == [laporan]


def test_confidential_report_visible_to_aom(clinic, staf):
    from accounts.models import User

    aom_user = User.objects.create_user(username="aom4", password="TestPassword123!")
    UserRole.objects.create(user=aom_user, clinic=clinic, role=Role.AOM)

    create_laporan(clinic=clinic, user=staf, title="Rahasia", visibility=ReportVisibility.RAHASIA_AOM)

    qs = visible_laporan_queryset(aom_user, clinic)
    assert qs.count() == 1


def test_confidential_report_visible_with_explicit_capability(clinic, staf, admin_teknis):
    create_laporan(clinic=clinic, user=staf, title="Rahasia", visibility=ReportVisibility.RAHASIA_AOM)

    from accounts.models import User

    # Admin teknis TANPA capability -> tidak terlihat. Query pengguna baru agar
    # cache capability_codes() tidak ikut membawa hasil sebelum grant (PRD 6.3).
    fresh_before = User.objects.get(pk=admin_teknis.pk)
    assert visible_laporan_queryset(fresh_before, clinic).count() == 0

    UserCapability.objects.create(user=admin_teknis, capability=Capability.REPORT_VIEW_CONFIDENTIAL)
    fresh_after = User.objects.get(pk=admin_teknis.pk)
    assert visible_laporan_queryset(fresh_after, clinic).count() == 1


def test_cross_clinic_user_sees_nothing_even_for_cabang_visibility(clinic, clinic_b, staf):
    create_laporan(clinic=clinic, user=staf, title="Umum cabang A", visibility=ReportVisibility.CABANG)

    from accounts.models import User

    other = User.objects.create_user(username="other_b", password="TestPassword123!")
    UserRole.objects.create(user=other, clinic=clinic_b, role=Role.STAF)

    assert visible_laporan_queryset(other, clinic).count() == 0
