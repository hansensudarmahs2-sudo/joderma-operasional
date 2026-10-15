"""Hutang DO (15 Okt 2026): satu halaman untuk semua yang menunggu Direktur."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import ActionItem, ActionItemStatus, Clinic, Priority, TaskAssignment, TaskAssignmentStatus
from direktur import hutang, services
from direktur.models import Decider, Decision, DecisionStatus
from owner.models import OwnerRequest, RequestKind

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, username, roles):
    user = User.objects.create_user(username=username, password=PASSWORD, display_name=username.title())
    for role in roles:
        UserRole.objects.create(user=user, clinic=clinic, role=role)
    return user


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def director(jemur):
    return _user(jemur, "direktur", [Role.AOM])


@pytest.fixture
def owner(jemur):
    return _user(jemur, "owner", [Role.OWNER])


@pytest.fixture
def heni(jemur):
    return _user(jemur, "heni", [Role.SUPERVISOR])


def _task(actor, clinic, title, target, due=None):
    return services.create_manual_task(actor=actor, clinic=clinic, title=title, target=target, due_at=due)


def test_only_director_can_open(client, jemur, director, heni, owner):
    url = reverse("direktur:hutang")
    client.force_login(heni)
    assert client.get(url).status_code == 403
    client.force_login(owner)
    assert client.get(url).status_code == 403
    client.force_login(director)
    assert client.get(url).status_code == 200


def test_page_collects_everything_that_waits_for_director(client, jemur, director, heni, owner):
    kemarin = timezone.now() - dt.timedelta(days=1)
    lusa = timezone.now() + dt.timedelta(days=2)
    # 1. task saya: satu lewat tenggat, satu tanpa tenggat → yang lewat di atas
    _task(director, jemur, "Tanpa tenggat", f"user:{director.pk}")
    _task(director, jemur, "Lewat tenggat", f"user:{director.pk}", due=kemarin)
    # 2. task yang saya berikan ke Heni, belum selesai
    _task(director, jemur, "Untuk Heni", f"user:{heni.pk}", due=lusa)
    # 3. permintaan Owner: satu tinggal ditutup (task selesai), satu masih berjalan, satu sudah ditutup
    tutup = OwnerRequest.objects.create(kind=RequestKind.TEMUAN, title="Lagu rock", created_by=owner)
    done = ActionItem.objects.create(
        clinic=jemur, title="Ganti lagu", owner=heni, created_by=director, status=ActionItemStatus.SELESAI,
        source_type="permintaan_owner", source_id=tutup.pk, source_label=f"Temuan P-{tutup.pk}",
    )
    jalan = OwnerRequest.objects.create(kind=RequestKind.TEMUAN, title="Vit C kosong", created_by=owner)
    ActionItem.objects.create(
        clinic=jemur, title="Penyisiran BHP", owner=heni, created_by=director, status=ActionItemStatus.BARU,
        source_type="permintaan_owner", source_id=jalan.pk, source_label=f"Temuan P-{jalan.pk}",
    )
    OwnerRequest.objects.create(kind=RequestKind.PERMINTAAN, title="Sudah selesai", created_by=owner,
                                completed_at=timezone.now(), completed_by=director)
    # 4. keputusan menunggu Owner, tanpa tanggal
    Decision.objects.create(title="Harga bedah", decider=Decider.OWNER, status=DecisionStatus.MENUNGGU,
                            created_by=director)
    Decision.objects.create(title="Sudah ditetapkan", decider=Decider.OWNER, status=DecisionStatus.DITETAPKAN,
                            created_by=director, decided_on=timezone.localdate())

    ctx = hutang.context(director)
    assert [r["item"].title for r in ctx["mine"]] == ["Lewat tenggat", "Tanpa tenggat"]
    assert ctx["mine_overdue"] == 1
    assert [i.title for i in ctx["delegated"]] == ["Untuk Heni", "Penyisiran BHP"]  # bertenggat dulu, tanpa tenggat di bawah
    assert [r["req"].title for r in ctx["owner_tutup"]] == ["Lagu rock"]
    assert ctx["owner_tutup"][0]["tasks_total"] == 1 and done.status == ActionItemStatus.SELESAI
    assert [r["req"].title for r in ctx["owner_berjalan"]] == ["Vit C kosong"]
    assert [d.title for d in ctx["decisions"]] == ["Harga bedah"]
    assert ctx["decisions_no_date"] == 1
    # task saya + task dari saya + tinggal ditutup + butir pengingat hari ini yang belum diingatkan
    assert ctx["total"] == 2 + 2 + 1 + ctx["pengingat_terbuka"]

    client.force_login(director)
    html = client.get(reverse("direktur:hutang")).content.decode()
    for text in ("Lewat tenggat", "Untuk Heni", "Lagu rock", "Vit C kosong", "Harga bedah", "tanpa tanggal"):
        assert text in html
    assert "Sudah selesai" not in html
    assert "Sudah ditetapkan" not in html


def test_quick_note_becomes_task_for_self_with_due(client, jemur, director):
    client.force_login(director)
    resp = client.post(
        reverse("direktur:hutang"),
        {"judul": "Pasang Telegram di HP klinik", "batas": "2026-10-20", "cabang": str(jemur.pk)},
    )
    assert resp.status_code == 302
    item = ActionItem.objects.get(title="Pasang Telegram di HP klinik")
    assert item.owner == director and item.created_by == director and item.clinic == jemur
    assert item.priority == Priority.SEDANG
    assert timezone.localtime(item.due_at).date() == dt.date(2026, 10, 20)
    assert TaskAssignment.objects.filter(action_item=item, assignee=director).exists()
    # tampil di bagian "Task saya"
    html = client.get(reverse("direktur:hutang")).content.decode()
    assert "Pasang Telegram di HP klinik" in html


def test_quick_note_requires_title(client, jemur, director):
    client.force_login(director)
    resp = client.post(reverse("direktur:hutang"), {"judul": "   ", "batas": "", "cabang": str(jemur.pk)}, follow=True)
    assert resp.status_code == 200
    assert ActionItem.objects.count() == 0
    assert "Judul task wajib diisi." in resp.content.decode()


def test_menu_has_hutang_link(client, jemur, director):
    client.force_login(director)
    html = client.get(reverse("direktur:overview")).content.decode()
    assert reverse("direktur:hutang") in html
    assert "Hutang DO" in html
