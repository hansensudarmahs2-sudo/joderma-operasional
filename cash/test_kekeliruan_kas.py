"""Kekeliruan administratif (3 Okt 2026): Diharapkan tidak diisi kasir sehingga seluruh uang tampak selisih.

Direktur Operasional menutup perkara saat verifikasi: kas terverifikasi dengan catatan, tanda "Ada selisih"
hilang, angka selisih tetap tersimpan.
"""
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import Role, UserRole
from audit.models import AuditAction, AuditEvent
from cash.models import CashSessionType, CashStatus, VerificationResult
from cash.services import cash_summary, get_or_create_session, save_count, submit_for_verification, verify

pytestmark = pytest.mark.django_db


@pytest.fixture
def direktur(clinic):
    from accounts.models import User

    u = User.objects.create_user(username="hansen1", password="TestPassword123!", display_name="Hansen")
    UserRole.objects.create(user=u, clinic=clinic, role=Role.AOM)
    return u


def _counted(day, kasir, expected=0):
    s = get_or_create_session(day, CashSessionType.CLOSING, user=kasir)
    save_count(s, user=kasir, quantities={100000: 6, 50000: 1, 2000: 1, 1000: 1, 500: 1, 200: 1, 100: 1},
               expected_total=expected, note="dipakai bayar ongkir px total: 30000")
    submit_for_verification(s, kasir)
    s.refresh_from_db()
    assert s.variance == 653800
    return s


def test_sesuai_with_variance_is_rejected_with_guidance(day, kasir, supervisor):
    s = _counted(day, kasir)
    with pytest.raises(ValidationError) as exc:
        verify(s, verifier=supervisor, result=VerificationResult.SESUAI)
    assert "kekeliruan administratif" in " ".join(exc.value.messages)
    s.refresh_from_db()
    assert s.status == CashStatus.MENUNGGU_VERIFIKASI


def test_director_closes_as_administrative_error(client, day, kasir, direktur):
    s = _counted(day, kasir)
    assert cash_summary(day)["has_variance"]
    client.force_login(direktur)
    page = client.get(reverse("cash:review", args=[s.pk])).content.decode()
    assert "Setujui: kekeliruan administratif" in page
    client.post(reverse("cash:verify", args=[s.pk]), {"aksi": "administratif", "catatan": "Diharapkan tidak diisi"})
    s.refresh_from_db()
    assert s.status == CashStatus.DISETUJUI_DENGAN_CATATAN and s.is_verified
    assert s.variance == 653800 and not s.variance_open  # angka tetap, perkara ditutup
    v = s.verifications.get()
    assert v.verifier == direktur and v.note == "Kekeliruan administratif: Diharapkan tidak diisi"
    assert not cash_summary(day)["has_variance"]
    assert AuditEvent.objects.filter(entity_type="cashsession", action=AuditAction.VERIFY,
                                     reason__startswith="Kekeliruan administratif").exists()
    page = client.get(reverse("cash:review", args=[s.pk])).content.decode()
    assert "Disetujui dengan catatan" in page and "Setujui: kekeliruan administratif" not in page


def test_already_selisih_can_be_closed_without_correction(client, day, kasir, supervisor, direktur):
    s = _counted(day, kasir)
    verify(s, verifier=supervisor, note="uji coba")  # hasil otomatis: Selisih
    s.refresh_from_db()
    assert s.status == CashStatus.SELISIH
    with pytest.raises(ValidationError):  # verifikasi biasa tidak bisa diulang
        verify(s, verifier=supervisor, note="lagi")
    client.force_login(direktur)
    assert "Tutup perkara selisih" in client.get(reverse("cash:review", args=[s.pk])).content.decode()
    client.post(reverse("cash:verify", args=[s.pk]), {"aksi": "administratif"})
    s.refresh_from_db()
    assert s.status == CashStatus.DISETUJUI_DENGAN_CATATAN
    assert s.verifications.order_by("-id").first().note == "Kekeliruan administratif"


def test_only_director_closes_as_administrative_error(client, day, kasir, supervisor):
    s = _counted(day, kasir)
    client.force_login(supervisor)
    assert "Setujui: kekeliruan administratif" not in client.get(reverse("cash:review", args=[s.pk])).content.decode()
    resp = client.post(reverse("cash:verify", args=[s.pk]), {"aksi": "administratif"})
    assert resp.status_code == 403
    s.refresh_from_db()
    assert s.status == CashStatus.MENUNGGU_VERIFIKASI


def test_open_variances_listed_on_cash_page_after_the_day(client, clinic, day, kasir, supervisor, direktur):
    """Masalah 4 Okt: kas berstatus Selisih dari hari kemarin tidak bisa dicari dari halaman Kas."""
    import datetime as dt

    s = _counted(day, kasir)
    verify(s, verifier=supervisor, note="uji coba")
    type(day).objects.filter(pk=day.pk).update(date=day.date - dt.timedelta(days=1))
    client.force_login(direktur)
    page = client.get(reverse("cash:index")).content.decode()
    assert "Selisih belum ditutup" in page and reverse("cash:review", args=[s.pk]) in page
    client.post(reverse("cash:verify", args=[s.pk]), {"aksi": "administratif"})
    assert "Selisih belum ditutup" not in client.get(reverse("cash:index")).content.decode()
