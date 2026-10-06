"""Keputusan product owner 6 Okt 2026: tidak ada harga dan nama pabrikan/supplier di ops.joderma.id.

Test ini memakai baris tiruan (tanpa berkas .xls), jadi tetap jalan tanpa xlrd. Dari kolom
pabrikan hanya diambil tanda "produksi sendiri" untuk kolom Tindakan.
"""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic
from stok import hitung, parser, services
from stok.models import PergerakanBulanan, PosisiStok, Produk, StatusPeriode


def _baris_produk(pid, nama, pabrikan):
    r = [""] * 23
    r[0] = float(pid)
    r[3], r[4], r[5], r[6], r[7], r[9] = "Krim", nama, "-", pabrikan, "-", "Obat luar"
    r[10], r[12] = 15000.0, 25000.0          # harga modal, harga jual
    r[15], r[19], r[20], r[22] = "Tube", 5.0, 10.0, "Aktif"
    return r


def _daftar_produk():
    rows = [[""] * 23] * 4 + [
        _baris_produk(1, "Krim Racikan Dryn", "DRYN"),
        _baris_produk(2, "Salep Pabrik", "PT Contoh Farma"),
    ]
    return parser._daftar_produk("DAFTAR PRODUK PER 30 SEPTEMBER 2026", rows)


def _tingkat_persediaan():
    rows = [[""] * 9] * 3 + [
        ["Krim", "", "Krim Racikan Dryn", "", "", "", 1.0, "", 15000.0],
        ["Krim", "", "Salep Pabrik", "", "", "", 1.0, "", 15000.0],
    ]
    return parser._tingkat_persediaan("TINGKAT PERSEDIAAN JEMUR PER 30 SEPTEMBER 2026", rows, "stok.xls")


def test_parser_keeps_no_price_or_manufacturer_name():
    produk = _daftar_produk().baris
    for b in produk:
        assert not {"harga_modal", "harga_jual", "pabrikan"} & set(b)
    assert [b["produksi_sendiri"] for b in produk] == [True, False]
    for b in _tingkat_persediaan().baris:
        assert "nilai_modal" not in b


def test_models_have_no_price_or_manufacturer_field():
    nama_produk = {f.name for f in Produk._meta.get_fields()}
    assert not {"harga_modal", "harga_jual", "pabrikan"} & nama_produk
    assert "produksi_sendiri" in nama_produk
    assert "nilai_modal" not in {f.name for f in PosisiStok._meta.get_fields()}


@pytest.fixture
def data_tiruan(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    jmr = Clinic.objects.create(code="jmr", name="JoDerma Jemur Andayani")
    user = User.objects.create_user(username="apoteker1", password="TestPassword123!", display_name="Apoteker")
    UserRole.objects.create(user=user, clinic=jmr, role=Role.APOTEKER)
    UserRole.objects.create(user=user, clinic=jmr, role=Role.STAF)
    services.impor_hasil(_daftar_produk(), b"x", "produk.xls", user)
    services.impor_hasil(_tingkat_persediaan(), b"x", "stok.xls", user, jmr)
    for p in Produk.objects.all():
        PergerakanBulanan.objects.create(clinic=jmr, produk=p, tahun=2026, bulan=9, stok_awal=11, dijual=-10, stok_akhir=1)
    StatusPeriode.objects.update_or_create(clinic=jmr, tahun=2026, bulan=9, defaults={"lengkap": True})
    return jmr, user


def test_import_sets_own_production_flag(data_tiruan):
    assert Produk.objects.get(omnicare_id=1).produksi_sendiri is True
    assert Produk.objects.get(omnicare_id=2).produksi_sendiri is False


def test_order_page_shows_action_without_price_or_supplier(client, data_tiruan):
    jmr, user = data_tiruan
    data = next(c for c in hitung.hitung().cabang if c.clinic == jmr)
    tindakan = {b.produk.nama: b.tindakan for b in hitung.prioritas(data)}
    assert tindakan == {"Krim Racikan Dryn": "Produksi sendiri", "Salep Pabrik": "Order distributor"}

    client.force_login(user)
    for tab in ("order", "transfer", "impor"):
        body = client.get(reverse("stok:index"), {"tab": tab, "cabang": "semua"}).content.decode()
        assert "Rp" not in body and "15000" not in body and "15.000" not in body
        assert "PT Contoh Farma" not in body and "pabrikan" not in body.lower()
    body = client.get(reverse("stok:index"), {"tab": "order", "cabang": "semua"}).content.decode()
    assert "Produksi sendiri" in body and "Order distributor" in body
