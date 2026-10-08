"""Halaman detail task (/direktur/task/<id>/): Direktur bisa mengubah task yang sudah dikirim.

Kasus nyata 1 Okt 2026: task "Limbah perlu koordinasi ..." untuk Desy tampil di Jadwal Task
tetapi Direktur (hanya peran AOM) tidak punya tempat untuk mengubah statusnya.
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import (
    ActionItem,
    ActionItemStatus,
    Clinic,
    Priority,
    TaskAssignmentStatus,
    TaskAudienceType,
    TaskEvent,
    TaskEventType,
)
from core.task_services import create_task, submit_assignment

pytestmark = pytest.mark.django_db


def _user(clinic, username, *roles):
    user = User.objects.create_user(username=username, password="x", display_name=username.title())
    for role in roles:
        UserRole.objects.create(user=user, clinic=clinic, role=role)
    return user


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def director(jemur):
    return _user(jemur, "hansen1", Role.AOM)


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.PERAWAT)


@pytest.fixture
def task(jemur, director, desy):
    return create_task(
        clinic=jemur, actor=director, title="Limbah perlu koordinasi dengan vendor",
        audience_type=TaskAudienceType.USER, user_ids=[desy.pk],
        due_at=timezone.now() - dt.timedelta(days=1),
    )


def _url(item):
    return reverse("direktur:task_detail", args=[item.pk])


def test_task_titles_link_to_detail(client, director, task):
    client.force_login(director)
    for name in ("direktur:gantt", "direktur:kanban", "direktur:matrix", "direktur:team"):
        body = client.get(reverse(name)).content.decode()
        assert _url(task) in body, name
    body = client.get(_url(task) + "?dari=gantt").content.decode()
    assert "Ubah task" in body and "Tandai selesai" in body and "← Jadwal Task" in body


def test_director_closes_task_without_waiting_for_staff(client, director, desy, task):
    client.force_login(director)
    resp = client.post(_url(task), {"aksi": "selesai", "bintang": "5", "catatan": "Vendor sudah dijadwalkan"})
    assert resp.status_code == 302
    task.refresh_from_db()
    a = task.task_assignments.get()
    assert task.status == ActionItemStatus.SELESAI
    assert a.status == TaskAssignmentStatus.CONFIRMED and a.reviewer == director
    assert TaskEvent.objects.filter(action_item=task, event_type=TaskEventType.CONFIRMED).exists()
    assert AuditEvent.objects.filter(action=AuditAction.CLOSE, entity_id=task.pk).exists()
    # Hilang dari Jadwal Task sebagai "lewat target"
    body = client.get(reverse("direktur:gantt")).content.decode()
    assert "bar-late" not in body


def test_close_requires_note(client, director, task):
    client.force_login(director)
    client.post(_url(task), {"aksi": "selesai", "bintang": "5", "catatan": " "})
    task.refresh_from_db()
    assert task.status == ActionItemStatus.BARU


def test_director_updates_status_priority_and_target(client, director, task):
    client.force_login(director)
    client.post(_url(task), {
        "aksi": "ubah", "status": "DIKERJAKAN", "prioritas": Priority.TINGGI,
        "batas": (timezone.localdate() + dt.timedelta(days=3)).isoformat(), "progres": "Menunggu vendor",
    })
    task.refresh_from_db()
    assert task.status == ActionItemStatus.DIKERJAKAN and task.priority == Priority.TINGGI
    assert not task.is_overdue and task.progress_note == "Menunggu vendor"
    old_due = task.due_at
    # Tanggal sama -> jam target lama dipertahankan
    client.post(_url(task), {
        "aksi": "ubah", "status": "DIKERJAKAN", "prioritas": Priority.TINGGI,
        "batas": timezone.localtime(old_due).date().isoformat(), "progres": "",
    })
    task.refresh_from_db()
    assert task.due_at == old_due
    # Status Selesai tidak boleh lewat formulir ubah
    client.post(_url(task), {"aksi": "ubah", "status": "SELESAI", "prioritas": Priority.TINGGI, "batas": ""})
    task.refresh_from_db()
    assert task.status == ActionItemStatus.DIKERJAKAN


def test_confirm_and_revision_from_detail(client, director, desy, task):
    a = task.task_assignments.get()
    submit_assignment(a, user=desy, note="Sudah ditelepon")
    client.force_login(director)
    assert "Konfirmasi selesai" in client.get(_url(task)).content.decode()
    client.post(_url(task), {"aksi": "revisi", "assignment": a.pk, "catatan": "Lampirkan jadwal vendor"})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.REVISION_REQUIRED
    submit_assignment(a, user=desy)
    client.post(_url(task), {"aksi": "konfirmasi", "bintang": "5", "assignment": a.pk})
    task.refresh_from_db()
    assert task.status == ActionItemStatus.SELESAI


def test_cancel_task(client, director, task):
    client.force_login(director)
    client.post(_url(task), {"aksi": "batal", "catatan": "Digabung dengan task lain"})
    task.refresh_from_db()
    assert task.status == ActionItemStatus.BATAL
    assert task.task_assignments.get().status == TaskAssignmentStatus.CANCELLED


def test_comment_appears_in_history(client, director, task):
    client.force_login(director)
    client.post(_url(task), {"aksi": "catatan", "catatan": "Vendor datang Senin"})
    assert "Vendor datang Senin" in client.get(_url(task)).content.decode()


def test_owner_reads_only(client, jemur, task):
    owner = _user(jemur, "yohanes", Role.OWNER)
    client.force_login(owner)
    body = client.get(_url(task)).content.decode()
    assert task.title in body and "Ubah task" not in body and "Tandai selesai" not in body
    assert client.post(_url(task), {"aksi": "selesai", "bintang": "5", "catatan": "x"}).status_code == 403
    task.refresh_from_db()
    assert task.status == ActionItemStatus.BARU


def test_staff_cannot_open_detail(client, desy, task):
    client.force_login(desy)
    assert client.get(_url(task)).status_code == 403


def test_director_can_use_old_action_item_update(client, director, task):
    client.force_login(director)
    resp = client.post(reverse("core:action_item_update", args=[task.pk]), {"status": "DIKERJAKAN", "catatan": ""})
    assert resp.status_code == 302
    task.refresh_from_db()
    assert task.status == ActionItemStatus.DIKERJAKAN
