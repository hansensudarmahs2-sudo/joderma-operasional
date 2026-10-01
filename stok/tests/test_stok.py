"""Modul Stok Apotek fase 1.

File uji adalah ekspor Omnicare 30 September 2026 (`fixtures/`) yang juga dipakai workbook
*Analisa Persediaan JoDerma Jul-Sep 2026*, sehingga angka di sini = angka workbook.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic
from stok import hitung, parser, services
from stok.models import Parameter, PergerakanBulanan, Produk, ProdukAlias, StatusPeriode, Unggahan

FIX = Path(__file__).parent / "fixtures"
PERGERAKAN = {
    ("jemur", 7): "movement_30376_2026-07.xls",
    ("jemur", 8): "movement_30376_2026-08.xls",
    ("jemur", 9): "movement_30376_2026-09.xls",
    ("citra", 7): "movement_31281_2026-07.xls",
    ("citra", 8): "movement_31281_2026-08.xls",
    ("citra", 9): "movement_31281_2026-09.xls",
}


def _baca(nama: str) -> tuple[bytes, parser.HasilBaca]:
    data = (FIX / nama).read_bytes()
    return data, parser.baca(data, nama)


def _user(clinic, username, *roles):
    user = User.objects.create_user(username=username, password="TestPassword123!", display_name=username.title())
    for role in roles:
        UserRole.objects.create(user=user, clinic=clinic, role=role)
    return user


@pytest.fixture
def cabang(db):
    jmr = Clinic.objects.create(code="jmr", name="JoDerma Jemur Andayani")
    ctl = Clinic.objects.create(code="jc", name="JoDerma Citraland")
    return jmr, ctl


@pytest.fixture
def apoteker(cabang):
    return _user(cabang[0], "apoteker1", Role.APOTEKER, Role.STAF)


def _impor(user, nama, clinic=None):
    data = (FIX / nama).read_bytes()
    return services.impor(data, nama, user, clinic)


@pytest.fixture
def data_30sep(cabang, apoteker, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    _impor(apoteker, "product_list_30376.xls")
    _impor(apoteker, "stock_level_30376.xls")
    _impor(apoteker, "stock_level_31281.xls")
    for nama in PERGERAKAN.values():
        _impor(apoteker, nama)
    return cabang


# --- Pembaca file -----------------------------------------------------------


def test_parser_reads_all_exports_that_default_xlrd_rejects():
    jumlah = {nama: len(_baca(nama)[1].baris) for nama in PERGERAKAN.values()}
    assert [jumlah[PERGERAKAN[k]] for k in (("jemur", 7), ("jemur", 8), ("jemur", 9))] == [244, 252, 242]
    assert [jumlah[PERGERAKAN[k]] for k in (("citra", 7), ("citra", 8), ("citra", 9))] == [213, 233, 246]
    _, produk = _baca("product_list_30376.xls")
    assert len(produk.baris) == 422
    assert sum(1 for b in produk.baris if b["non_stok"]) == 7
    _, sep = _baca(PERGERAKAN[("jemur", 9)])
    assert (sep.jenis, sep.tahun, sep.bulan, sep.petunjuk_cabang) == ("PERGERAKAN", 2026, 9, "jemur")
    _, stok = _baca("stock_level_31281.xls")
    assert (stok.tanggal.isoformat(), stok.petunjuk_cabang, len(stok.baris)) == ("2026-09-30", "citra", 267)


def test_key_matches_name_plus_dose_across_reports():
    assert parser.kunci("Rydian Tablet", "10 mg") == parser.kunci("Rydian Tablet10 mg") == parser.kunci("Rydian Tablet 10 mg")
    assert parser.kunci("AB Oint", "-") == "aboint"


def test_unknown_file_is_rejected():
    with pytest.raises(parser.FileTidakDikenal):
        parser.baca(b"bukan excel", "x.xls")


# --- Impor dan uji kelengkapan ------------------------------------------------


def test_full_import_all_periods_complete(data_30sep):
    jmr, ctl = data_30sep
    assert Produk.objects.count() == 422
    assert StatusPeriode.objects.count() == 6
    assert all(s.lengkap for s in StatusPeriode.objects.all())
    for bulan, mutasi in ((7, 7392), (8, 6820), (9, 8449)):
        rows = PergerakanBulanan.objects.filter(tahun=2026, bulan=bulan)
        assert round(sum(r.mutasi for r in rows.filter(clinic=jmr))) == mutasi
        assert round(sum(r.mutasi for r in rows)) == 0
    # 16 produk Jemur: laporan pergerakan diunduh setelah Tingkat Persediaan (dicatat, tidak gagal)
    assert len(StatusPeriode.objects.get(clinic=jmr, bulan=9).selisih_stok) == 16
    assert StatusPeriode.objects.get(clinic=ctl, bulan=9).selisih_stok == []


def _sep_citraland_tanpa(nama_hilang: str, blok: int = 50):
    data, hasil = _baca(PERGERAKAN[("citra", 9)])
    idx = next(i for i, b in enumerate(hasil.baris) if b["nama"] == nama_hilang)
    awal = max(0, idx - blok // 2)
    potong = copy.deepcopy(hasil)
    potong.baris = hasil.baris[:awal] + hasil.baris[awal + blok:]
    return data, potong


def test_truncated_download_marks_period_incomplete(cabang, apoteker, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    jmr, ctl = cabang
    for nama in ("product_list_30376.xls", "stock_level_30376.xls", "stock_level_31281.xls"):
        _impor(apoteker, nama)
    for key, nama in PERGERAKAN.items():
        if key != ("citra", 9):
            _impor(apoteker, nama)
    data, potong = _sep_citraland_tanpa("Forti D 5000")
    services.impor_hasil(potong, data, "terpotong.xls", apoteker)

    sep = StatusPeriode.objects.get(clinic=ctl, tahun=2026, bulan=9)
    assert not sep.lengkap
    assert sep.jumlah_baris == 196
    assert "Forti D 5000" in sep.diduga_hilang
    # Periode belum lengkap tidak masuk rata-rata
    data_ctl = next(c for c in hitung.hitung().cabang if c.clinic == ctl)
    assert data_ctl.periode == [(2026, 7), (2026, 8)]
    assert data_ctl.periode_belum_lengkap == [(2026, 9)]


def test_two_truncated_downloads_merge_without_duplicates(data_30sep, apoteker):
    jmr, ctl = data_30sep
    PergerakanBulanan.objects.filter(clinic=ctl, tahun=2026, bulan=9).delete()
    data, a = _sep_citraland_tanpa("Forti D 5000")
    _, b = _sep_citraland_tanpa("Cream EC")
    services.impor_hasil(a, data, "unduhan-1.xls", apoteker)
    assert not StatusPeriode.objects.get(clinic=ctl, bulan=9).lengkap
    up = services.impor_hasil(b, data, "unduhan-2.xls", apoteker)
    assert PergerakanBulanan.objects.filter(clinic=ctl, tahun=2026, bulan=9).count() == 246
    assert StatusPeriode.objects.get(clinic=ctl, bulan=9).lengkap
    assert any("Digabung" in p for p in up.peringatan)


def test_movement_requires_product_list_and_branch(cabang, apoteker, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    with pytest.raises(Exception, match="Daftar Produk"):
        _impor(apoteker, PERGERAKAN[("jemur", 9)])
    _impor(apoteker, "product_list_30376.xls")
    data = (FIX / PERGERAKAN[("jemur", 9)]).read_bytes()
    with pytest.raises(Exception, match="Cabang tidak bisa ditebak"):
        services.impor(data, "laporan.xls", apoteker)
    up = services.impor(data, "laporan.xls", apoteker, cabang[0])
    assert up.jumlah_cocok == 242


def test_renamed_product_keeps_history_through_alias(data_30sep, apoteker):
    produk = Produk.objects.get(nama="Forti D 5000")
    data, hasil = _baca("product_list_30376.xls")
    for b in hasil.baris:
        if b["omnicare_id"] == produk.omnicare_id:
            b["nama"] = "Forti D 5000 IU"
            b["kunci"] = parser.kunci("Forti D 5000 IU")
    services.impor_hasil(hasil, data, "produk-baru.xls", apoteker)
    assert ProdukAlias.objects.filter(produk=produk, kunci="fortid5000").exists()
    assert services.peta_kunci()["fortid5000"] == produk.pk


# --- Perhitungan = workbook ---------------------------------------------------


def test_status_and_transfer_match_workbook(data_30sep):
    jmr, ctl = data_30sep
    hasil = hitung.hitung()
    per = {c.clinic: c for c in hasil.cabang}
    assert hitung.hitung_status(per[jmr]) == {"Kosong": 48, "Di bawah buffer": 90, "Mendekati buffer": 14, "Aman": 133, "Tanpa pemakaian": 67}
    assert hitung.hitung_status(per[ctl]) == {"Kosong": 43, "Di bawah buffer": 49, "Mendekati buffer": 19, "Aman": 149, "Tanpa pemakaian": 50}
    arah = [(t.dari.clinic, t.ke.clinic) for t in hasil.transfer]
    assert arah.count((ctl, jmr)) == 40 and arah.count((jmr, ctl)) == 19
    # Nilai rupiah dari lembar Ringkasan workbook
    assert sum(t.nilai for t in hasil.transfer) == pytest.approx(35_504_905.485, abs=0.01)
    assert sum(b.nilai_order for b in per[jmr].baris.values()) == pytest.approx(230_648_447.375, abs=0.01)
    assert sum(b.nilai_order for b in per[ctl].baris.values()) == pytest.approx(84_202_222.736, abs=0.01)
    assert per[jmr].periode == [(2026, 7), (2026, 8), (2026, 9)]
    assert len(hitung.prioritas(per[jmr])) + len(hitung.prioritas(per[ctl])) == 545


def test_parameter_changes_status(data_30sep):
    jmr, _ = data_30sep
    param = Parameter.aktif()
    param.bulan_buffer = 2
    param.save()
    status = hitung.hitung_status(next(c for c in hitung.hitung().cabang if c.clinic == jmr))
    assert status["Di bawah buffer"] > 90


# --- Halaman dan hak akses -----------------------------------------------------


def test_pharmacist_uploads_several_files_at_once(client, cabang, apoteker, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(apoteker)
    files = [open(FIX / n, "rb") for n in (PERGERAKAN[("jemur", 9)], "product_list_30376.xls", "stock_level_30376.xls")]
    try:
        resp = client.post(reverse("stok:unggah"), {"file": files, "cabang": ""}, follow=True)
    finally:
        for f in files:
            f.close()
    assert resp.status_code == 200
    assert Unggahan.objects.count() == 3  # Daftar Produk diproses lebih dulu meski dipilih terakhir
    assert PergerakanBulanan.objects.count() == 242
    body = resp.content.decode()
    assert "Status periode pergerakan" in body and "242 dari 242 baris" in body


def test_pages_render_with_data(client, data_30sep, apoteker):
    client.force_login(apoteker)
    for tab in ("order", "transfer", "impor"):
        body = client.get(reverse("stok:index"), {"tab": tab, "cabang": "semua"}).content.decode()
        assert "Stok Apotek" in body
    body = client.get(reverse("stok:index"), {"tab": "order", "cabang": "semua", "status": "Kosong"}).content.decode()
    assert "Kosong" in body and "Simpan parameter" in body


@pytest.mark.parametrize("roles", [(Role.APOTEKER,), (Role.ASISTEN_APOTEKER,), (Role.AOM,)])
def test_pharmacy_staff_and_director_can_edit(client, cabang, roles):
    user = _user(cabang[0], "u1", *roles)
    client.force_login(user)
    assert client.get(reverse("stok:index")).status_code == 200
    resp = client.post(reverse("stok:parameter"), {
        "bulan_rata_rata": "3", "bulan_buffer": "1.5", "ambang_persen": "25", "target_bulan": "2", "cadangan_bulan": "2",
    })
    assert resp.status_code == 302
    assert Parameter.aktif().bulan_buffer == 1.5


def test_owner_reads_only(client, cabang):
    owner = _user(cabang[0], "yohanes", Role.OWNER)
    client.force_login(owner)
    body = client.get(reverse("stok:index"), {"tab": "impor"}).content.decode()
    assert "Status periode pergerakan" in body
    assert "Unggah ekspor Omnicare" not in body and "Simpan parameter" not in body
    assert client.post(reverse("stok:unggah")).status_code == 403
    assert client.post(reverse("stok:parameter"), {"bulan_buffer": "9"}).status_code == 403


@pytest.mark.parametrize("roles", [(Role.PERAWAT, Role.STAF), (Role.FRONT_DESK,), (Role.SUPERVISOR,), (Role.ADMIN,)])
def test_other_roles_are_forbidden(client, cabang, roles):
    client.force_login(_user(cabang[0], "u2", *roles))
    assert client.get(reverse("stok:index")).status_code == 403
    assert client.post(reverse("stok:unggah")).status_code == 403
    assert client.post(reverse("stok:parameter")).status_code == 403


def test_menu_shows_stok_only_for_allowed_roles(cabang):
    from core import peran

    def label(user):
        return [lbl for s in peran.nav_sections(user) for lbl, _ in s.items]

    assert "Stok Apotek" in label(_user(cabang[0], "a", Role.APOTEKER, Role.STAF))
    assert "Stok Apotek" in label(_user(cabang[0], "b", Role.ASISTEN_APOTEKER))
    assert "Stok Apotek" in label(_user(cabang[0], "c", Role.AOM))
    assert "Stok Apotek" in label(_user(cabang[0], "d", Role.OWNER))
    assert "Stok Apotek" not in label(_user(cabang[0], "e", Role.PERAWAT, Role.STAF))
