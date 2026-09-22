"""Fase 4: masukan privat, publikasi AOM dengan snapshot, dan negative tests (plan 10)."""
from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Capability, Role, User, UserCapability, UserRole
from audit.models import AuditAction, AuditEvent
from reports.models import Masukan
from reports.services import (
    archive_masukan,
    create_masukan,
    publish_masukan,
    visible_masukan_queryset,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def aom_user(clinic):
    user = User.objects.create_user(username="aom_masukan", password="TestPassword123!")
    UserRole.objects.create(user=user, clinic=clinic, role=Role.AOM)
    return user


def test_any_active_user_can_create_masukan(clinic, staf):
    masukan = create_masukan(clinic=clinic, user=staf, title="Usul jam operasional")
    assert masukan.created_by == staf
    assert AuditEvent.objects.filter(
        entity_type="masukan", entity_id=str(masukan.pk), action=AuditAction.CREATE
    ).exists()


def test_blank_title_is_rejected(clinic, staf):
    with pytest.raises(ValidationError):
        create_masukan(clinic=clinic, user=staf, title="")


def test_initial_visibility_is_submitter_and_aom_only(clinic, staf, kasir, aom_user):
    create_masukan(clinic=clinic, user=staf, title="Usul privat")

    assert visible_masukan_queryset(staf, clinic).count() == 1
    assert visible_masukan_queryset(kasir, clinic).count() == 0
    assert visible_masukan_queryset(aom_user, clinic).count() == 1


def test_non_aom_cannot_publish_masukan(clinic, staf, clinic_b):
    masukan = create_masukan(clinic=clinic, user=staf, title="Usul privat")
    with pytest.raises(PermissionDenied):
        publish_masukan(masukan, user=staf, clinics=[clinic])


def test_aom_can_publish_masukan_records_who_when_where(clinic, clinic_b, staf, aom_user):
    masukan = create_masukan(clinic=clinic, user=staf, title="Usul jam operasional")

    publication = publish_masukan(masukan, user=aom_user, clinics=[clinic, clinic_b], note="disetujui")

    assert publication.published_by == aom_user
    assert publication.published_at is not None
    assert set(publication.clinics.all()) == {clinic, clinic_b}
    assert publication.source_version == masukan.version
    assert AuditEvent.objects.filter(
        entity_type="masukanpublication", entity_id=str(publication.pk), action=AuditAction.PUBLISH
    ).exists()


def test_publish_requires_at_least_one_clinic(clinic, staf, aom_user):
    masukan = create_masukan(clinic=clinic, user=staf, title="Usul jam operasional")
    with pytest.raises(ValidationError):
        publish_masukan(masukan, user=aom_user, clinics=[])


def test_publication_snapshot_is_immutable_after_edit(clinic, staf, aom_user):
    """Edit isi asli setelah publikasi tidak boleh mengubah snapshot yang sudah terbit."""
    masukan = create_masukan(clinic=clinic, user=staf, title="Judul awal", description="Isi awal")
    publication = publish_masukan(masukan, user=aom_user, clinics=[clinic])

    masukan.title = "Judul diedit setelah publikasi"
    masukan.description = "Isi diedit setelah publikasi"
    masukan.version += 1
    masukan.save()

    publication.refresh_from_db()
    assert publication.title_snapshot == "Judul awal"
    assert publication.description_snapshot == "Isi awal"
    assert publication.source_version == 1


def test_submitter_still_sees_own_feedback_after_publication(clinic, staf, aom_user):
    masukan = create_masukan(clinic=clinic, user=staf, title="Usul jam operasional")
    publish_masukan(masukan, user=aom_user, clinics=[clinic])

    masukan.refresh_from_db()
    assert masukan.is_published is True
    assert visible_masukan_queryset(staf, clinic).filter(pk=masukan.pk).exists()


def test_capability_grant_allows_publish_without_aom_role(clinic, staf, clinic_b):
    publisher = User.objects.create_user(username="publisher_cap", password="TestPassword123!")
    UserRole.objects.create(user=publisher, clinic=clinic, role=Role.SUPERVISOR)
    UserCapability.objects.create(user=publisher, capability=Capability.SUGGESTION_PUBLISH)
    UserCapability.objects.create(user=publisher, capability=Capability.REPORT_VIEW_CONFIDENTIAL)

    masukan = create_masukan(clinic=clinic, user=staf, title="Usul jam operasional")
    publication = publish_masukan(masukan, user=publisher, clinics=[clinic])
    assert publication.published_by == publisher


def test_capability_publisher_cannot_target_another_branch(clinic, staf, clinic_b):
    publisher = User.objects.create_user(username="publisher_scoped", password="TestPassword123!")
    UserRole.objects.create(user=publisher, clinic=clinic, role=Role.SUPERVISOR)
    UserCapability.objects.create(user=publisher, capability=Capability.SUGGESTION_PUBLISH)
    UserCapability.objects.create(user=publisher, capability=Capability.REPORT_VIEW_CONFIDENTIAL)

    masukan = create_masukan(clinic=clinic, user=staf, title="Usul scoped")
    with pytest.raises(PermissionDenied):
        publish_masukan(masukan, user=publisher, clinics=[clinic_b])


def test_publication_rejects_inactive_target(clinic, staf, aom_user):
    inactive = type(clinic).objects.create(
        code="inactive-target", name="Inactive", open_time="12:00", close_time="21:00", active=False
    )
    masukan = create_masukan(clinic=clinic, user=staf, title="Usul aktif")
    with pytest.raises(ValidationError):
        publish_masukan(masukan, user=aom_user, clinics=[inactive])


def test_archive_requires_reason_and_capability(clinic, staf, aom_user):
    masukan = create_masukan(clinic=clinic, user=staf, title="Usul jam operasional")

    with pytest.raises(PermissionDenied):
        archive_masukan(masukan, user=staf, reason="tidak relevan")

    with pytest.raises(ValidationError):
        archive_masukan(masukan, user=aom_user, reason="")

    archive_masukan(masukan, user=aom_user, reason="Sudah diterapkan di kebijakan lain.")
    masukan.refresh_from_db()
    assert masukan.archived_at is not None
    assert Masukan.objects.filter(pk=masukan.pk).exists()  # tidak dihapus
    assert AuditEvent.objects.filter(
        entity_type="masukan", entity_id=str(masukan.pk), action=AuditAction.ARCHIVE
    ).exists()


# --- Negative tests via HTTP (leak prevention, plan 15/16) -----------------


def test_masukan_detail_blocked_for_other_staf_same_clinic(client, clinic, staf):
    other = User.objects.create_user(username="masukan_other_staf", password="TestPassword123!")
    UserRole.objects.create(user=other, clinic=clinic, role=Role.STAF)

    masukan = create_masukan(clinic=clinic, user=staf, title="Usul privat")

    client.login(username="masukan_other_staf", password="TestPassword123!")
    response = client.get(reverse("reports:masukan_detail", args=[masukan.pk]))
    assert response.status_code == 403


def test_masukan_not_in_list_for_other_staf_same_clinic(client, clinic, staf):
    other = User.objects.create_user(username="masukan_other_staf2", password="TestPassword123!")
    UserRole.objects.create(user=other, clinic=clinic, role=Role.STAF)

    create_masukan(clinic=clinic, user=staf, title="Usul privat")

    client.login(username="masukan_other_staf2", password="TestPassword123!")
    response = client.get(reverse("reports:masukan_list"))
    assert response.json()["results"] == []


def test_masukan_publish_endpoint_rejects_non_aom(client, clinic, staf):
    masukan = create_masukan(clinic=clinic, user=staf, title="Usul privat")

    client.login(username="staf", password="TestPassword123!")
    response = client.post(
        reverse("reports:masukan_publish", args=[masukan.pk]), {"clinics": [clinic.pk]}
    )
    assert response.status_code == 403
