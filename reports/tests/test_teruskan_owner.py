"""Teruskan ke Owner menjadi permintaan keputusan; Owner diberi tahu (7 Okt 2026)."""
import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic, local_today
from direktur import services as direktur
from direktur.models import Decider, Decision
from notifications.models import Notification
from reports import inbox, triage
from reports.models import ForwardTo, InboxTriage
from reports.services import create_laporan

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def people(jemur):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen"),
        "yohanes": _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes"),
        "jean": _user(jemur, "jean", Role.OWNER, display_name="Jean"),
        "yani": _user(jemur, "yani", Role.STAF, display_name="Yani"),
    }


def test_owner_decision_notifies_all_owners(jemur, people):
    h = people["hansen"]
    d = direktur.create_decision(actor=h, title="Tambah anggaran tissue", decider=Decider.OWNER, clinic=jemur,
                                 needed_by=local_today() + dt.timedelta(days=3))
    for owner in (people["yohanes"], people["jean"]):
        n = Notification.objects.get(user=owner, type_code="DECISION_REQUESTED")
        assert n.title == "Direktur Operasional meminta keputusan: Tambah anggaran tissue"
        assert n.body == f"Jemur Andayani · perlu diputuskan sebelum {d.needed_by:%d/%m/%Y}"
        assert n.url == reverse("owner:decision", args=[d.pk])
    assert not Notification.objects.filter(user=h, type_code="DECISION_REQUESTED").exists()


def test_dirut_decider_notifies_and_other_deciders_do_not(jemur, people):
    h = people["hansen"]
    direktur.create_decision(actor=h, title="Strategis", decider=Decider.DIRUT)
    n = Notification.objects.get(user=people["yohanes"], type_code="DECISION_REQUESTED")
    assert n.body == "lintas cabang · tanpa tenggat"
    for decider in (Decider.RAPAT_BERSAMA, Decider.PJ_PELAYANAN, Decider.DIREKTUR_OPERASIONAL):
        direktur.create_decision(actor=h, title=f"Bukan Owner {decider}", decider=decider, clinic=jemur)
    assert Notification.objects.filter(type_code="DECISION_REQUESTED").count() == 2


def test_forward_to_owner_creates_decision(jemur, people):
    h = people["hansen"]
    laporan = create_laporan(clinic=jemur, user=people["yani"], title="Tissue habis tiap Sabtu",
                             description="Sudah 3 minggu berturut-turut.")
    row = inbox.find_row(h, inbox.SOURCE_LAPORAN, laporan.pk)
    t = triage.forward(row, actor=h, to=ForwardTo.DIRUT, note="perlu tambahan anggaran")
    d = Decision.objects.get()
    assert (d.decider, d.title, d.clinic, d.created_by) == (Decider.OWNER, "Tissue habis tiap Sabtu", jemur, h)
    assert "Sudah 3 minggu berturut-turut." in d.background
    assert f"Rujukan: L-{laporan.pk} ({row['kind_label']}, dari {row['reporter']})" in d.background
    assert "Catatan Direktur: perlu tambahan anggaran" in d.background
    assert InboxTriage.objects.get(pk=t.pk).decision == d
    assert Notification.objects.filter(user=people["yohanes"], type_code="DECISION_REQUESTED").exists()


def test_forward_elsewhere_creates_no_decision(jemur, people):
    h = people["hansen"]
    laporan = create_laporan(clinic=jemur, user=people["yani"], title="Harga obat naik")
    t = triage.forward(inbox.find_row(h, inbox.SOURCE_LAPORAN, laporan.pk), actor=h, to=ForwardTo.APOTEKER)
    assert t.decision is None and not Decision.objects.exists()


def test_forward_twice_to_owner_reuses_waiting_decision(jemur, people):
    h = people["hansen"]
    laporan = create_laporan(clinic=jemur, user=people["yani"], title="Tissue habis")
    row = inbox.find_row(h, inbox.SOURCE_LAPORAN, laporan.pk)
    triage.forward(row, actor=h, to=ForwardTo.DIRUT, note="satu")
    triage.forward(row, actor=h, to=ForwardTo.DIRUT, note="dua")
    assert Decision.objects.count() == 1
    for owner in (people["yohanes"], people["jean"]):
        assert Notification.objects.filter(user=owner, type_code="DECISION_REQUESTED").count() == 1


def test_retriage_elsewhere_cancels_waiting_owner_decision(jemur, people):
    from owner import services as owner_services

    h = people["hansen"]
    laporan = create_laporan(clinic=jemur, user=people["yani"], title="Tissue habis")
    row = inbox.find_row(h, inbox.SOURCE_LAPORAN, laporan.pk)
    first = triage.forward(row, actor=h, to=ForwardTo.DIRUT).decision
    t = triage.forward(row, actor=h, to=ForwardTo.APOTEKER)
    first.refresh_from_db()
    assert first.status == "DIBATALKAN" and "Pilahan Inbox diubah" in first.decision_text
    assert t.decision is None
    assert first.pk not in [r["decision"].pk for r in owner_services.decisions_awaiting(people["yohanes"])]


def test_retriage_does_not_cancel_decided_owner_decision(jemur, people):
    from owner import services as owner_services

    h = people["hansen"]
    laporan = create_laporan(clinic=jemur, user=people["yani"], title="Tissue habis")
    row = inbox.find_row(h, inbox.SOURCE_LAPORAN, laporan.pk)
    first = triage.forward(row, actor=h, to=ForwardTo.DIRUT).decision
    owner_services.decide(first, actor=people["yohanes"], verdict="setuju")
    triage.forward(row, actor=h, to=ForwardTo.APOTEKER)
    first.refresh_from_db()
    assert first.status == "DITETAPKAN"


def test_forward_message_to_owner_says_owner_notified(client, jemur, people):
    client.force_login(people["hansen"])
    laporan = create_laporan(clinic=jemur, user=people["yani"], title="Tissue habis")
    url = reverse("reports:inbox_triage", args=[inbox.SOURCE_LAPORAN, laporan.pk])
    body = client.post(url, {"aksi": "teruskan", "ke": ForwardTo.DIRUT, "catatan": "perlu anggaran"},
                       follow=True).content.decode()
    assert "Diteruskan ke Owner sebagai permintaan keputusan; Owner sudah diberi tahu." in body
    assert "Dicatat sebagai diteruskan" not in body

    lain = create_laporan(clinic=jemur, user=people["yani"], title="Harga obat naik")
    url = reverse("reports:inbox_triage", args=[inbox.SOURCE_LAPORAN, lain.pk])
    body = client.post(url, {"aksi": "teruskan", "ke": ForwardTo.APOTEKER, "catatan": "cek"},
                       follow=True).content.decode()
    assert "Dicatat sebagai diteruskan; tetap dipantau di tab Dipantau." in body
    assert "Owner sudah diberi tahu" not in body
