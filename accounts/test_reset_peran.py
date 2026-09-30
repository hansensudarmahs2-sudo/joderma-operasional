"""Reset peran ke default: definisi standar, pratinjau, dan penerapan."""
from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from django.urls import reverse

from accounts.models import PicAssignment, PicFunction, Role, User, UserRole
from accounts.peran_standar import apply_plan, build_plan
from core.models import ActionItem, Clinic

pytestmark = pytest.mark.django_db


@pytest.fixture
def cabang(db):
    jmr = Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")
    ctl = Clinic.objects.create(code="JC", name="Joderma Citraland")
    return jmr, ctl


def _user(name, clinic, *roles, password="PasswordLama123!"):
    u = User.objects.create_user(username=name, password=password)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def test_reset_creates_missing_fixes_roles_and_keeps_passwords_and_data(cabang):
    jmr, ctl = cabang
    desy = _user("desy", jmr, Role.PERAWAT, Role.SUPERVISOR)  # SUPERVISOR bukan peran default Desy
    PicAssignment.objects.create(user=desy, clinic=jmr, function=PicFunction.CLEANLINESS, starts_on="2026-09-01")
    regita = _user("regita", jmr, Role.PERAWAT)  # ejaan lama, cabang lama
    hansen = _user("hansen1", jmr, Role.AOM, Role.ADMIN)
    stranger = _user("AOM_HS", jmr, Role.AOM)
    task = ActionItem.objects.create(clinic=jmr, title="Task Desy", owner=desy)

    plans, _ = build_plan()
    assert UserRole.objects.filter(user=desy, role=Role.SUPERVISOR).exists()  # pratinjau tidak menulis
    apply_plan(plans)

    desy.refresh_from_db()
    assert desy.check_password("PasswordLama123!")
    assert not UserRole.objects.filter(user=desy, role=Role.SUPERVISOR).exists()
    assert set(UserRole.objects.filter(user=desy).values_list("role", flat=True)) == {
        Role.PERAWAT, Role.FRONT_DESK, Role.ONLINE, Role.PIC, Role.STAF}
    assert not PicAssignment.objects.get(user=desy, function=PicFunction.CLEANLINESS).active
    assert set(PicAssignment.objects.filter(user=desy, active=True).values_list("function", flat=True)) == {
        PicFunction.CASHIER, PicFunction.ONLINE}
    regita.refresh_from_db()
    assert regita.username == "regitta"
    assert set(UserRole.objects.filter(user=regita).values_list("clinic__code", flat=True)) == {"JC"}
    assert set(UserRole.objects.filter(user=hansen).values_list("role", flat=True)) == {Role.AOM}
    assert set(UserRole.objects.filter(user=stranger).values_list("role", flat=True)) == {Role.AOM}
    jean = User.objects.get(username="jean")
    assert jean.check_password("klinik123") and jean.must_change_password
    assert set(UserRole.objects.filter(user=jean).values_list("role", flat=True)) == {Role.OWNER}
    assert User.objects.get(username="yohanes").has_role(Role.OWNER)
    task.refresh_from_db()
    assert task.owner_id == desy.pk
    # Kedua kali: tidak ada yang berubah.
    plans, _ = build_plan()
    assert not any(p.changed for p in plans)


def test_reset_page_preview_and_apply(client, cabang):
    jmr, _ = cabang
    admin = _user("superadmin", jmr, Role.ADMIN)
    client.force_login(admin)
    body = client.get(reverse("accounts:role_reset")).content.decode()
    assert "Yang akan berubah" in body and "jean" in body
    assert not User.objects.filter(username="jean").exists()
    client.post(reverse("accounts:role_reset"), {})  # tanpa konfirmasi
    assert not User.objects.filter(username="jean").exists()
    client.post(reverse("accounts:role_reset"), {"konfirmasi": "1"})
    assert User.objects.filter(username="jean").exists()
    assert "Sesuai default" in client.get(reverse("accounts:role_reset")).content.decode()


def test_reset_page_permissions(client, cabang):
    jmr, _ = cabang
    client.force_login(_user("hansen1", jmr, Role.AOM))
    assert client.get(reverse("accounts:role_reset")).status_code == 200
    for name, role in (("owner1", Role.OWNER), ("staf1", Role.STAF), ("ks1", Role.SUPERVISOR)):
        client.force_login(_user(name, jmr, role))
        assert client.get(reverse("accounts:role_reset")).status_code == 403
        assert client.post(reverse("accounts:role_reset"), {"konfirmasi": "1"}).status_code == 403
    assert not User.objects.filter(username="jean").exists()


def test_command_matches_button(cabang):
    out = io.StringIO()
    call_command("seed_staf_cabang", dry_run=True, stdout=out)
    assert "jean:" in out.getvalue() and not User.objects.filter(username="jean").exists()
    call_command("seed_staf_cabang", prune=True, stdout=io.StringIO())
    plans, _ = build_plan()
    assert not any(p.changed for p in plans)
