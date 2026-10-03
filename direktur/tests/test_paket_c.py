"""Paket C tahap 2: pemeriksa task, verifikasi oleh Direktur Utama / Owner, laporan progres PIC.

Aturan matriks wewenang: pekerjaan yang dikerjakan sendiri oleh Direktur Operasional diverifikasi
Direktur Utama. Di aplikasi, Dirut dan Owner sama-sama berperan OWNER (akun jean dan yohanes).
"""
from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import (
    ActionItemStatus,
    Attachment,
    Clinic,
    ReviewBy,
    TaskAssignmentStatus,
    TaskAudienceType,
    TaskEvent,
    TaskEventType,
)
from core.photos import can_view_attachment
from core.task_services import (
    can_review_assignment,
    close_task,
    confirm_assignment,
    create_task,
    report_progress,
    request_revision,
    submit_assignment,
    update_task,
)
from notifications.models import Notification
from owner.services import recent_achievements, verification_queue

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


from core.tests.test_foto import _png  # noqa: E402


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


@pytest.fixture
def people(jemur):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM),
        "yohanes": _user(jemur, "yohanes", Role.OWNER),
        "jean": _user(jemur, "jean", Role.OWNER),
        "heni": _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT, Role.STAF),
        "yani": _user(jemur, "yani", Role.PERAWAT, Role.STAF),
    }


def _task(clinic, actor, title, to, **kw):
    return create_task(clinic=clinic, actor=actor, title=title, audience_type=TaskAudienceType.USER,
                       user_ids=[to.pk], **kw)


def test_directors_own_task_is_verified_by_dirut(people, jemur):
    h, y, j = people["hansen"], people["yohanes"], people["jean"]
    item = _task(jemur, y, "Susun SOP limbah", h)
    assert item.review_by == ReviewBy.DIREKTUR and item.reviewed_by_dirut  # dihitung dari penerima
    a = item.task_assignments.get()
    submit_assignment(a, user=h, note="SOP diunggah ke Drive")
    # Direktur tidak bisa memverifikasi pekerjaannya sendiri; koordinator juga tidak.
    assert not can_review_assignment(a, h) and not can_review_assignment(a, people["heni"])
    assert can_review_assignment(a, y) and can_review_assignment(a, j)
    with pytest.raises(PermissionDenied):
        confirm_assignment(a, reviewer=people["heni"])
    # Notifikasi ke Owner/Dirut, bukan ke Direktur.
    assert {n.user.username for n in Notification.objects.filter(type_code="TASK_SUBMITTED")} == {"yohanes", "jean"}
    request_revision(a, reviewer=j, note="Tambahkan jadwal jemput vendor")
    assert Notification.objects.filter(user=h, type_code="TASK_REVISION").exists()
    submit_assignment(a, user=h, note="Jadwal jemput Selasa dan Jumat ditambahkan")
    confirm_assignment(a, reviewer=j)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI
    assert Notification.objects.filter(user=h, type_code="TASK_CONFIRMED").exists()


def test_director_cannot_close_own_task_directly(people, jemur):
    h = people["hansen"]
    item = _task(jemur, h, "Rapikan arsip", h)
    with pytest.raises(ValidationError):
        close_task(item, actor=h, note="beres")
    other = _task(jemur, h, "Cek APAR", people["yani"])
    close_task(other, actor=h, note="sudah dicek bersama")
    assert other.status == ActionItemStatus.SELESAI


def test_staff_task_keeps_director_as_reviewer_unless_changed(people, jemur):
    h, y = people["hansen"], people["yohanes"]
    item = _task(jemur, h, "Ganti lampu lobi", people["yani"])
    a = item.task_assignments.get()
    assert not item.reviewed_by_dirut
    submit_assignment(a, user=people["yani"], note="lampu diganti")
    assert can_review_assignment(a, h) and not can_review_assignment(a, y)
    assert Notification.objects.filter(user=h, type_code="TASK_SUBMITTED").exists()
    assert not Notification.objects.filter(user=y, type_code="TASK_SUBMITTED").exists()
    update_task(item, actor=h, status="BARU", priority="TINGGI", due_at=None, progress_note="",
                review_by=ReviewBy.DIRUT)
    item.refresh_from_db()
    assert item.reviewed_by_dirut and can_review_assignment(a, y) and not can_review_assignment(a, h)
    with pytest.raises(ValidationError):
        update_task(item, actor=h, status="BARU", priority="SEDANG", due_at=None, progress_note="",
                    review_by="SIAPA")


