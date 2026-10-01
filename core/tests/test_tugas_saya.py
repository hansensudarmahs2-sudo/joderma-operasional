"""Tugas saya di halaman Hari Ini: task yang dikirim ke staf harus terlihat tanpa dicari.

Kasus nyata (1 Oktober 2026): task "pengolahan limbah" untuk Desy ada di database tetapi
tidak tampil di Hari Ini. Sebabnya: daftar lama hanya muncul bila sesi hari operasional
sudah dibuat, hanya membaca `ActionItem.owner` (kosong untuk task ke banyak orang/peran),
dan hanya cabang aktif.
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import (
    ActionItem,
    ActionItemStatus,
    Clinic,
    OperationalDay,
    TaskAssignmentMode,
    TaskAssignmentStatus,
    TaskAudienceType,
)
from core.task_services import claim_shared_task, create_task, my_tasks, submit_assignment

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="JC", name="Citraland")


@pytest.fixture
def hansen(jemur, citraland):
    u = _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")
    return u


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.PERAWAT, Role.FRONT_DESK, Role.STAF, display_name="Desy")


def _task(actor, clinic, title, *, users=None, role="", mode=TaskAssignmentMode.INDIVIDUAL, due=None):
    return create_task(
        clinic=clinic, actor=actor, title=title,
        audience_type=TaskAudienceType.ROLE if role else (
            TaskAudienceType.USER if len(users or []) == 1 else TaskAudienceType.USERS),
        user_ids=[u.pk for u in users or []], role=role, mode=mode, due_at=due,
        description="Pilah limbah medis, timbang, catat di log.",
    )


def test_task_shows_on_hari_ini_without_operational_day(client, jemur, hansen, desy):
    _task(hansen, jemur, "Pengolahan limbah", users=[desy])
    assert not OperationalDay.objects.exists()
    client.force_login(desy)
    body = client.get(reverse("core:dashboard")).content.decode()
    card = body.split('id="tugas-saya"', 1)[1].split("</section>", 1)[0]
    assert "Pengolahan limbah" in card and "dari dr. Hansen" in card and "Pilah limbah medis" in card
    assert "Ajukan selesai" in card
    # Bagian tugas berada di atas, sebelum status hari operasional.
    assert body.index('id="tugas-saya"') < body.index("Belum ada sesi hari operasional")


def test_task_sent_to_many_people_shows_for_each(client, jemur, hansen, desy):
    lia = _user(jemur, "lia", Role.PERAWAT, Role.STAF)
    item = _task(hansen, jemur, "Rapikan troli tindakan", users=[desy, lia])
    assert item.owner is None  # tidak ada owner tunggal
    assert [r["item"].pk for r in my_tasks(desy)] == [item.pk]
    assert [r["item"].pk for r in my_tasks(lia)] == [item.pk]


def test_role_task_and_other_branch(client, jemur, citraland, hansen, desy):
    UserRole.objects.create(user=desy, clinic=citraland, role=Role.PERAWAT)  # perbantuan
    item = _task(hansen, citraland, "Cek autoklaf Citraland", users=[desy])
    role_item = _task(hansen, jemur, "Briefing perawat", role=Role.PERAWAT)
    titles = {r["item"].title for r in my_tasks(desy)}
    assert {item.title, role_item.title} <= titles
    client.force_login(desy)
    page = client.get(reverse("core:action_items")).content.decode()
    assert "Cek autoklaf Citraland" in page  # halaman semua task juga lintas cabang


def test_order_states_and_hidden_cases(jemur, hansen, desy):
    now = timezone.now()
    later = _task(hansen, jemur, "Minggu depan", users=[desy], due=now + dt.timedelta(days=5))
    late = _task(hansen, jemur, "Sudah lewat", users=[desy], due=now - dt.timedelta(hours=3))
    waiting = _task(hansen, jemur, "Sudah diajukan", users=[desy])
    submit_assignment(waiting.task_assignments.get(), user=desy)
    done = _task(hansen, jemur, "Selesai", users=[desy])
    done.status = ActionItemStatus.SELESAI
    done.save()
    cancelled = _task(hansen, jemur, "Dibatalkan", users=[desy])
    cancelled.task_assignments.update(status=TaskAssignmentStatus.CANCELLED)
    rows = my_tasks(desy)
    assert [r["item"].title for r in rows] == ["Sudah lewat", "Minggu depan", "Sudah diajukan"]
    assert rows[0]["overdue"] and rows[-1]["waiting"] and not rows[-1]["can_submit"]
    assert later.pk and late.pk


def test_shared_task_claimed_by_other_disappears(jemur, hansen, desy):
    lia = _user(jemur, "lia", Role.PERAWAT, Role.STAF)
    item = _task(hansen, jemur, "Ambil sampel", users=[desy, lia], mode=TaskAssignmentMode.BERSAMA)
    row = my_tasks(desy)[0]
    assert row["can_claim"] and not row["can_submit"]
    claim_shared_task(item.task_assignments.get(assignee=lia), user=lia)
    assert my_tasks(desy) == []
    assert my_tasks(lia)[0]["can_submit"]


def test_submit_from_hari_ini_returns_there(client, jemur, hansen, desy):
    item = _task(hansen, jemur, "Pengolahan limbah", users=[desy])
    assignment = item.task_assignments.get()
    client.force_login(desy)
    response = client.post(reverse("core:assignment_submit", args=[assignment.pk]),
                           {"next": reverse("core:dashboard")})
    assert response["Location"] == reverse("core:dashboard")
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED
    body = client.get(reverse("core:dashboard")).content.decode()
    assert "Menunggu konfirmasi" in body
    # `next` ke luar aplikasi diabaikan.
    item2 = _task(hansen, jemur, "Lain", users=[desy])
    response = client.post(reverse("core:assignment_submit", args=[item2.task_assignments.get().pk]),
                           {"next": "https://contoh.invalid/"})
    assert response["Location"] == reverse("core:action_items")


def test_other_people_cannot_see_or_submit(client, jemur, hansen, desy):
    item = _task(hansen, jemur, "Pengolahan limbah", users=[desy])
    yani = _user(jemur, "yani", Role.PERAWAT, Role.STAF)
    assert my_tasks(yani) == []
    client.force_login(yani)
    client.post(reverse("core:assignment_submit", args=[item.task_assignments.get().pk]),
                {"next": reverse("core:dashboard")})
    assert item.task_assignments.get().status == TaskAssignmentStatus.OPEN


def test_owner_only_item_without_assignment_still_listed(jemur, desy):
    item = ActionItem.objects.create(clinic=jemur, title="Tindak lanjut checklist", source_type="checklist",
                                     owner=desy)
    assert [r["item"].pk for r in my_tasks(desy)] == [item.pk]


def test_empty_state(client, jemur, desy):
    client.force_login(desy)
    assert "Tidak ada tugas yang menunggu Anda." in client.get(reverse("core:dashboard")).content.decode()
