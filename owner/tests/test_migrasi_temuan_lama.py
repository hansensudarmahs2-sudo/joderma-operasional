"""Migrasi data owner 0004: temuan dan sub task Direktur dari sebelum fitur sub task (6 Okt 2026)."""
from __future__ import annotations

import datetime as dt
import importlib

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import ActionItem, ActionItemStatus, Clinic, TaskAssignment, TaskAssignmentStatus, local_today
from owner import services
from owner.models import OwnerRequest, RequestKind

pytestmark = pytest.mark.django_db
migrasi = importlib.import_module("owner.migrations.0004_tutup_temuan_lama")


def _jalankan():
    migrasi.tutup_data_lama(django_apps, None)


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.PIC, Role.FRONT_DESK, display_name="Desy")


def _temuan(owner, title="Temuan lama"):
    return services.create_request(actor=owner, kind=RequestKind.TEMUAN, title=title)


def _task(req, clinic, creator, status=ActionItemStatus.SELESAI, title="Task", when=None):
    item = ActionItem.objects.create(clinic=clinic, title=title, source_type="permintaan_owner", source_id=req.pk,
                                     status=status, created_by=creator)
    if when is not None:
        ActionItem.objects.filter(pk=item.pk).update(updated_at=when)
    return item


def test_old_finished_finding_is_closed_with_last_task_time(jemur, yohanes, hansen):
    req = _temuan(yohanes)
    earlier = timezone.now() - dt.timedelta(days=5)
    last = timezone.now() - dt.timedelta(days=2)
    _task(req, jemur, hansen, title="Pertama", when=earlier)
    _task(req, jemur, hansen, title="Terakhir", when=last)
    _task(req, jemur, hansen, status=ActionItemStatus.BATAL, title="Dibatalkan")
    _jalankan()
    req.refresh_from_db()
    assert req.completed_at == last and req.completed_by == hansen
    assert services.progress(req)["label"] == "Selesai & terverifikasi"
    event = AuditEvent.objects.get(entity_type="ownerrequest", entity_id=str(req.pk), action="CLOSE")
    assert "migrasi 0004" in event.reason and event.actor is None


def test_closer_left_empty_when_last_task_creator_is_not_director(jemur, yohanes, desy):
    req = _temuan(yohanes)
    _task(req, jemur, desy)
    _jalankan()
    req.refresh_from_db()
    assert req.completed_at is not None and req.completed_by is None


def test_open_unsplit_and_requests_are_untouched(jemur, yohanes, hansen):
    running = _temuan(yohanes, "Masih berjalan")
    _task(running, jemur, hansen)
    _task(running, jemur, hansen, status=ActionItemStatus.DIKERJAKAN)
    unsplit = _temuan(yohanes, "Belum dipecah")
    only_cancelled = _temuan(yohanes, "Hanya batal")
    _task(only_cancelled, jemur, hansen, status=ActionItemStatus.BATAL)
    request = services.create_request(actor=yohanes, title="Permintaan", target_date=local_today() + dt.timedelta(days=5))
    _task(request, jemur, hansen)
    _jalankan()
    assert not OwnerRequest.objects.filter(completed_at__isnull=False).exists()
    assert not AuditEvent.objects.filter(action="CLOSE").exists()
    assert unsplit.pk


def _stuck(req, clinic, director, person):
    """Assignment yang diajukan sebelum aturan baru: masih SUBMITTED menunggu Owner."""
    from direktur.services import create_task_from_source

    item = create_task_from_source(actor=director, clinic=clinic, title="Sub task lama", target=f"user:{person.pk}",
                                   source_type="permintaan_owner", source_id=req.pk)
    TaskAssignment.objects.filter(action_item=item).update(status=TaskAssignmentStatus.SUBMITTED,
                                                           submitted_at=timezone.now() - dt.timedelta(days=3))
    return item


def test_stuck_director_subtask_is_confirmed_and_finding_closed(jemur, yohanes, hansen):
    req = _temuan(yohanes)
    item = _stuck(req, jemur, hansen, hansen)
    _jalankan()
    a = item.task_assignments.get()
    item.refresh_from_db()
    req.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and a.reviewer is None and a.confirmed_at is not None
    assert item.task_events.filter(event_type="CONFIRMED", note__contains="migrasi 0004").exists()
    assert item.status == ActionItemStatus.SELESAI
    # Waktu selesai = saat Direktur mengajukan, bukan saat migrasi berjalan.
    assert req.completed_at == a.submitted_at and req.completed_by == hansen


def test_staff_and_non_finding_submissions_are_untouched(jemur, yohanes, hansen, desy):
    req = _temuan(yohanes)
    staff = _stuck(req, jemur, hansen, desy)
    request = services.create_request(actor=yohanes, title="Permintaan", target_date=local_today() + dt.timedelta(days=5))
    own_request_task = _stuck(request, jemur, hansen, hansen)
    _jalankan()
    for item in (staff, own_request_task):
        assert item.task_assignments.get().status == TaskAssignmentStatus.SUBMITTED
    req.refresh_from_db()
    assert req.completed_at is None


def test_running_twice_changes_nothing_more(jemur, yohanes, hansen):
    req = _temuan(yohanes)
    _task(req, jemur, hansen)
    _stuck(_temuan(yohanes, "Kedua"), jemur, hansen, hansen)
    _jalankan()
    counts = (AuditEvent.objects.count(), OwnerRequest.objects.filter(completed_at__isnull=False).count())
    stamp = OwnerRequest.objects.get(pk=req.pk).completed_at
    _jalankan()
    assert (AuditEvent.objects.count(), OwnerRequest.objects.filter(completed_at__isnull=False).count()) == counts
    assert OwnerRequest.objects.get(pk=req.pk).completed_at == stamp
