"""Fixture bersama untuk seluruh test suite. Hanya data sintetis."""
from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from accounts.models import Capability, Role, User, UserCapability, UserRole
from checklists.models import ChecklistArea, ChecklistTemplate, ChecklistTemplateItem, InputType
from core.models import Clinic
from core.services import get_or_create_day
from nurses.models import NurseEligibility, ProcedureCategory


@pytest.fixture
def clinic(db):
    return Clinic.objects.create(
        code="test-cabang", name="JoDerma Test", open_time="12:00", close_time="21:00"
    )


def _make_user(clinic, username, roles, caps=()):
    user = User.objects.create_user(
        username=username, password="TestPassword123!", display_name=username.title()
    )
    for role in roles:
        UserRole.objects.create(user=user, clinic=clinic, role=role)
    for cap in caps:
        UserCapability.objects.create(user=user, capability=cap)
    return user


@pytest.fixture
def supervisor(clinic):
    return _make_user(clinic, "supervisor", [Role.SUPERVISOR], [Capability.CASH_VIEW_AMOUNTS])


@pytest.fixture
def kasir(clinic):
    return _make_user(clinic, "kasir", [Role.FRONT_DESK, Role.STAF])


@pytest.fixture
def kasir2(clinic):
    return _make_user(clinic, "kasir2", [Role.FRONT_DESK])


@pytest.fixture
def perawat(clinic):
    return _make_user(clinic, "perawat1", [Role.PERAWAT, Role.STAF])


@pytest.fixture
def perawat_b(clinic):
    return _make_user(clinic, "perawat2", [Role.PERAWAT])


@pytest.fixture
def staf(clinic):
    return _make_user(clinic, "staf", [Role.STAF])


@pytest.fixture
def admin_teknis(clinic):
    return _make_user(clinic, "adminteknis", [Role.ADMIN])


@pytest.fixture
def template(clinic):
    tpl = ChecklistTemplate.objects.create(
        clinic=clinic, name="Ruang konsultasi", area=ChecklistArea.RUANG_KONSULTASI, version=1
    )
    ChecklistTemplateItem.objects.create(
        template=tpl, label="Alat lengkap", category="Alat", required=True, sort_order=1
    )
    ChecklistTemplateItem.objects.create(
        template=tpl,
        label="Sarung tangan",
        category="BHP",
        required=True,
        input_type=InputType.KUANTITAS,
        min_quantity=20,
        unit="pasang",
        sort_order=2,
    )
    ChecklistTemplateItem.objects.create(
        template=tpl, label="Item opsional", category="Lain", required=False, sort_order=3
    )
    return tpl


@pytest.fixture
def day(clinic, template, supervisor):
    obj, _ = get_or_create_day(clinic, user=supervisor)
    return obj


@pytest.fixture
def kategori(clinic):
    return ProcedureCategory.objects.create(clinic=clinic, code="laser", name="Laser")


@pytest.fixture
def eligible_nurses(kategori, perawat, perawat_b):
    NurseEligibility.objects.create(nurse=perawat, category=kategori)
    NurseEligibility.objects.create(nurse=perawat_b, category=kategori)
    return [perawat, perawat_b]


@pytest.fixture
def now():
    return timezone.now()


@pytest.fixture
def today():
    return timezone.localtime(timezone.now()).date()
