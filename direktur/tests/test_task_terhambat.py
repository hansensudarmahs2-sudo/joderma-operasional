"""Task terhambat di tampilan Direktur (tahap 3a, 7 Okt 2026)."""
import datetime as dt
import re

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core import task_services as ts
from core.models import ActionItem, Clinic, TaskAudienceType, local_today

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.STAF, display_name="Desy")


def _blocked(hansen, jemur, desy, days=3):
    item = ts.create_task(clinic=jemur, actor=hansen, title="Ganti filter AC", audience_type=TaskAudienceType.USER,
                          user_ids=[desy.pk])
    ts.report_blocker(item.task_assignments.get(), user=desy, reason="Vendor baru bisa Jumat",
                      proposed_due=local_today() + dt.timedelta(days=days))
    return ActionItem.objects.get(pk=item.pk)


def test_detail_shows_box_and_approves(client, jemur, hansen, desy):
    item = _blocked(hansen, jemur, desy)
    client.force_login(hansen)
    url = reverse("direktur:task_detail", args=[item.pk])
    body = client.get(url).content.decode()
    target = (local_today() + dt.timedelta(days=3)).strftime("%d/%m/%Y")
    assert "Terhambat" in body and "Vendor baru bisa Jumat" in body and f"Setujui target {target}" in body
    usulan = re.search(r'name="usulan" value="([^"]+)"', body).group(1)
    client.post(url, {"aksi": "setujui_target", "usulan": usulan})
    item.refresh_from_db()
    assert not item.is_blocked and item.due_at is not None
    assert "Setujui target" not in client.get(url).content.decode()


def test_stale_usulan_does_not_approve(client, jemur, hansen, desy):
    item = _blocked(hansen, jemur, desy, days=3)
    client.force_login(hansen)
    url = reverse("direktur:task_detail", args=[item.pk])
    stale = re.search(r'name="usulan" value="([^"]+)"', client.get(url).content.decode()).group(1)
    ts.report_blocker(item.task_assignments.get(), user=desy, reason="Mundur lagi",
                      proposed_due=local_today() + dt.timedelta(days=6))
    original_due = ActionItem.objects.get(pk=item.pk).due_at
    client.post(url, {"aksi": "setujui_target", "usulan": stale})
    item.refresh_from_db()
    assert item.is_blocked and item.due_at == original_due


def test_staff_cannot_open_director_detail(client, jemur, hansen, desy):
    item = _blocked(hansen, jemur, desy)
    client.force_login(desy)
    assert client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "setujui_target"}).status_code == 403
    assert ActionItem.objects.get(pk=item.pk).is_blocked


def test_list_team_and_overview_show_blocked(client, jemur, hansen, desy):
    item = _blocked(hansen, jemur, desy)
    client.force_login(hansen)
    assert "Terhambat" in client.get(reverse("direktur:tasks")).content.decode()
    assert "Terhambat" in client.get(reverse("direktur:team")).content.decode()
    assert "1 task terhambat" in client.get(reverse("direktur:overview")).content.decode()
    ts.report_progress(item.task_assignments.get(), user=desy, note="Vendor datang")
    assert "task terhambat" not in client.get(reverse("direktur:overview")).content.decode()
