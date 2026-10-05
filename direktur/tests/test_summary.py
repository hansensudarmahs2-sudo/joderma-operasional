"""Fase 5 redefinisi peran: summary harian Direktur ke Owner dan lonceng notifikasi."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import ActionItem, ActionItemStatus, Clinic, local_today
from direktur import services
from direktur import summary as daily
from direktur.management.commands.seed_audit_direktur import seed
from direktur.models import AuditItem, CheckResult, DailySummary, Decider
from notifications.models import Notification
from owner import services as owner_services

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="citraland", name="Citraland")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def owners(jemur):
    return [_user(jemur, "yohanes", Role.OWNER), _user(jemur, "jean", Role.OWNER)]


def _section(content, title):
    return next(s for s in content["sections"] if s["title"] == title)


def test_compose_collects_the_four_parts(jemur, citraland, hansen, owners):
    seed()
    services.record_check(item=AuditItem.objects.get(code="harian-limbah"), clinic=jemur, actor=hansen,
                          result=CheckResult.TEMUAN, note="Kotak pertama penuh")
    d = services.create_decision(actor=hansen, title="Jam briefing", decider=Decider.DIREKTUR_OPERASIONAL)
    services.settle_decision(d, actor=hansen, decision_text="13.45–13.50", is_policy=True,
                             decided_on=local_today())
    services.create_decision(actor=hansen, title="Imbalan koordinator", decider=Decider.OWNER)
    done = ActionItem.objects.create(clinic=citraland, title="Rapikan rak", source_type="manual",
                                     status=ActionItemStatus.SELESAI)
    req = owner_services.create_request(actor=owners[0], title="Evaluasi harga paket",
                                        target_date=local_today() + dt.timedelta(days=5))

    content = daily.compose(hansen)
    checklist = _section(content, "Checklist Direktur")
    jemur_line = next(i for i in checklist["items"] if i["text"].startswith("Jemur Andayani"))
    assert jemur_line["tag"] == "1 temuan" and "belum dicek" in jemur_line["meta"]
    assert any(i["text"].startswith("Temuan") and i["meta"] == "Kotak pertama penuh" for i in checklist["items"])
    assert any(i["text"].startswith("Citraland") for i in checklist["items"])

    decisions = _section(content, "Keputusan dan task hari ini")
    texts = [i["text"] for i in decisions["items"]]
    assert "Ditetapkan: Jam briefing" in texts and "Dicatat: Imbalan koordinator" in texts
    assert f"Selesai: {done.title}" in texts
    # Task tindak lanjut temuan tidak diulang; temuannya sudah ada di bagian Checklist Direktur.
    assert not any(t.startswith("Task baru: Temuan") for t in texts)

    requests = _section(content, "Permintaan dan temuan Owner")
    assert [i["text"] for i in requests["items"]] == [req.title]
    assert requests["items"][0]["tag"] == "Menunggu Direktur"


def test_send_then_resend_updates_one_summary(jemur, hansen, owners):
    first = daily.send_summary(actor=hansen, note="Hari tenang.")
    assert first.send_count == 1 and first.note == "Hari tenang."
    assert Notification.objects.filter(type_code="summary_harian").count() == 2  # yohanes dan jean
    assert not Notification.objects.filter(user=hansen).exists()
    second = daily.send_summary(actor=hansen, note="Ada tambahan: kas selisih.")
    assert second.pk == first.pk and second.send_count == 2 and second.note.startswith("Ada tambahan")
    assert DailySummary.objects.count() == 1
    for owner in owners:
        notes = Notification.objects.filter(user=owner, type_code="summary_harian")
        assert notes.count() == 1 and "diperbarui" in notes.get().title
        assert notes.get().url == f"{reverse('owner:summary')}?tanggal={local_today().isoformat()}"
    assert AuditEvent.objects.filter(entity_type="dailysummary").count() == 2


def test_resend_after_read_makes_new_notification(jemur, hansen, owners):
    daily.send_summary(actor=hansen)
    Notification.objects.update(read_at=timezone.now())
    daily.send_summary(actor=hansen)
    assert Notification.objects.filter(user=owners[0], read_at__isnull=True).count() == 1


def test_snapshot_does_not_change_after_sending(jemur, hansen, owners):
    daily.send_summary(actor=hansen)
    ActionItem.objects.create(clinic=jemur, title="Task sesudah kirim", source_type="manual")
    summary = DailySummary.objects.get()
    assert "Task sesudah kirim" not in str(summary.content)


def test_only_director_sends(jemur, owners):
    staf = _user(jemur, "yani", Role.PERAWAT)
    for user in (owners[0], staf):
        with pytest.raises(PermissionDenied):
            daily.send_summary(actor=user)
    assert not DailySummary.objects.exists()


def test_checklist_page_button_and_http_send(client, jemur, hansen, owners):
    seed()
    client.force_login(hansen)
    page = client.get(reverse("direktur:checklist")).content.decode()
    assert "Simpan dan kirim summary ke Owner" in page and "belum dikirim" in page
    assert "Pratinjau isi yang disusun otomatis" in page
    response = client.post(reverse("direktur:summary_send"),
                           {"catatan": "Besok cek limbah Citraland.", "next": "/direktur/checklist/?siklus=HARIAN"})
    assert response["Location"] == "/direktur/checklist/?siklus=HARIAN#summary-owner"
    page = client.get(reverse("direktur:checklist")).content.decode()
    assert "Besok cek limbah Citraland." in page and "terkirim pukul" in page
    client.force_login(owners[1])
    body = client.get(reverse("owner:summary")).content.decode()
    assert "Besok cek limbah Citraland." in body and "Checklist Direktur" in body


def test_send_rejects_outside_next(client, jemur, hansen):
    client.force_login(hansen)
    response = client.post(reverse("direktur:summary_send"), {"next": "https://contoh.invalid/"})
    assert response["Location"] == reverse("direktur:checklist") + "#summary-owner"


def test_send_forbidden_for_others(client, jemur, owners):
    for user in (owners[0], _user(jemur, "heni", Role.SUPERVISOR), _user(jemur, "superadmin", Role.ADMIN)):
        client.force_login(user)
        assert client.post(reverse("direktur:summary_send"), {"catatan": "x"}).status_code == 403
    assert not DailySummary.objects.exists()


def test_director_menu_has_summary(client, hansen):
    client.force_login(hansen)
    body = client.get(reverse("direktur:overview")).content.decode()
    assert reverse("owner:summary") in body.split('id="main-nav"', 1)[1]


# --- Lonceng ---------------------------------------------------------------------


def test_bell_shows_red_count(client, jemur, owners):
    owner = owners[0]
    client.force_login(owner)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert 'class="bell"' in body and "bell-count" not in body and 'aria-label="Notifikasi"' in body
    for i in range(3):
        Notification.objects.create(user=owner, type_code="x", title=f"N{i}")
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert '<span class="bell-count">3</span>' in body and "3 belum dibaca" in body
    Notification.objects.bulk_create([Notification(user=owner, type_code="x", title="N") for _ in range(100)])
    assert '<span class="bell-count">99+</span>' in client.get(reverse("owner:dashboard")).content.decode()


def test_summary_can_be_downloaded_as_pdf(client, jemur, hansen, owners):
    """5 Okt 2026: tombol Unduh PDF di Summary Harian (Owner dan Direktur)."""
    seed()
    services.record_check(item=AuditItem.objects.get(code="harian-limbah"), clinic=jemur, actor=hansen,
                          result=CheckResult.TEMUAN, note="Kotak penuh → minta jemput 😊\nbaris kedua")
    item = daily.send_summary(actor=hansen, note="Catatan: tunggu vendor ≤ 2 hari")
    day = item.date.isoformat()
    for who in (owners[0], hansen):
        client.force_login(who)
        page = client.get(reverse("owner:summary"), {"tanggal": day}).content.decode()
        assert f'{reverse("owner:summary_pdf")}?tanggal={day}' in page and "Unduh PDF" in page
        resp = client.get(reverse("owner:summary_pdf"), {"tanggal": day})
        assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
        assert resp["Content-Disposition"] == f'attachment; filename="summary-harian-{day}.pdf"'
        assert resp.content.startswith(b"%PDF") and len(resp.content) > 2000
    other = (item.date - dt.timedelta(days=3)).isoformat()
    assert client.get(reverse("owner:summary_pdf"), {"tanggal": other}).status_code == 404
    staff = _user(jemur, "yani", Role.PERAWAT, Role.STAF)
    client.force_login(staff)
    assert client.get(reverse("owner:summary_pdf"), {"tanggal": day}).status_code == 403