def test_owner_verifies_from_task_detail_and_dashboard(client, people, jemur):
    h, j = people["hansen"], people["jean"]
    item = _task(jemur, people["yohanes"], "Evaluasi alur pendaftaran", h)
    a = item.task_assignments.get()
    submit_assignment(a, user=h, note="Alur baru diuji 2 hari")
    client.force_login(j)
    dash = client.get(reverse("owner:dashboard")).content.decode()
    assert 'id="menunggu-verifikasi"' in dash and "Evaluasi alur pendaftaran" in dash and "Alur baru diuji" in dash
    assert [r["item"] for r in verification_queue(j)] == [item] and verification_queue(h) == []
    page = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "Pemeriksa: Direktur Utama / Owner" in page and "Konfirmasi selesai" in page
    # Owner tetap tidak bisa mengubah atau menutup task.
    client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "selesai", "catatan": "x"})
    client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "catatan", "catatan": "Bagus, lanjut"})
    assert TaskEvent.objects.filter(action_item=item, event_type=TaskEventType.COMMENT, actor=j).exists()
    client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "konfirmasi", "assignment": a.pk})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and a.reviewer == j
    dash = client.get(reverse("owner:dashboard")).content.decode()
    assert 'id="menunggu-verifikasi"' not in dash and "Capaian 7 hari terakhir" in dash
    assert recent_achievements(j)[0]["reviewers"] == "Jean"
    # Direktur melihat pemeriksanya dan tidak mendapat tombol tutup langsung.
    other = _task(jemur, people["yohanes"], "Atur ulang rak", h)
    client.force_login(h)
    page = client.get(reverse("direktur:task_detail", args=[other.pk])).content.decode()
    assert "Tandai selesai tanpa menunggu penerima" not in page and "Pemeriksa: Direktur Utama / Owner" in page


def test_progress_report_and_required_evidence(client, people, jemur):
    h, yani = people["hansen"], people["yani"]
    item = _task(jemur, h, "Pengolahan limbah", yani)
    a = item.task_assignments.get()
    with pytest.raises(PermissionDenied):
        report_progress(a, user=people["heni"], note="x")
    with pytest.raises(ValidationError):
        report_progress(a, user=yani, note=" ")
    client.force_login(yani)
    home = client.get(reverse("core:dashboard")).content.decode()
    assert "Lapor progres" in home and "Catatan bukti" in home
    client.post(reverse("core:assignment_progress", args=[a.pk]),
                {"catatan": "Vendor dihubungi, jemput Senin", "foto": _png(), "next": reverse("core:dashboard")})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.IN_PROGRESS
    event = TaskEvent.objects.get(action_item=item, event_type=TaskEventType.PROGRESS)
    photo = Attachment.objects.get(entity_type="taskevent", entity_id=event.pk)
    assert can_view_attachment(yani, photo) and can_view_attachment(h, photo)
    outsider = _user(Clinic.objects.create(code="JC", name="Citraland"), "regita", Role.STAF)
    assert not can_view_attachment(outsider, photo)
    home = client.get(reverse("core:dashboard")).content.decode()
    assert "Progres terakhir" in home and "Vendor dihubungi" in home
    # Ajukan selesai tanpa catatan bukti ditolak.
    client.post(reverse("core:assignment_submit", args=[a.pk]), {"next": reverse("core:dashboard")})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.IN_PROGRESS
    client.post(reverse("core:assignment_submit", args=[a.pk]), {"catatan": "Limbah 3 kg dijemput"})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.SUBMITTED
    with pytest.raises(ValidationError):
        report_progress(a, user=yani, note="sesudah diajukan")
    client.force_login(h)
    page = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "Laporan progres" in page and "Vendor dihubungi, jemput Senin" in page
    assert f'{reverse("core:attachment", args=[photo.pk])}' in page
