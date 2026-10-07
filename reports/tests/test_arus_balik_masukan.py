"""Tahap 3b: pengirim Masukan privat diberi tahu tanggapan Direktur; hasil pilah dan riwayat tampil."""
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from notifications.models import Notification
from reports import triage
from reports.inbox import find_row
from reports.models import MasukanTanggapan
from reports.services import add_masukan_tanggapan, archive_masukan, create_masukan, publish_masukan

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _masukan(clinic, user):
    return create_masukan(clinic=clinic, user=user, title="Jam istirahat digeser", description="Usul.")


def _notes(user):
    return list(Notification.objects.filter(user=user, type_code="MASUKAN_RESPONSE"))


@pytest.fixture
def aom(clinic):
    return _user(clinic, "hansen1", Role.AOM)


def test_aom_writes_tanggapan_and_sender_notified(clinic, staf, aom):
    masukan = _masukan(clinic, staf)
    t = add_masukan_tanggapan(masukan, user=aom, note="  Kami pertimbangkan.  ")
    assert t.note == "Kami pertimbangkan." and t.author == aom
    assert MasukanTanggapan.objects.filter(masukan=masukan).count() == 1
    (n,) = _notes(staf)
    assert n.title == "Tanggapan atas masukan Anda: Jam istirahat digeser"
    assert "Kami pertimbangkan." in n.body
    assert n.url == reverse("reports:masukan_page_detail", args=[masukan.pk])


def test_owner_cannot_write(clinic, staf):
    owner = _user(clinic, "yohanes", Role.OWNER)
    masukan = _masukan(clinic, staf)
    with pytest.raises(PermissionDenied):
        add_masukan_tanggapan(masukan, user=owner, note="halo")
    assert MasukanTanggapan.objects.count() == 0


def test_sender_post_is_403(client, clinic, staf):
    masukan = _masukan(clinic, staf)
    client.force_login(staf)
    r = client.post(reverse("reports:masukan_page_detail", args=[masukan.pk]), {"aksi": "tanggapan", "catatan": "balas"})
    assert r.status_code == 403
    assert MasukanTanggapan.objects.count() == 0


def test_blank_refused(clinic, staf, aom):
    masukan = _masukan(clinic, staf)
    with pytest.raises(ValidationError):
        add_masukan_tanggapan(masukan, user=aom, note="   ")


def test_publish_notifies_sender_besides_broadcast(clinic, staf, aom):
    masukan = _masukan(clinic, staf)
    publish_masukan(masukan, user=aom, clinics=[clinic])
    (n,) = _notes(staf)
    assert "Dipublikasikan ke JoDerma Test." in n.body
    assert Notification.objects.filter(user=staf, type_code="MASUKAN_PUBLISHED").exists()


def test_archive_notifies_sender(clinic, staf, aom):
    masukan = _masukan(clinic, staf)
    archive_masukan(masukan, user=aom, reason="Duplikat")
    (n,) = _notes(staf)
    assert "Diarsipkan. Alasan: Duplikat" in n.body


def test_triage_dismiss_notifies_once(clinic, staf, aom):
    masukan = _masukan(clinic, staf)
    triage.dismiss(find_row(aom, "masukan", masukan.pk), actor=aom, reason="Sudah ada aturannya")
    (n,) = _notes(staf)
    assert "tidak ditindaklanjuti" in n.body and "Sudah ada aturannya" in n.body
    assert MasukanTanggapan.objects.count() == 0


def test_triage_to_meeting_notifies_once(clinic, staf, aom):
    masukan = _masukan(clinic, staf)
    triage.to_meeting(find_row(aom, "masukan", masukan.pk), actor=aom)
    (n,) = _notes(staf)
    assert "rapat bersama" in n.body


def test_page_shows_triage_and_tanggapan_to_sender_without_form(client, clinic, staf, aom):
    masukan = _masukan(clinic, staf)
    url = reverse("reports:masukan_page_detail", args=[masukan.pk])
    client.force_login(staf)
    assert "Belum ada tanggapan." in client.get(url).content.decode()
    triage.dismiss(find_row(aom, "masukan", masukan.pk), actor=aom, reason="Sudah ada aturannya")
    add_masukan_tanggapan(masukan, user=aom, note="Terima kasih usulnya")
    html = client.get(url).content.decode()
    assert "Hasil pilah: Tidak ditindaklanjuti" in html and "Sudah ada aturannya" in html
    assert "Terima kasih usulnya" in html
    assert "Tulis tanggapan" not in html and "Belum ada tanggapan." not in html


def test_aom_sees_form_and_can_post(client, clinic, staf, aom):
    masukan = _masukan(clinic, staf)
    url = reverse("reports:masukan_page_detail", args=[masukan.pk])
    client.force_login(aom)
    assert "Tulis tanggapan" in client.get(url).content.decode()
    client.post(url, {"aksi": "tanggapan", "catatan": "Siap, kami bahas."})
    assert "Siap, kami bahas." in client.get(url).content.decode()
    assert len(_notes(staf)) == 1
