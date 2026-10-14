"""Katalog materi, Ingatkan besok, pengaturan, dan peringatan kapasitas (kebutuhan 3.2, 3.3, 4.1, 4.3)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import Clinic, local_today
from direktur.models import Decider, Decision, DecisionStatus
from pengingat import katalog as kat
from pengingat import services as sv
from pengingat.models import Materi, Paksa, Pengaturan, Sebab

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur", name="JoDerma Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def do(jemur):
    return _user(jemur, "hansen1", Role.AOM)


@pytest.fixture
def client_do(client, do):
    client.force_login(do)
    return client


def _form(**extra):
    data = {"kode": "ar-13", "judul": "Alur baru", "jenis": "alur", "kelas": "B", "sasaran": ["Perawat", "Kasir"],
            "poin": ["Satu", "Dua", "Tiga"], "teks_wa": "Halo tim {cabang}", "rujukan": "Alur.docx",
            "aktif": "1", "tanggal_sosialisasi": "", "catatan": "", "urutan": "30", "cabang": ""}
    data.update(extra)
    return data


def test_catalog_page_lists_active_and_capacity(client_do):
    body = client_do.get(reverse("pengingat:katalog")).content.decode()
    assert "SP-01" in body and "EST-01" not in body  # bawaan: hanya yang aktif
    assert "Kapasitas mingguan 12 butir" in body and "kebutuhan materi aktif ±12 butir" in body
    body = client_do.get(reverse("pengingat:katalog"), {"status": "nonaktif"}).content.decode()
    assert "EST-01" in body and "SP-01" not in body
    assert "Pengingat" in body and 'aria-label="Kebijakan"' in body  # tab kelompok Kebijakan


def test_capacity_warning_when_demand_exceeds(client_do):
    Materi.objects.filter(aktif=True).update(kelas="A")  # 21 butir mingguan > 12
    assert kat.kapasitas() == {"kapasitas": 12, "kebutuhan": 21.0, "lebih": True}
    body = client_do.get(reverse("pengingat:katalog")).content.decode()
    assert "Kapasitas mingguan 12, kebutuhan 21 — sebagian materi akan terlambat" in body


def test_create_material_with_ulangan_and_audit(client_do, do):
    today = local_today()
    res = client_do.post(reverse("pengingat:materi_baru"), _form(tanggal_sosialisasi=today.isoformat()))
    assert res.status_code == 302
    m = Materi.objects.get(kode="AR-13")
    assert m.sasaran == ["Kasir", "Perawat"] or set(m.sasaran) == {"Perawat", "Kasir"}
    assert m.poin == ["Satu", "Dua", "Tiga"] and m.urutan == 30 and m.aktif
    assert Paksa.objects.filter(materi=m, sebab=Sebab.ULANGAN).count() == 5
    assert AuditEvent.objects.filter(entity_type="pengingat_materi", entity_id=str(m.pk)).exists()


def test_new_form_defaults_to_today_for_socialisation(client_do):
    body = client_do.get(reverse("pengingat:materi_baru")).content.decode()
    assert f'value="{local_today().isoformat()}"' in body


def test_form_validation_keeps_input(client_do):
    res = client_do.post(reverse("pengingat:materi_baru"), _form(kode="SP-01", sasaran=[], poin=["", "", ""]))
    body = res.content.decode()
    assert res.status_code == 200 and "Kode SP-01 sudah dipakai" in body
    assert "Pilih minimal satu sasaran." in body and "Tulis minimal satu poin kunci." in body
    assert 'value="Alur baru"' in body and Materi.objects.count() == 22


def test_edit_material_and_changed_date_reschedules(client_do):
    m = Materi.objects.get(kode="AR-07")
    url = reverse("pengingat:materi_ubah", args=[m.pk])
    assert "AR-07" in client_do.get(url).content.decode()
    client_do.post(url, _form(kode="AR-07", judul="Siap memanggil dokter", kelas="A"))
    m.refresh_from_db()
    assert m.judul == "Siap memanggil dokter" and not Paksa.objects.filter(materi=m).exists()
    client_do.post(url, _form(kode="AR-07", judul="Siap memanggil dokter", tanggal_sosialisasi=local_today().isoformat()))
    assert Paksa.objects.filter(materi=m, sebab=Sebab.ULANGAN).count() == 5


def test_policy_reference_only_for_enacted_policies(client_do, do, jemur):
    pol = Decision.objects.create(title="Batas belanja Rp1 jt", decider=Decider.OWNER, status=DecisionStatus.DITETAPKAN,
                                  is_policy=True, decision_text="Belanja di atas Rp1 jt perlu persetujuan.", created_by=do)
    draft = Decision.objects.create(title="Masih dibahas", decider=Decider.OWNER, created_by=do)
    client_do.post(reverse("pengingat:materi_baru"), _form(kode="KB-01", jenis="kebijakan", kebijakan=str(draft.pk)))
    assert not Materi.objects.filter(kode="KB-01").exists()
    client_do.post(reverse("pengingat:materi_baru"), _form(kode="KB-01", jenis="kebijakan", kebijakan=str(pol.pk)))
    m = Materi.objects.get(kode="KB-01")
    assert m.kebijakan == pol
    Materi.objects.exclude(pk=m.pk).update(aktif=False)
    cfg = Pengaturan.get()
    cfg.hari_kerja = list(range(7))
    cfg.save()
    body = client_do.get(reverse("direktur:overview")).content.decode()
    assert "Batas belanja Rp1 jt" in body and "Belanja di atas Rp1 jt perlu persetujuan." in body


def test_deactivate_keeps_history_and_stops_scheduling(client_do):
    m = Materi.objects.get(kode="SP-01")
    client_do.post(reverse("pengingat:materi_aktif", args=[m.pk]), {"aktif": "0"})
    m.refresh_from_db()
    assert not m.aktif
    cfg = Pengaturan.get()
    cfg.hari_kerja = list(range(7))
    cfg.save()
    assert "SP-01" not in [b.materi.kode for b in sv.kartu_untuk(local_today()).butir.all()]
    client_do.post(reverse("pengingat:materi_aktif", args=[m.pk]), {"aktif": "1"})
    m.refresh_from_db()
    assert m.aktif


def test_ingatkan_besok_forces_next_workday(client_do, do):
    m = Materi.objects.get(kode="PO-01")
    client_do.post(reverse("pengingat:ingatkan_besok", args=[m.pk]))
    p = Paksa.objects.get(materi=m, sebab=Sebab.TEMUAN)
    assert p.tanggal == sv.next_workday(local_today(), Pengaturan.get())
    client_do.post(reverse("pengingat:ingatkan_besok", args=[m.pk]))
    assert Paksa.objects.filter(materi=m, sebab=Sebab.TEMUAN).count() == 1  # tidak berlipat
    est = Materi.objects.get(kode="EST-01")
    res = client_do.post(reverse("pengingat:ingatkan_besok", args=[est.pk]), follow=True)
    assert "Materi nonaktif tidak dijadwalkan" in res.content.decode()


def test_ingatkan_besok_appears_outside_quota(do):
    sab = dt.date(2026, 10, 24)
    Paksa.objects.all().delete()  # tanpa ulangan AR-12 dari data awal
    m = Materi.objects.get(kode="PO-01")
    p = kat.ingatkan_besok(m, user=do, today=sab)
    assert p.tanggal == dt.date(2026, 10, 26)
    kartu = sv.kartu_untuk(dt.date(2026, 10, 26))
    assert [b.materi.kode for b in kartu.butir.all()][0] == "PO-01" and kartu.butir.count() == 3


def test_settings_saved_and_validated(client_do):
    res = client_do.post(reverse("pengingat:pengaturan"), {"hari_kerja": ["0", "2", "4"], "kuota": "3",
                                                         "interval_a": "5", "interval_b": "10", "interval_c": "20"})
    assert res.status_code == 302
    cfg = Pengaturan.get()
    assert cfg.hari_kerja == [0, 2, 4] and cfg.kuota == 3 and cfg.interval("C") == 20
    res = client_do.post(reverse("pengingat:pengaturan"), {"kuota": "0", "interval_a": "x", "interval_b": "1",
                                                         "interval_c": "1"}, follow=True)
    body = res.content.decode()
    assert "Pilih minimal satu hari kerja." in body and "Butir per hari harus angka 1–10." in body
    assert Pengaturan.get().kuota == 3
    assert AuditEvent.objects.filter(entity_type="pengingat_pengaturan").count() == 1


@pytest.mark.parametrize("roles", [(Role.STAF,), (Role.PIC, Role.FRONT_DESK), (Role.OWNER,)])
def test_catalog_forbidden_for_non_director(client, jemur, roles):
    client.force_login(_user(jemur, "orang", *roles))
    m = Materi.objects.first()
    for name, args in (("katalog", []), ("materi_baru", []), ("materi_ubah", [m.pk])):
        assert client.get(reverse(f"pengingat:{name}", args=args)).status_code == 403
    for name, args in (("materi_baru", []), ("materi_ubah", [m.pk]), ("materi_aktif", [m.pk]),
                       ("ingatkan_besok", [m.pk]), ("pengaturan", [])):
        assert client.post(reverse(f"pengingat:{name}", args=args), _form(aktif="0", kuota="5")).status_code == 403
    m.refresh_from_db()
    assert m.aktif and Materi.objects.count() == 22 and not Paksa.objects.filter(sebab=Sebab.TEMUAN).exists()
