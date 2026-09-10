"""Test otorisasi, session, dan security smoke (PRD 20.1, 21)."""
import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import Capability, Role, User, UserCapability, UserRole
from audit.models import AuditAction, AuditEvent
from core.permissions import (
    can_export,
    can_view_audit,
    can_view_cash_amounts,
    can_verify_cash,
    is_supervisor,
)

pytestmark = pytest.mark.django_db


def _login(client, user):
    assert client.login(username=user.username, password="TestPassword123!")
    return client


# --- Perimeter autentikasi -------------------------------------------------

@pytest.mark.parametrize(
    "url_name",
    [
        "core:dashboard",
        "checklists:index",
        "cash:index",
        "queueing:board",
        "nurses:board",
        "breaks:list",
        "issues:list",
        "reports:index",
        "audit:log",
        "accounts:user_list",
    ],
)
def test_anonymous_cannot_open_any_page(client, clinic, url_name):
    response = client.get(reverse(url_name))
    assert response.status_code in (301, 302)
    assert "/akun/login" in response["Location"]


# --- Matriks izin ----------------------------------------------------------

def test_admin_teknis_has_no_business_data_rights(admin_teknis):
    """Admin teknis tidak otomatis memperoleh hak bisnis sensitif (PRD 6.3)."""
    assert can_view_cash_amounts(admin_teknis) is False
    assert can_verify_cash(admin_teknis) is False
    assert can_view_audit(admin_teknis) is False


def test_admin_gains_capability_only_when_granted_explicitly(admin_teknis):
    UserCapability.objects.create(user=admin_teknis, capability=Capability.CASH_VIEW_AMOUNTS)
    admin_teknis = User.objects.get(pk=admin_teknis.pk)  # buang cache peran
    assert can_view_cash_amounts(admin_teknis) is True


def test_staff_cannot_open_cash_page(client, clinic, staf, template):
    _login(client, staf)
    assert client.get(reverse("cash:index")).status_code == 403


def test_staff_cannot_open_audit_log(client, clinic, staf, template):
    _login(client, staf)
    assert client.get(reverse("audit:log")).status_code == 403


def test_staff_cannot_manage_users(client, clinic, staf):
    _login(client, staf)
    assert client.get(reverse("accounts:user_list")).status_code == 403


def test_supervisor_can_open_audit_and_cash(client, clinic, supervisor, template):
    _login(client, supervisor)
    assert client.get(reverse("audit:log")).status_code == 200
    assert client.get(reverse("cash:index")).status_code == 200


def test_url_manipulation_cannot_bypass_permission(client, clinic, staf, kasir, day):
    """Pengguna tanpa izin tidak dapat mengubah data lewat POST manual (PRD 20.1)."""
    from queueing.services import create_entry
    from queueing.models import PaymentStatus, VisitType

    entry = create_entry(day, user=kasir, display_name="Pasien", visit_type=VisitType.KONSULTASI)
    _login(client, staf)
    response = client.post(
        reverse("queueing:set_payment", args=[entry.pk]),
        {"pembayaran": PaymentStatus.SUDAH_BAYAR},
    )
    assert response.status_code == 403
    entry.refresh_from_db()
    assert entry.payment_status == PaymentStatus.BELUM_BAYAR


def test_export_requires_permission(client, clinic, staf, supervisor, template):
    _login(client, staf)
    assert client.get(reverse("reports:export", args=["antrean"])).status_code == 403

    client2 = Client()
    _login(client2, supervisor)
    response = client2.get(reverse("reports:export", args=["antrean"]))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert AuditEvent.objects.filter(action=AuditAction.EXPORT).exists()


def test_front_desk_cannot_correct_verified_cash_via_url(client, clinic, day, kasir, supervisor):
    """Koreksi pasca-verifikasi tetap eksklusif supervisor (PRD 20.3)."""
    from cash.models import CashSessionType
    from cash.services import get_or_create_session, save_count, submit_for_verification, verify
    from django.urls import reverse as rev

    session = get_or_create_session(day, CashSessionType.OPENING, user=supervisor)
    save_count(session, user=supervisor, quantities={100000: 5}, expected_total=500000)
    submit_for_verification(session, supervisor)
    verify(session, verifier=kasir)

    _login(client, kasir)
    response = client.post(
        rev("cash:correct", args=[session.pk]),
        {"denom_100000": 9, "diharapkan": 900000, "alasan": "coba koreksi"},
    )
    assert response.status_code == 403
    session.refresh_from_db()
    assert session.actual_total == 500000


