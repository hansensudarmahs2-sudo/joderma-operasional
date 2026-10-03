"""Penutupan tanpa batas jam (keputusan 4 Okt 2026): tutup boleh molor lewat tengah malam karena
menunggu pasien terakhir; hari kemarin yang belum ditutup tetap menjadi hari yang berjalan sampai 06.00."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import ClinicConfig, DayStatus, OperationalDay, operational_date
from core.services import get_or_create_day
from jadwal.models import DutyAssignment, DutyGroup, DutyPortion

pytestmark = pytest.mark.django_db


def _local(day, hh, mm=0):
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hh, mm)), timezone.get_current_timezone())


def test_operational_date_keeps_unclosed_yesterday_until_cutoff(clinic):
    today = timezone.localdate()
    yesterday = today - dt.timedelta(days=1)
    assert operational_date(clinic, now=_local(today, 0, 30)) == today  # belum ada hari kemarin
    day = OperationalDay.objects.create(clinic=clinic, date=yesterday, status=DayStatus.CLOSING)
    assert operational_date(clinic, now=_local(today, 0, 30)) == yesterday
    assert operational_date(clinic, now=_local(today, 5, 59)) == yesterday
    assert operational_date(clinic, now=_local(today, 6, 0)) == today  # persiapan buka hari baru
    ClinicConfig.set(clinic, "day.late_close_cutoff_hour", 3)
    assert operational_date(clinic, now=_local(today, 4, 0)) == today
    ClinicConfig.set(clinic, "day.late_close_cutoff_hour", 6)
    day.status = DayStatus.CLOSED
    day.save()
    assert operational_date(clinic, now=_local(today, 0, 30)) == today  # sudah ditutup: hari baru


def test_cashier_closes_cash_after_midnight(client, clinic, monkeypatch):
    today = timezone.localdate()
    yesterday = today - dt.timedelta(days=1)
    kasir = User.objects.create_user(username="nanda", password="TestPassword123!", display_name="Nanda")
    for role in (Role.FRONT_DESK, Role.STAF):
        UserRole.objects.create(user=kasir, clinic=clinic, role=role)
    kas = DutyPortion.objects.create(clinic=clinic, code="kas", name="Kasir hari ini", group=DutyGroup.KAS)
    DutyAssignment.objects.create(portion=kas, clinic=clinic, date=yesterday, user=kasir)
    late_day, _ = get_or_create_day(clinic, date=yesterday)
    late_day.status = DayStatus.OPEN
    late_day.save()

    fixed = _local(today, 0, 40)
    monkeypatch.setattr(timezone, "now", lambda: fixed)
    day, created = get_or_create_day(clinic)
    assert day == late_day and not created  # tidak membuat hari baru tengah malam
    assert OperationalDay.today_for(clinic) == late_day
    client.force_login(kasir)
    resp = client.get(reverse("cash:index"))
    assert resp.status_code == 200 and resp.context["day"] == late_day
    page = client.get(reverse("core:today")).content.decode()
    assert "Anda kasir hari ini" in page
    assert not OperationalDay.objects.filter(clinic=clinic, date=today).exists()
