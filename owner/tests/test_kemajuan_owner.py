"""Owner diberi tahu kemajuan permintaan/temuannya: task dibuat, rencana temuan, permintaan selesai (7 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import ActionItem, Clinic, local_today
from direktur.services import create_task_from_source
from notifications.models import Notification
from owner import services
from owner.models import OwnerRequest, RequestKind

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, **extra)
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
def owner2(jemur):
    return _user(jemur, "owner2", Role.OWNER, display_name="dr. Dua")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.PIC, Role.FRONT_DESK, display_name="Desy")


def _request(owner, days=7, title="Rapikan display produk"):
    return services.create_request(actor=owner, title=title, target_date=local_today() + dt.timedelta(days=days))


def _temuan(owner, title="Alur pasien baru belum seragam"):
    return services.create_request(actor=owner, kind=RequestKind.TEMUAN, title=title)


def _task(req, hansen, jemur, person, title="Langkah 1", due=None, source="permintaan_owner", sid=None):
    return create_task_from_source(
        actor=hansen, clinic=jemur, title=title, target=f"user:{person.pk}", due_at=due,
        source_type=source, source_id=req.pk if sid is None else sid, source_label="x",
    )


def _notes(user, suffix, req):
    return Notification.objects.filter(user=user, entity_ref=f"permintaan_owner:{req.pk}:{suffix}")


def _finish(item, hansen, person):
    from core.task_services import confirm_assignment, submit_assignment

    a = item.task_assignments.get()
    submit_assignment(a, user=person, note="beres")
    confirm_assignment(a, reviewer=hansen)


# --- Pemicu 1: task dibuat -------------------------------------------------------


def test_first_task_notifies_every_owner(yohanes, owner2, hansen, desy, jemur):
    req = _request(yohanes)
    due = dt.datetime.combine(local_today() + dt.timedelta(days=5), dt.time(21, 0))
    from django.utils import timezone

    _task(req, hansen, jemur, desy, title="Foto display", due=timezone.make_aware(due))
    for o in (yohanes, owner2):
        n = _notes(o, "task", req).get()
        assert n.title == f"Mulai dikerjakan: {req.title}"
        assert "Foto display" in n.body and "Desy" in n.body
        assert f"target {local_today() + dt.timedelta(days=5):%d/%m/%Y}" in n.body
        assert n.url == reverse("owner:request_detail", args=[req.pk])
    assert not Notification.objects.filter(user=hansen, entity_ref__endswith=":task").exists()


def test_second_task_merges_into_one_notification(yohanes, hansen, desy, jemur):
    req = _request(yohanes)
    _task(req, hansen, jemur, desy, title="Langkah 1")
    _task(req, hansen, jemur, desy, title="Langkah 2")
    qs = _notes(yohanes, "task", req)
    assert qs.count() == 1
    assert qs.get().title == f"Task baru untuk: {req.title}"


def test_task_via_detail_view_notifies(client, yohanes, hansen, desy, jemur):
    req = _request(yohanes)
    client.force_login(hansen)
    client.post(reverse("owner:request_detail", args=[req.pk]), {
        "aksi": "task", "cabang": jemur.pk, "judul": "Langkah 1", "penerima": f"user:{desy.pk}",
        "prioritas": "SEDANG"})
    assert _notes(yohanes, "task", req).get().title.startswith("Mulai dikerjakan")


def test_inbox_triage_assign_notifies(yohanes, hansen, desy, jemur):
    from reports import triage
    from reports.inbox import find_row

    req = _request(yohanes)
    triage.assign(find_row(hansen, "permintaan_owner", req.pk), actor=hansen, clinic=jemur, title="Langkah 1",
                  target=f"user:{desy.pk}")
    assert _notes(yohanes, "task", req).get().title == f"Mulai dikerjakan: {req.title}"


def test_other_source_does_not_notify(yohanes, hansen, desy, jemur):
    req = _request(yohanes)
    _task(req, hansen, jemur, desy, source="manual", sid=999)
    assert not Notification.objects.filter(user=yohanes, entity_ref__startswith="permintaan_owner:").exclude(
        entity_ref=f"permintaan_owner:{req.pk}").exists()


def test_task_notification_does_not_overwrite_note_notification(yohanes, hansen, desy, jemur):
    req = _request(yohanes)
    services.add_note(req, actor=hansen, body="Sedang diatur")
    _task(req, hansen, jemur, desy)
    assert Notification.objects.get(user=yohanes, entity_ref=f"permintaan_owner:{req.pk}").title.startswith(
        "Catatan baru")
    assert _notes(yohanes, "task", req).count() == 1


# --- Pemicu 2: rencana temuan --------------------------------------------------


def test_set_plan_notifies_only_when_changed(yohanes, hansen):
    req = _temuan(yohanes)
    target = local_today() + dt.timedelta(days=5)
    services.set_plan(req, actor=hansen, plan_title="Seragamkan alur", target_date=target)
    n = _notes(yohanes, "rencana", req).get()
    assert n.title == f"Rencana temuan: {req.title}"
    assert "Task besar: Seragamkan alur" in n.body and f"{target:%d/%m/%Y}" in n.body
    Notification.objects.filter(pk=n.pk).delete()
    services.set_plan(req, actor=hansen, plan_title="Seragamkan alur", target_date=target)
    assert not _notes(yohanes, "rencana", req).exists()
    services.set_plan(req, actor=hansen, plan_title="Seragamkan alur v2", target_date=target)
    assert _notes(yohanes, "rencana", req).count() == 1


# --- Pemicu 3: permintaan selesai ----------------------------------------------


def test_request_done_only_after_last_task_on_time(yohanes, hansen, desy, jemur):
    req = _request(yohanes)
    t1 = _task(req, hansen, jemur, desy, title="A")
    t2 = _task(req, hansen, jemur, desy, title="B")
    _finish(t1, hansen, desy)
    assert not _notes(yohanes, "selesai", req).exists()
    _finish(t2, hansen, desy)
    n = _notes(yohanes, "selesai", req).get()
    assert n.title == f"Permintaan selesai: {req.title}" and "tepat waktu" in n.body


def test_request_done_late(yohanes, hansen, desy, jemur):
    req = _request(yohanes)
    OwnerRequest.objects.filter(pk=req.pk).update(target_date=local_today() - dt.timedelta(days=3))
    _finish(_task(req, hansen, jemur, desy), hansen, desy)
    assert "terlambat 3 hari" in _notes(yohanes, "selesai", req).get().body


def test_close_task_path_notifies(yohanes, hansen, desy, jemur):
    from core.task_services import close_task

    req = _request(yohanes)
    close_task(_task(req, hansen, jemur, desy), actor=hansen, note="selesai langsung")
    assert _notes(yohanes, "selesai", req).get().title.startswith("Permintaan selesai")


def test_cancel_last_open_task_notifies(yohanes, hansen, desy, jemur):
    from core.task_services import cancel_task

    req = _request(yohanes)
    t1 = _task(req, hansen, jemur, desy, title="A")
    t2 = _task(req, hansen, jemur, desy, title="B")
    _finish(t1, hansen, desy)
    assert not _notes(yohanes, "selesai", req).exists()
    cancel_task(t2, actor=hansen, reason="tidak jadi")
    assert _notes(yohanes, "selesai", req).get().title.startswith("Permintaan selesai")


def test_cancel_with_other_open_task_does_not_notify(yohanes, hansen, desy, jemur):
    from core.task_services import cancel_task

    req = _request(yohanes)
    t1 = _task(req, hansen, jemur, desy, title="A")
    _task(req, hansen, jemur, desy, title="B")
    cancel_task(t1, actor=hansen, reason="tidak jadi")
    assert not _notes(yohanes, "selesai", req).exists()


def test_finding_tasks_done_does_not_send_request_done(yohanes, hansen, desy, jemur):
    req = _temuan(yohanes)
    _finish(_task(req, hansen, jemur, desy), hansen, desy)
    assert not _notes(yohanes, "selesai", req).exists()


def test_deleted_request_is_ignored(yohanes, hansen, desy, jemur):
    from core.task_services import close_task

    req = _request(yohanes)
    item = _task(req, hansen, jemur, desy)
    OwnerRequest.objects.filter(pk=req.pk).delete()
    close_task(item, actor=hansen, note="selesai")
    assert ActionItem.objects.get(pk=item.pk).status == "SELESAI"
