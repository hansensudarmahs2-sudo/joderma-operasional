"""Tahap 3b: pelapor Laporan staf diberi tahu tanggapan, riwayat tampil, tanggapan bisa ditambah."""
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from notifications.models import Notification
from reports import triage
from reports.inbox import find_row
from reports.models import LaporanUpdate, ReportStatus, ReportVisibility
from reports.services import add_laporan_note, archive_laporan, change_laporan_status, create_laporan

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _laporan(clinic, user, **kw):
    return create_laporan(clinic=clinic, user=user, title="Tissue habis tiap Sabtu", description="Usul.", **kw)


def _notes(user):
    return list(Notification.objects.filter(user=user, type_code="LAPORAN_RESPONSE"))


@pytest.fixture
def aom(clinic):
    return _user(clinic, "hansen1", Role.AOM)


def test_status_change_notifies_reporter(clinic, staf, supervisor):
    laporan = _laporan(clinic, staf)
    change_laporan_status(laporan, user=supervisor, to_status=ReportStatus.UNDER_REVIEW, note="Kami cek.")
    notes = _notes(staf)
    assert len(notes) == 1
    assert notes[0].title == "Tanggapan atas laporan Anda: Tissue habis tiap Sabtu"
    assert "Ditinjau" in notes[0].body and "Kami cek." in notes[0].body
    assert notes[0].url == reverse("reports:laporan_page_detail", args=[laporan.pk])


def test_rahasia_laporan_notification_has_no_content(clinic, staf, aom):
    laporan = _laporan(clinic, staf, visibility=ReportVisibility.RAHASIA_AOM)
    change_laporan_status(laporan, user=aom, to_status=ReportStatus.UNDER_REVIEW, note="Rahasia isi")
    (n,) = _notes(staf)
    assert n.title == "Ada tanggapan pada catatan Anda"
    assert n.body == ""
    assert n.url == reverse("reports:laporan_page_detail", args=[laporan.pk])


def test_add_note_by_director(clinic, staf, aom):
    laporan = _laporan(clinic, staf)
    u = add_laporan_note(laporan, user=aom, note="  Akan kami bahas.  ")
    assert u.note == "Akan kami bahas." and u.from_status == "" and u.status == ReportStatus.OPEN
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.OPEN
    (n,) = _notes(staf)
    assert "Akan kami bahas." in n.body
    with pytest.raises(ValidationError):
        add_laporan_note(laporan, user=aom, note="   ")


def test_add_note_by_plain_staff_refused(client, clinic, staf):
    laporan = _laporan(clinic, staf)
    other = _user(clinic, "yani", Role.STAF)
    with pytest.raises(PermissionDenied):
        add_laporan_note(laporan, user=other, note="halo")
    assert LaporanUpdate.objects.filter(laporan=laporan).count() == 1  # hanya "Laporan dibuat."
    client.force_login(other)
    r = client.post(reverse("reports:laporan_page_detail", args=[laporan.pk]), {"aksi": "tanggapan", "catatan": "halo"})
    assert r.status_code == 403
    assert LaporanUpdate.objects.filter(laporan=laporan).count() == 1


def test_no_self_notification(clinic):
    sup = _user(clinic, "heni", Role.SUPERVISOR, Role.STAF)
    laporan = _laporan(clinic, sup)
    add_laporan_note(laporan, user=sup, note="Catatan sendiri")
    assert _notes(sup) == []


def test_archive_notifies(clinic, staf, aom):
    laporan = _laporan(clinic, staf)
    archive_laporan(laporan, user=aom, reason="Duplikat")
    (n,) = _notes(staf)
    assert "Diarsipkan. Alasan: Duplikat" in n.body


def test_triage_dismiss_keeps_status_and_notifies_once(clinic, staf, aom):
    laporan = _laporan(clinic, staf)
    triage.dismiss(find_row(aom, "laporan", laporan.pk), actor=aom, reason="Sudah normal")
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.OPEN
    ups = list(laporan.updates.all())[1:]  # setelah "Laporan dibuat."
    assert len(ups) == 1 and "tidak ditindaklanjuti" in ups[0].note and "Sudah normal" in ups[0].note
    assert len(_notes(staf)) == 1


def test_triage_to_meeting_advances_and_notifies_once(clinic, staf, aom):
    laporan = _laporan(clinic, staf)
    triage.to_meeting(find_row(aom, "laporan", laporan.pk), actor=aom)
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.UNDER_REVIEW
    ups = list(laporan.updates.all())[1:]
    assert len(ups) == 2
    assert ups[0].note == "Dipilah Direktur Operasional." and "rapat bersama" in ups[1].note
    assert len(_notes(staf)) == 1


def test_page_shows_riwayat_with_labels_and_hides_form_from_staff(client, clinic, staf, supervisor):
    laporan = _laporan(clinic, staf)
    url = reverse("reports:laporan_page_detail", args=[laporan.pk])
    client.force_login(supervisor)
    assert "Laporan dibuat." in client.get(url).content.decode()
    change_laporan_status(laporan, user=supervisor, to_status=ReportStatus.UNDER_REVIEW, note="Sedang dicek tim")
    html = client.get(url).content.decode()
    assert "Baru → " in html and "<strong>Ditinjau</strong>" in html and "Sedang dicek tim" in html
    assert ">Selesai<" in html and ">RESOLVED<" not in html
    assert "Tambah tanggapan" in html
    client.post(url, {"aksi": "tanggapan", "catatan": "Update kedua"})
    assert "Update kedua" in client.get(url).content.decode()
    assert len(_notes(staf)) == 1  # digabung dedupe 10 menit
    client.force_login(staf)
    assert "Tambah tanggapan" not in client.get(url).content.decode()


def test_inbox_triage_shows_help_text_for_notes(client, clinic, staf, aom):
    laporan = _laporan(clinic, staf)
    url = reverse("reports:inbox_triage", args=["laporan", laporan.pk])
    client.force_login(aom)
    page = client.get(url).content.decode()
    help_text = "Catatan ini terlihat oleh pelapor dan, untuk laporan cabang, oleh staf cabang itu."
    assert help_text in page
