"""Paket D tahap 2: bahan rapat mingguan (Kamis lalu s.d. Rabu)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import ActionItem, Clinic, TaskAudienceType, local_today
from core.task_services import confirm_assignment, create_task, submit_assignment
from direktur import meeting, services
from direktur.models import Decider
from issues.models import Issue, IssueType
from issues.services import create_issue
from owner.models import RequestKind
from owner.services import create_request

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _meeting_covering_today() -> dt.date:
    """Kamis setelah hari ini, supaya hari ini masuk periode (Kamis lalu s.d. Rabu)."""
    today = local_today()
    return today + dt.timedelta(days=(3 - today.weekday()) % 7 or 7)


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="JC", name="Joderma Citraland")


@pytest.fixture
def people(jemur, citraland):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM),
        "jean": _user(jemur, "jean", Role.OWNER),
        "heni": _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT, Role.STAF),
        "regita": _user(citraland, "regita", Role.SUPERVISOR, Role.STAF),
    }


def test_period_and_parse():
    assert meeting.period_for(dt.date(2026, 10, 8)) == (dt.date(2026, 10, 1), dt.date(2026, 10, 7))
    assert meeting.parse_meeting("2026-10-05") == dt.date(2026, 10, 8)  # dibulatkan ke Kamis
    assert meeting.parse_meeting("2026-10-08") == dt.date(2026, 10, 8)
    assert meeting.parse_meeting("ngawur", today=dt.date(2026, 10, 3)) == dt.date(2026, 10, 8)


@pytest.fixture
def week(people, jemur, citraland):
    h, j = people["hansen"], people["jean"]
    services.create_decision(actor=h, title="Ganti vendor limbah", decider=Decider.RAPAT_BERSAMA, clinic=jemur)
    services.create_decision(actor=h, title="Harga paket baru", decider=Decider.DIRUT)
    settled = services.create_decision(actor=h, title="Jam buka Minggu", decider=Decider.RAPAT_BERSAMA)
    services.settle_decision(settled, actor=h, decision_text="Buka 09.00")
    create_request(actor=j, kind=RequestKind.TEMUAN, title="Sampah lobi penuh", clinic=jemur)
    done = create_task(clinic=jemur, actor=h, title="Servis AC", audience_type=TaskAudienceType.USER,
                       user_ids=[people["heni"].pk])
    a = done.task_assignments.get()
    submit_assignment(a, user=people["heni"], note="AC dingin lagi")
    confirm_assignment(a, reviewer=h)
    create_task(clinic=citraland, actor=h, title="Rapikan rak obat", audience_type=TaskAudienceType.USER,
                user_ids=[people["regita"].pk], due_at=timezone.now() - dt.timedelta(days=3))
    create_issue(clinic=citraland, issue_type=IssueType.KERUSAKAN, title="Lampu lobi mati", user=people["regita"],
                 location="Lobi", impact="NORMAL")
    services.create_note(author=h, body="Catatan pribadi direktur", clinic=citraland)
    old = create_issue(clinic=jemur, issue_type=IssueType.MASUKAN, title="Masukan lama", user=people["heni"])
    Issue.objects.filter(pk=old.pk).update(created_at=timezone.now() - dt.timedelta(days=20))
    old_done = create_task(clinic=jemur, actor=h, title="Task lama", audience_type=TaskAudienceType.USER,
                           user_ids=[people["heni"].pk])
    ActionItem.objects.filter(pk=old_done.pk).update(status="SELESAI",
                                                     updated_at=timezone.now() - dt.timedelta(days=20))


def test_compose_collects_the_week(people, week):
    data = meeting.compose(people["hansen"], _meeting_covering_today())
    assert [r["decision"].title for r in data["agenda_rapat"]] == ["Ganti vendor limbah"]
    assert [r["decision"].title for r in data["agenda_lain"]] == ["Harga paket baru"]
    assert [d.title for d in data["decided"]] == ["Jam buka Minggu"]
    req = data["requests"][0]
    assert req["request"].title == "Sampah lobi penuh" and req["new"]
    assert [x["item"].title for x in data["done"]] == ["Servis AC"]
    assert data["done"][0]["people"] == "Heni" and data["done"][0]["reviewers"] == "Hansen1"
    assert [x["item"].title for x in data["overdue"]] == ["Rapikan rak obat"]
    inbox = data["inbox"]
    assert inbox["Joderma Citraland"]["kinds"] == {"Kerusakan": 1}  # catatan pribadi Direktur tidak ikut
    assert "Masukan" not in inbox.get("JoDerma Jemur Andayani", {}).get("kinds", {})  # di luar periode
    text = meeting.as_text(data)
    for line in ("*Agenda keputusan bersama*", "1. Ganti vendor limbah — JoDerma Jemur Andayani",
                 "Menunggu pemutus lain: 1 perkara", "- Jam buka Minggu: Buka 09.00",
                 "[temuan] Sampah lobi penuh (baru)", "*Selesai dan terverifikasi: 1 task*",
                 "*Lewat target: 1 task*", "- Joderma Citraland: 1 (Kerusakan 1)"):
        assert line in text, line
    assert "Task lama" not in text


def test_page_access_and_navigation(client, people, week):
    m = _meeting_covering_today()
    for who in ("hansen", "jean"):
        client.force_login(people[who])
        body = client.get(reverse("direktur:meeting"), {"tanggal": m.isoformat()}).content.decode()
        assert "Bahan rapat Kamis" in body and "Ganti vendor limbah" in body and "Servis AC" in body
        assert 'id="teks-rapat"' in body and "Salin untuk WhatsApp" in body
        assert 'href="/direktur/rapat/">Bahan Rapat</a>' in body
        prev = (m - dt.timedelta(days=7)).isoformat()
        assert f"?tanggal={prev}" in body
    client.force_login(people["hansen"])
    overview = client.get(reverse("direktur:overview")).content.decode()
    assert reverse("direktur:meeting") in overview
    for who in ("heni", "regita"):
        client.force_login(people[who])
        assert client.get(reverse("direktur:meeting")).status_code in (302, 403)
