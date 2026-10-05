"""6 Okt 2026: angka "diharapkan" kas disusun sistem (keputusan product owner).

Kasus nyata Citraland 4–5 Okt: kolom "Uang modal diharapkan" dibiarkan 0 sehingga seluruh uang
terbaca sebagai selisih (Rp 653.800, 821.800, 784.800).
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Capability, Role, User, UserCapability, UserRole
from cash.models import CashSession, CashSessionType, CashStatus
from cash.services import expected_baseline, expected_for, get_or_create_session, save_count
from core.models import DayStatus, OperationalDay, operational_date

pytestmark = pytest.mark.django_db


def _prev_closing(clinic, date, user, amount):
    """Kas akhir hari sebelumnya, lalu harinya ditutup (supaya tidak dianggap hari berjalan sebelum 06.00)."""
    day = OperationalDay.objects.create(clinic=clinic, date=date)
    session = get_or_create_session(day, CashSessionType.CLOSING, user=user)
    _count(session, user, amount)
    OperationalDay.objects.filter(pk=day.pk).update(status=DayStatus.CLOSED)
    day.refresh_from_db()
    return day


def _count(session, user, amount, expected=None):
    """Hitungan cepat dalam lembar Rp 100.000, Rp 1.000, dan koin Rp 100."""
    q = {100000: amount // 100000, 1000: (amount % 100000) // 1000, 100: (amount % 1000) // 100}
    return save_count(session, user=user, quantities=q, expected_total=amount if expected is None else expected,
                      note="uji")


@pytest.fixture
def kasir(clinic):
    u = User.objects.create_user(username="nanda", password="TestPassword123!", display_name="Nanda")
    for r in (Role.FRONT_DESK, Role.SUPERVISOR):
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    UserCapability.objects.get_or_create(user=u, capability=Capability.CASH_VIEW_AMOUNTS)
    return u


def test_baseline_rules(clinic, kasir):
    today = operational_date(clinic)  # hari operasional (tutup molor s.d. 06.00)
    day = OperationalDay.objects.create(clinic=clinic, date=today)
    opening = get_or_create_session(day, CashSessionType.OPENING, user=kasir)
    # Belum ada kas akhir sebelumnya: manual.
    assert expected_baseline(opening)["base"] is None
    assert expected_for(opening, manual=500_000) == (500_000, "Diisi manual (belum ada kas akhir sebelumnya)")

    yday = _prev_closing(clinic, today - dt.timedelta(days=2), kasir, 653_800)
    # Kas awal = kas akhir terakhir (hari libur di antaranya dilewati), angka manual diabaikan.
    expected, basis = expected_for(opening, manual=0)
    assert expected == 653_800 and basis.startswith(f"Kas akhir {yday.date:%d/%m/%Y}") and "Nanda" in basis

    closing = get_or_create_session(day, CashSessionType.CLOSING, user=kasir)
    # Kas awal hari ini belum dihitung: dasar kas akhir terakhir.
    assert expected_for(closing, cash_in=100_000)[0] == 753_800
    _count(opening, kasir, 821_800, expected=653_800)
    expected, basis = expected_for(closing, cash_in=250_000, cash_out=50_000)
    assert expected == 821_800 + 200_000 and basis.startswith("Kas awal hari ini")


def test_form_uses_system_expected_and_submits(client, clinic, kasir):
    today = operational_date(clinic)  # hari operasional (tutup molor s.d. 06.00)
    _prev_closing(clinic, today - dt.timedelta(days=1), kasir, 653_800)
    client.force_login(kasir)
    page = client.get(reverse("cash:form", args=["OPENING"])).content.decode()
    assert "Yang seharusnya ada" in page and "653.800" in page and 'name="diharapkan"' not in page
    session = CashSession.objects.get(operational_day__date=today, session_type=CashSessionType.OPENING)
    post = {"versi": session.version, "denom_100000": 6, "denom_50000": 1, "denom_2000": 1, "denom_1000": 1,
            "denom_500": 1, "denom_200": 1, "denom_100": 1, "diharapkan": "0", "ajukan": "1"}
    # 653.800 tepat: kasir tidak mengisi diharapkan (0) tapi sistem memakai kas akhir kemarin.
    resp = client.post(reverse("cash:save", args=[session.pk]), post)
    session.refresh_from_db()
    assert resp.status_code == 302 and session.expected_total == 653_800 and session.variance == 0
    assert session.status == CashStatus.MENUNGGU_VERIFIKASI and session.expected_basis.startswith("Kas akhir")

    # Kas akhir: kas awal + tunai masuk − tunai keluar.
    page = client.get(reverse("cash:form", args=["CLOSING"])).content.decode()
    assert "Tunai masuk hari ini" in page and "Kas awal hari ini" in page
    closing = CashSession.objects.get(operational_day__date=today, session_type=CashSessionType.CLOSING)
    client.post(reverse("cash:save", args=[closing.pk]), {
        "versi": closing.version, "denom_100000": 8, "tunai_masuk": "200000", "tunai_keluar": "53800",
        "catatan": "", "diharapkan": "0"})
    closing.refresh_from_db()
    assert closing.expected_total == 653_800 + 200_000 - 53_800 == 800_000
    assert closing.variance == 0 and closing.cash_in_total == 200_000 and closing.status == CashStatus.DRAFT


def test_review_shows_system_comparison_for_old_zero_expected(client, clinic, kasir):
    today = operational_date(clinic)  # hari operasional (tutup molor s.d. 06.00)
    _prev_closing(clinic, today - dt.timedelta(days=1), kasir, 653_800)
    day = OperationalDay.objects.create(clinic=clinic, date=today)
    opening = get_or_create_session(day, CashSessionType.OPENING, user=kasir)
    _count(opening, kasir, 821_800, expected=0)  # cara lama: diharapkan dibiarkan 0
    client.force_login(kasir)
    page = client.get(reverse("cash:review", args=[opening.pk])).content.decode()
    assert "Pembanding dari sistem" in page and "653.800" in page and "lebih <strong>Rp 168.000" in page
    assert clinic.name in page
    index = client.get(reverse("cash:index")).content.decode()
    assert f"Kas · {clinic.name}" in index
