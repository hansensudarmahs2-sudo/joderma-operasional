"""9 Okt 2026: kebijakan dipilah Klinik / Apotek / Semua staf (semua staf membaca semuanya) dan kebijakan
"Hanya Owner" yang hanya terlihat dan diumumkan ke Owner dan Direktur Operasional."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic
from direktur import services as direktur
from direktur.models import Decider, Decision, PolicyGroup
from notifications.models import Notification

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


@pytest.fixture
def people(jemur):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM),
        "yohanes": _user(jemur, "yohanes", Role.OWNER),
        "yani": _user(jemur, "yani", Role.PERAWAT, Role.STAF),
        "luki": _user(jemur, "luki", Role.ASISTEN_APOTEKER, Role.STAF),
    }


def _policy(actor, title, group, owner_only=False, announce=True, decided_on=None):
    d = direktur.create_decision(actor=actor, title=title, decider=Decider.DIREKTUR_OPERASIONAL)
    return direktur.settle_decision(d, actor=actor, decision_text=f"Isi {title}", is_policy=True,
                                    policy_group=group, owner_only=owner_only, announce=announce,
                                    decided_on=decided_on)


def test_groups_shown_to_nurse_and_pharmacy_alike(client, people):
    h = people["hansen"]
    _policy(h, "Biaya racik", PolicyGroup.APOTEK)
    _policy(h, "Verifikasi identitas", PolicyGroup.KLINIK)
    _policy(h, "Izin dan sakit", PolicyGroup.SEMUA)
    for who in ("yani", "luki"):
        client.force_login(people[who])
        body = client.get(reverse("reports:policies")).content.decode()
        assert all(t in body for t in ("Biaya racik", "Verifikasi identitas", "Izin dan sakit"))
        assert body.index('id="kelompok-KLINIK"') < body.index('id="kelompok-APOTEK"') < body.index('id="kelompok-SEMUA"')
        assert "Hanya Owner" not in body
        only = client.get(reverse("reports:policies"), {"kelompok": "APOTEK"}).content.decode()
        assert "Biaya racik" in only and "Verifikasi identitas" not in only


def test_owner_only_policy_hidden_from_staff_and_not_announced(client, people):
    h = people["hansen"]
    d = _policy(h, "Pengajuan dukungan untuk dokter", PolicyGroup.KLINIK, owner_only=True)
    assert not Notification.objects.filter(user__in=[people["yani"], people["luki"]],
                                           type_code="POLICY_PUBLISHED").exists()
    assert Notification.objects.filter(user=people["yohanes"], type_code="POLICY_PUBLISHED").exists()
    client.force_login(people["yani"])
    body = client.get(reverse("reports:policies")).content.decode()
    assert "Pengajuan dukungan untuk dokter" not in body
    assert "Pengajuan dukungan" not in client.get(reverse("reports:policies"), {"kelompok": "OWNER"}).content.decode()
    for who in ("yohanes", "hansen"):
        client.force_login(people[who])
        body = client.get(reverse("reports:policies")).content.decode()
        assert "Pengajuan dukungan untuk dokter" in body and 'id="kelompok-OWNER"' in body
    assert d.owner_only


def test_bulk_insert_without_announcement_keeps_date(people):
    d = _policy(people["hansen"], "Plester waterproof", PolicyGroup.APOTEK, announce=False,
                decided_on=dt.date(2026, 9, 15))
    assert d.decided_on == dt.date(2026, 9, 15)
    assert not Notification.objects.filter(type_code="POLICY_PUBLISHED").exists()


def test_unknown_group_rejected_and_none_keeps_group(people):
    h = people["hansen"]
    d = _policy(h, "Briefing", PolicyGroup.KLINIK)
    with pytest.raises(ValidationError):
        direktur.settle_decision(d, actor=h, decision_text="x", is_policy=True, policy_group="XX")
    direktur.settle_decision(Decision.objects.get(pk=d.pk), actor=h, decision_text="Isi baru", is_policy=True)
    assert Decision.objects.get(pk=d.pk).policy_group == PolicyGroup.KLINIK


def test_director_form_sets_group_and_owner_only(client, people):
    h = people["hansen"]
    d = direktur.create_decision(actor=h, title="Diskon staf", decider=Decider.DIREKTUR_OPERASIONAL)
    client.force_login(h)
    url = reverse("direktur:decision_detail", args=[d.pk])
    assert 'name="kelompok"' in client.get(url).content.decode()
    client.post(url, {"isi": "Tidak ada diskon staf.", "kebijakan": "1", "kelompok": "SEMUA", "hanya_owner": "1"})
    d.refresh_from_db()
    assert d.is_policy and d.policy_group == PolicyGroup.SEMUA and d.owner_only
