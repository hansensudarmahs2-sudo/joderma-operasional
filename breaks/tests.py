"""Test jadwal istirahat: overlap dan minimum staffing (PRD 20.6)."""
import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import Role, User, UserRole
from breaks.models import BreakStatus, BreakType
from breaks.services import cancel_break, create_break, has_overlap, staffing_warnings, update_break
from core.models import ClinicConfig

pytestmark = pytest.mark.django_db


def _dt(hour, minute=0):
    today = timezone.localtime(timezone.now()).date()
    return timezone.make_aware(
        dt.datetime.combine(today, dt.time(hour, minute)), timezone.get_current_timezone()
    )


def _today():
    return timezone.localtime(timezone.now()).date()


def _extra_front_desk(clinic, username):
    user = User.objects.create_user(username=username, password="TestPassword123!")
    UserRole.objects.create(user=user, clinic=clinic, role=Role.FRONT_DESK)
    return user


def _extra_nurse(clinic, username):
    user = User.objects.create_user(username=username, password="TestPassword123!")
    UserRole.objects.create(user=user, clinic=clinic, role=Role.PERAWAT)
    return user


def test_overlap_for_same_person_rejected(clinic, supervisor, kasir, kasir2, perawat, perawat_b):
    create_break(
        clinic,
        supervisor=supervisor,
        user=kasir,
        date=_today(),
        break_type=BreakType.MAKAN,
        start_at=_dt(13),
        end_at=_dt(14),
    )
    assert has_overlap(kasir, _dt(13, 30), _dt(14, 30)) is True
    with pytest.raises(ValidationError) as exc:
        create_break(
            clinic,
            supervisor=supervisor,
            user=kasir,
            date=_today(),
            break_type=BreakType.IBADAH,
            start_at=_dt(13, 30),
            end_at=_dt(14, 30),
        )
    assert "bertabrakan" in " ".join(exc.value.messages).lower()


def test_end_before_start_rejected(clinic, supervisor, kasir, kasir2, perawat, perawat_b):
    with pytest.raises(ValidationError):
        create_break(
            clinic,
            supervisor=supervisor,
            user=kasir,
            date=_today(),
            break_type=BreakType.MAKAN,
            start_at=_dt(14),
            end_at=_dt(13),
        )


def test_minimum_staffing_warning_requires_override(clinic, supervisor, kasir, perawat, perawat_b):
    # Hanya satu front desk aktif -> menjadwalkan istirahat melanggar minimum 1
    with pytest.raises(ValidationError) as exc:
        create_break(
            clinic,
            supervisor=supervisor,
            user=kasir,
            date=_today(),
            break_type=BreakType.MAKAN,
            start_at=_dt(13),
            end_at=_dt(14),
        )
    assert "minimum" in " ".join(exc.value.messages).lower()

    schedule, warnings = create_break(
        clinic,
        supervisor=supervisor,
        user=kasir,
        date=_today(),
        break_type=BreakType.MAKAN,
        start_at=_dt(13),
        end_at=_dt(14),
        staffing_override_reason="Supervisor menggantikan sementara di front desk",
    )
    assert warnings and schedule.staffing_override_reason


def test_no_warning_when_enough_staff(clinic, supervisor, kasir, kasir2, perawat, perawat_b):
    schedule, warnings = create_break(
        clinic,
        supervisor=supervisor,
        user=kasir,
        date=_today(),
        break_type=BreakType.MAKAN,
        start_at=_dt(13),
        end_at=_dt(14),
    )
    assert warnings == []
    assert schedule.duration_minutes == 60


def test_configurable_minimum(clinic, supervisor, kasir, kasir2, perawat, perawat_b):
    ClinicConfig.set(clinic, "break.min_active_front_desk", 2)
    warnings = staffing_warnings(clinic, _dt(13), _dt(14))
    assert warnings == []  # belum ada yang istirahat, 2 front desk aktif
    create_break(
        clinic,
        supervisor=supervisor,
        user=kasir,
        date=_today(),
        break_type=BreakType.MAKAN,
        start_at=_dt(13),
        end_at=_dt(14),
        staffing_override_reason="Uji konfigurasi",
    )
    assert staffing_warnings(clinic, _dt(13, 15), _dt(13, 45))


def test_cancel_requires_reason(clinic, supervisor, kasir, kasir2, perawat, perawat_b):
    schedule, _ = create_break(
        clinic,
        supervisor=supervisor,
        user=kasir,
        date=_today(),
        break_type=BreakType.IBADAH,
        start_at=_dt(15),
        end_at=_dt(15, 30),
    )
    with pytest.raises(ValidationError):
        cancel_break(schedule, supervisor=supervisor, reason="")
    cancel_break(schedule, supervisor=supervisor, reason="Jadwal digeser")
    schedule.refresh_from_db()
    assert schedule.status == BreakStatus.BATAL


def test_update_detects_overlap(clinic, supervisor, kasir, kasir2, perawat, perawat_b):
    first, _ = create_break(
        clinic, supervisor=supervisor, user=kasir, date=_today(),
        break_type=BreakType.MAKAN, start_at=_dt(13), end_at=_dt(14),
    )
    second, _ = create_break(
        clinic, supervisor=supervisor, user=kasir, date=_today(),
        break_type=BreakType.IBADAH, start_at=_dt(16), end_at=_dt(16, 30),
    )
    with pytest.raises(ValidationError):
        update_break(second, supervisor=supervisor, start_at=_dt(13, 30), end_at=_dt(14, 30))
