"""Penjadwalan Pengingat Harian DO (kebutuhan bagian 4) dengan tanggal tetap."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from accounts.models import Role, User, UserRole
from core.models import Clinic
from pengingat import services as sv
from pengingat.models import Butir, Diingatkan, Kartu, Materi, Paksa, Pengaturan, Sebab, Status

pytestmark = pytest.mark.django_db

SEN = dt.date(2026, 10, 19)  # Senin
SAB = dt.date(2026, 10, 24)
MIN = dt.date(2026, 10, 25)


def d(n):
    return SEN + dt.timedelta(days=n)


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur", name="JoDerma Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def citra(db):
    return Clinic.objects.create(code="JC", name="JoDerma Citraland", open_time="14:00", close_time="22:00")


@pytest.fixture
def do(jemur):
    u = User.objects.create_user(username="hansen1", password="TestPassword123!", display_name="dr. Hansen")
    UserRole.objects.create(user=u, clinic=jemur, role=Role.AOM)
    return u


@pytest.fixture
def kosong(db):
    """Katalog kosong (tanpa data awal) supaya tiap test menyusun materinya sendiri."""
    Paksa.objects.all().delete()
    Materi.objects.all().delete()
    return Pengaturan.get()


def _m(kode, kelas="A", sasaran=("Perawat",), urutan=None, aktif=True, **kw):
    kw.setdefault("teks_wa", f"Teks {kode}")
    return Materi.objects.create(kode=kode, judul=f"Materi {kode}", kelas=kelas, sasaran=list(sasaran),
                                 urutan=urutan if urutan is not None else Materi.objects.count() + 1,
                                 aktif=aktif, poin=["a", "b", "c"], **kw)


def _ingat(materi, tanggal, do, clinic=None):
    return Diingatkan.objects.create(materi=materi, tanggal=tanggal, clinic=clinic, saluran="GRUP_WA", oleh=do)


def _kodes(kartu):
    return [b.materi.kode for b in kartu.butir.all()] if kartu else []


# --- Data awal ---------------------------------------------------------------------------------


def test_seed_catalog():
    assert Materi.objects.count() == 22
    aktif = Materi.objects.filter(aktif=True)
    assert {k: aktif.filter(kelas=k).count() for k in "ABC"} == {"A": 6, "B": 9, "C": 6}
    est = Materi.objects.get(kode="EST-01")
    assert not est.aktif and "Ditunda" in est.catatan
    assert Pengaturan.get().hari_kerja == [0, 1, 2, 3, 4, 5] and Pengaturan.get().kuota == 2
    assert set(Paksa.objects.values_list("materi__kode", flat=True)) <= {"AR-12"}
    assert Materi.objects.get(kode="AR-12").tanggal_sosialisasi == dt.date(2026, 10, 13)
    assert "{cabang}" in Materi.objects.get(kode="SP-01").teks_wa


# --- Pemilihan ---------------------------------------------------------------------------------


def test_two_items_on_workday_none_on_sunday(kosong):
    for k in ("A1", "A2", "A3"):
        _m(k, sasaran=(k,))
    assert _kodes(sv.kartu_untuk(SEN)) == ["A1", "A2"]
    assert sv.kartu_untuk(MIN) is None and not Kartu.objects.filter(tanggal=MIN).exists()


def test_never_reminded_ordered_by_class_then_catalog_order(kosong):
    _m("C1", "C", sasaran=("x",), urutan=1)
    _m("B1", "B", sasaran=("y",), urutan=2)
    _m("A1", "A", sasaran=("z",), urutan=3)
    _m("A0", "A", sasaran=("w",), urutan=4)
    assert _kodes(sv.kartu_untuk(SEN)) == ["A1", "A0"]


def test_only_due_items_fewer_than_quota(kosong, do):
    a = _m("A1", "A", sasaran=("x",))
    b = _m("B1", "B", sasaran=("y",))
    _ingat(a, d(-7), do)   # skor 1,0 -> jatuh tempo
    _ingat(b, d(-10), do)  # 10/14 -> belum
    assert _kodes(sv.kartu_untuk(SEN)) == ["A1"]


def test_highest_score_first_then_class(kosong, do):
    a = _m("A1", "A", sasaran=("x",))
    b = _m("B1", "B", sasaran=("y",))
    c = _m("C1", "C", sasaran=("z",))
    _ingat(a, d(-7), do)    # 1,0
    _ingat(b, d(-28), do)   # 2,0
    _ingat(c, d(-28), do)   # 1,0
    assert _kodes(sv.kartu_untuk(SEN)) == ["B1", "A1"]  # skor sama 1,0: A sebelum C


def test_target_variety(kosong):
    _m("P1", sasaran=("Perawat",))
    _m("P2", sasaran=("Perawat",))
    _m("K1", sasaran=("Kasir",))
    assert _kodes(sv.kartu_untuk(SEN)) == ["P1", "K1"]


def test_same_target_allowed_when_no_alternative(kosong):
    _m("P1", sasaran=("Perawat",))
    _m("P2", sasaran=("Perawat",))
    assert _kodes(sv.kartu_untuk(SEN)) == ["P1", "P2"]


def test_card_locked_for_the_day(kosong, do):
    for k in ("A1", "A2", "A3"):
        _m(k, sasaran=(k,))
    first = sv.kartu_untuk(SEN)
    b = first.butir.get(materi__kode="A1")
    sv.tandai_diingatkan(b, user=do, cabang="keduanya", saluran="GRUP_WA", today=SEN)
    again = sv.kartu_untuk(SEN)
    assert again.pk == first.pk and _kodes(again) == ["A1", "A2"]  # A3 tidak naik mengisi


def test_untouched_item_reappears_next_day(kosong, do):
    for k in ("A1", "A2", "A3"):
        _m(k, sasaran=(k,))
    k1 = sv.kartu_untuk(SEN)
    sv.tandai_diingatkan(k1.butir.get(materi__kode="A1"), user=do, cabang="keduanya", saluran="GRUP_WA", today=SEN)
    assert _kodes(sv.kartu_untuk(d(1))) == ["A2", "A3"]  # A2 tidak disentuh: tetap jatuh tempo


def test_tunda_forces_next_workday_outside_quota(kosong, do):
    for k in ("A1", "A2", "A3", "A4"):
        _m(k, sasaran=(k,))
    k1 = sv.kartu_untuk(SEN)
    p = sv.tunda(k1.butir.get(materi__kode="A1"), user=do, today=SEN)
    assert p.tanggal == d(1) and p.sebab == Sebab.TUNDA
    assert not Diingatkan.objects.exists()
    k2 = sv.kartu_untuk(d(1))
    assert _kodes(k2) == ["A1", "A2", "A3"]  # A1 paksa + kuota 2
    assert k2.butir.get(materi__kode="A1").paksa_id == p.pk


def test_tunda_on_saturday_goes_to_monday(kosong, do):
    _m("A1")
    k = sv.kartu_untuk(SAB)
    assert sv.tunda(k.butir.get(), user=do, today=SAB).tanggal == dt.date(2026, 10, 26)


def test_untouched_forced_item_reappears(kosong, do):
    a = _m("A1", sasaran=("x",))
    _ingat(a, SEN, do)
    Paksa.objects.create(materi=a, tanggal=d(1), sebab=Sebab.TEMUAN)
    assert _kodes(sv.kartu_untuk(d(1))) == ["A1"]
    assert _kodes(sv.kartu_untuk(d(2))) == ["A1"]  # tidak ditangani kemarin: muncul lagi
    sv.tandai_diingatkan(Kartu.objects.get(tanggal=d(2)).butir.get(), user=do, cabang="keduanya",
                         saluran="BRIEFING", today=d(2))
    assert Paksa.objects.get().selesai_pada == d(2)
    assert _kodes(sv.kartu_untuk(d(3))) == []


def test_diingatkan_records_log_and_stops_reappearing(kosong, do, jemur):
    _m("A1", sasaran=("x",))
    k = sv.kartu_untuk(SEN)
    log = sv.tandai_diingatkan(k.butir.get(), user=do, cabang=str(jemur.pk), saluran="LANGSUNG",
                               catatan=" briefing ", today=SEN)
    assert log.clinic == jemur and log.catatan == "briefing" and log.tanggal == SEN
    assert k.butir.get().status == Status.DIINGATKAN
    assert _kodes(sv.kartu_untuk(d(1))) == [] and _kodes(sv.kartu_untuk(d(8))) == ["A1"]  # 7 hari kemudian


def test_lewati_needs_reason_and_pushes_one_interval(kosong, do):
    _m("A1", sasaran=("x",))
    b = sv.kartu_untuk(SEN).butir.get()
    with pytest.raises(ValidationError):
        sv.lewati(b, user=do, alasan="  ", today=SEN)
    sv.lewati(b, user=do, alasan="Materi direvisi", today=SEN)
    assert not Diingatkan.objects.exists()
    assert _kodes(sv.kartu_untuk(d(1))) == [] and _kodes(sv.kartu_untuk(d(7))) == ["A1"]


def test_cannot_handle_twice_or_other_day(kosong, do):
    _m("A1", sasaran=("x",))
    b = sv.kartu_untuk(SEN).butir.get()
    with pytest.raises(ValidationError):
        sv.tunda(b, user=do, today=d(1))
    sv.tunda(b, user=do, today=SEN)
    with pytest.raises(ValidationError):
        sv.lewati(Butir.objects.get(pk=b.pk), user=do, alasan="x", today=SEN)


def test_inactive_items_never_scheduled(kosong):
    _m("A1", aktif=False)
    assert _kodes(sv.kartu_untuk(SEN)) == []


def test_ulangan_new_material(kosong, do):
    a = _m("N1", "C", sasaran=("x",), tanggal_sosialisasi=dt.date(2026, 10, 17))  # Sabtu
    made = sv.jadwalkan_ulangan(a, actor=do, today=dt.date(2026, 10, 17))
    # +1 Minggu -> Senin 19; +3 Selasa 20; +7 Sabtu 24; +14 Sabtu 31; +30 Senin 16/11
    assert [p.tanggal for p in made] == [dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 24),
                                         dt.date(2026, 10, 31), dt.date(2026, 11, 16)]
    assert sv.jadwalkan_ulangan(a, today=dt.date(2026, 10, 17)) == []  # tidak berlipat
    later = _m("N2", tanggal_sosialisasi=dt.date(2026, 10, 1))
    assert [p.tanggal for p in sv.jadwalkan_ulangan(later, today=SEN)] == [dt.date(2026, 10, 31)]


def test_ulangan_days_then_normal_rotation(kosong, do):
    a = _m("N1", "C", sasaran=("x",), tanggal_sosialisasi=SEN)
    _ingat(a, SEN, do)
    sv.jadwalkan_ulangan(a, today=SEN)
    hari = []
    for i in range(1, 60):
        day = d(i)
        k = sv.kartu_untuk(day)
        if k and k.butir.exists():
            hari.append(i)
            sv.tandai_diingatkan(k.butir.get(), user=do, cabang="keduanya", saluran="GRUP_WA", today=day)
    # ulangan +1, +3, +7 (Senin 26), +14, +30; lalu giliran normal kelas C (28 hari)
    assert hari[:5] == [1, 3, 7, 14, 30] and hari[5] == 58


# --- Tampilan ----------------------------------------------------------------------------------


def test_wa_text_cabang_placeholder(kosong, jemur):
    a = _m("A1", teks_wa="Selamat pagi tim {cabang} 🙏 halo")
    assert sv.teks_wa(a) == "Selamat pagi tim 🙏 halo"
    a.clinic = jemur
    assert sv.teks_wa(a) == "Selamat pagi tim Jemur Andayani 🙏 halo"


def test_last_reminded_per_branch(kosong, do, jemur, citra):
    a = _m("A1")
    _ingat(a, d(-10), do)            # keduanya
    _ingat(a, d(-3), do, clinic=citra)
    out = sv.terakhir_per_cabang([a.pk], [jemur, citra])[a.pk]
    assert out == [("Jemur Andayani", d(-10)), ("Citraland", d(-3))]


def test_preview_seven_days(kosong, do):
    for k in ("A1", "A2", "A3", "A4"):
        _m(k, sasaran=(k,))
    sv.kartu_untuk(SEN)
    prev = sv.pratinjau(SEN)
    assert len(prev) == 7 and [h.libur for h in prev] == [False] * 5 + [True, False]
    assert [m.kode for m in prev[0].materi] == ["A3", "A4"]  # A1, A2 dianggap sudah diingatkan hari ini
    assert prev[1].materi == []  # semuanya baru diingatkan; jatuh tempo lagi 7 hari kemudian
    assert [m.kode for m in prev[6].materi] == ["A1", "A2"]  # Senin berikutnya
