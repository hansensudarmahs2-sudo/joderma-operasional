"""Pengaturan klinik: nama, alamat, nomor HP, jam, DPJ, APJ."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import Clinic

pytestmark = pytest.mark.django_db


def _user(clinic, name, role):
    u = User.objects.create_user(username=name, password="TestPassword123!")
    UserRole.objects.create(user=u, clinic=clinic, role=role)
    return u


def _form(clinic, **kw):
    data = {"klinik": clinic.pk, "nama": clinic.name, "alamat": "Jl. Jemur Andayani XVIII No.34A",
            "hp": "0812-0000-0000", "buka": "14:00", "tutup": "22:00",
            "dpj": "dr. Yohanes Widjaja, Sp.DVE", "apj": "apt. Veronika Elvira Manggo, S.Farm."}
    data.update(kw)
    return data


def test_director_edits_profile_with_audit(client, clinic):
    client.force_login(_user(clinic, "direktur", Role.AOM))
    assert client.post(reverse("core:clinic_profile"), _form(clinic)).status_code == 302
    clinic.refresh_from_db()
    assert clinic.open_time == dt.time(14, 0) and clinic.close_time == dt.time(22, 0)
    assert clinic.dpj_name.startswith("dr. Yohanes") and clinic.phone == "0812-0000-0000"
    assert AuditEvent.objects.filter(entity_type="clinic", entity_id=str(clinic.pk)).exists()


def test_invalid_hours_rejected(client, clinic):
    client.force_login(_user(clinic, "admin1", Role.ADMIN))
    client.post(reverse("core:clinic_profile"), _form(clinic, buka="22:00", tutup="14:00"))
    clinic.refresh_from_db()
    assert clinic.open_time == dt.time(12, 0)


def test_owner_reads_staff_forbidden(client, clinic):
    owner = _user(clinic, "owner1", Role.OWNER)
    client.force_login(owner)
    body = client.get(reverse("core:clinic_profile")).content.decode()
    assert "Anda hanya dapat membaca" in body and 'name="dpj"' not in body
    assert client.post(reverse("core:clinic_profile"), _form(clinic)).status_code == 403
    client.force_login(_user(clinic, "staf1", Role.STAF))
    assert client.get(reverse("core:clinic_profile")).status_code == 403


def test_data_migration_sets_jemur_hours():
    from importlib import import_module

    mod = import_module("core.migrations.0005_clinic_profile_data")
    jmr = Clinic.objects.create(code="jemur-andayani", name="Jemur", open_time="12:00", close_time="21:00")
    ctl = Clinic.objects.create(code="citraland", name="Citraland", open_time="12:00", close_time="21:00")
    from django.apps import apps

    mod.forward(apps, None)
    jmr.refresh_from_db()
    ctl.refresh_from_db()
    assert jmr.open_time == dt.time(14, 0) and jmr.close_time == dt.time(22, 0)
    assert ctl.open_time == dt.time(12, 0)
    assert jmr.apj_name.startswith("apt. Veronika") and ctl.dpj_name.startswith("dr. Wisnu")
