"""Perintah rapikan_akun: buang akhiran _pic, password awal sama untuk semua."""
from __future__ import annotations

import io

import pytest
from django.core.management import call_command

from accounts.models import User
from audit.models import AuditAction, AuditEvent
from core.models import ActionItem, Clinic

pytestmark = pytest.mark.django_db


def test_renames_pic_suffix_resets_passwords_and_keeps_data():
    clinic = Clinic.objects.create(code="jemur-andayani", name="Jemur")
    desy = User.objects.create_user(username="desy_pic", password="rahasia-lama-123")
    hansen = User.objects.create_user(username="hansen1", password="lain-lagi-456")
    User.objects.create_user(username="lia", password="x-123456789012")
    User.objects.create_user(username="lia_pic", password="x-123456789012")  # bentrok, dilewati
    item = ActionItem.objects.create(clinic=clinic, title="Task untuk Desy", owner=desy)
    out = io.StringIO()
    call_command("rapikan_akun", password="klinik123", stdout=out)
    desy.refresh_from_db()
    hansen.refresh_from_db()
    assert desy.username == "desy" and desy.check_password("klinik123") and desy.must_change_password
    assert hansen.check_password("klinik123") and hansen.must_change_password
    assert User.objects.filter(username="lia_pic").exists() and "dilewati" in out.getvalue()
    item.refresh_from_db()
    assert item.owner_id == desy.pk  # data lama tetap melekat pada akun yang sama
    assert AuditEvent.objects.filter(action=AuditAction.PASSWORD_CHANGED, entity_label="desy").exists()


def test_dry_run_changes_nothing():
    User.objects.create_user(username="elvira_pic", password="rahasia-lama-123")
    call_command("rapikan_akun", dry_run=True, stdout=io.StringIO())
    user = User.objects.get(username="elvira_pic")
    assert user.check_password("rahasia-lama-123") and not user.must_change_password