def test_cash_export_blocked_without_cash_permission(client, clinic, admin_teknis, template):
    UserCapability.objects.create(user=admin_teknis, capability=Capability.REPORT_EXPORT)
    _login(client, admin_teknis)
    assert client.get(reverse("reports:export", args=["kas"])).status_code == 403


# --- Login, throttling, session -------------------------------------------

def test_failed_login_is_generic_and_audited(client, clinic, kasir):
    response = client.post(
        reverse("accounts:login"), {"username": "kasir", "password": "salah"}, follow=True
    )
    body = response.content.decode()
    assert "Nama pengguna atau kata sandi salah" in body
    assert "tidak terdaftar" not in body.lower()
    assert AuditEvent.objects.filter(action=AuditAction.LOGIN_FAILED).exists()


def test_login_lockout_after_repeated_failures(client, clinic, kasir, settings):
    settings.LOGIN_MAX_ATTEMPTS = 3
    for _ in range(3):
        client.post(reverse("accounts:login"), {"username": "kasir", "password": "salah"})
    response = client.post(
        reverse("accounts:login"),
        {"username": "kasir", "password": "TestPassword123!"},
        follow=True,
    )
    assert "Terlalu banyak percobaan gagal" in response.content.decode()


def test_successful_login_is_audited(client, clinic, kasir):
    response = client.post(
        reverse("accounts:login"),
        {"username": "kasir", "password": "TestPassword123!"},
    )
    assert response.status_code == 302
    assert AuditEvent.objects.filter(action=AuditAction.LOGIN_SUCCESS, actor=kasir).exists()


def test_logout_is_audited(client, clinic, kasir):
    client.post(reverse("accounts:login"), {"username": "kasir", "password": "TestPassword123!"})
    client.post(reverse("accounts:logout"))
    assert AuditEvent.objects.filter(action=AuditAction.LOGOUT, actor=kasir).exists()


def test_idle_timeout_logs_user_out(client, clinic, kasir, template, settings):
    import time

    settings.SESSION_IDLE_TIMEOUT_SECONDS = 1
    _login(client, kasir)
    assert client.get(reverse("core:dashboard")).status_code == 200
    time.sleep(1.2)
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302 and "/akun/login" in response["Location"]


def test_deactivated_user_is_logged_out(client, clinic, kasir, template):
    _login(client, kasir)
    kasir.is_active = False
    kasir.save()
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302


def test_csrf_required_for_mutations(clinic, kasir, day):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.login(username="kasir", password="TestPassword123!")
    response = csrf_client.post(reverse("queueing:create"), {"nama": "X", "jenis": "KONSULTASI"})
    assert response.status_code == 403


def test_password_minimum_length_enforced(clinic, kasir):
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.contrib.auth.password_validation import validate_password

    with pytest.raises(DjangoValidationError):
        validate_password("Pendek1!")
    validate_password("KataSandiPanjang2026!")


def test_role_change_is_audited(client, clinic, admin_teknis, staf):
    _login(client, admin_teknis)
    client.post(
        reverse("accounts:user_detail", args=[staf.pk]),
        {
            "username": staf.username,
            "display_name": "Staf",
            "job_title": "",
            "phone": "",
            "is_active": "on",
            "roles": [Role.STAF, Role.FRONT_DESK],
        },
    )
    assert AuditEvent.objects.filter(action=AuditAction.PERMISSION_CHANGED).exists()
    assert UserRole.objects.filter(user=staf, role=Role.FRONT_DESK).exists()


def test_audit_event_is_append_only():
    event = AuditEvent.objects.create(action=AuditAction.CREATE, entity_type="test", entity_id="1")
    event.reason = "diubah"
    with pytest.raises(RuntimeError):
        event.save()
    with pytest.raises(RuntimeError):
        event.delete()


def test_audit_never_stores_password(clinic, kasir):
    from audit.services import snapshot

    data = snapshot(kasir)
    assert "password" not in data
    assert not any("password" in k for k in data)
