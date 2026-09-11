"""Test yang menjaga dokumentasi tetap sinkron dengan kode.

Dokumen yang salah lebih berbahaya daripada dokumen yang tidak ada, karena orang
mengikutinya tanpa curiga. Test di sini menangkap jenis kekeliruan yang paling
sering terjadi: tautan yang menunjuk berkas terhapus, perintah manage.py yang
sudah tidak ada, dan daftar kapabilitas yang tertinggal saat kode berubah.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.core.management import get_commands

REPO = Path(__file__).resolve().parent.parent.parent
DOCS = sorted(REPO.glob("*.md")) + sorted((REPO / "docs").glob("*.md"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ada_dokumen_untuk_tiap_peran():
    """Setiap peran manusia punya panduannya sendiri."""
    for nama in ("panduan-staf.md", "panduan-supervisor.md", "panduan-admin.md"):
        assert (REPO / "docs" / nama).exists(), f"{nama} hilang"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_tautan_internal_tidak_rusak(doc: Path):
    for link in re.findall(r"\]\(([^)#][^)]*)\)", _text(doc)):
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        target = (doc.parent / link.split("#")[0]).resolve()
        assert target.exists(), f"{doc.name} menunjuk berkas yang tidak ada: {link}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_perintah_manage_py_benar_benar_ada(doc: Path):
    tersedia = set(get_commands())
    for perintah in re.findall(r"manage\.py\s+([a-z_]+)", _text(doc)):
        assert perintah in tersedia, f"{doc.name} menyebut perintah tidak dikenal: {perintah}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_script_yang_dirujuk_ada(doc: Path):
    for ref in re.findall(r"scripts/[A-Za-z0-9_.-]+", _text(doc)):
        assert (REPO / ref.rstrip(".,`)")).exists(), f"{doc.name} merujuk {ref} yang tidak ada"


def test_semua_kapabilitas_terdokumentasi():
    """Kapabilitas baru harus dijelaskan, bukan diam-diam muncul di UI."""
    from accounts.models import Capability

    teks = _text(REPO / "docs" / "peran-dan-akses.md")
    for cap in Capability:
        assert cap.value in teks, (
            f"Kapabilitas {cap.value} belum dijelaskan di docs/peran-dan-akses.md"
        )


def test_semua_peran_terdokumentasi():
    from accounts.models import Role

    teks = _text(REPO / "docs" / "peran-dan-akses.md")
    for role in Role:
        assert role.value in teks, f"Peran {role.value} belum dijelaskan di docs/peran-dan-akses.md"


def test_jumlah_test_yang_diklaim_readme_masuk_akal():
    """README menyebut jumlah test; angka yang basi menyesatkan pembaca.

    Diperiksa longgar -- yang dicegah adalah angka yang jauh tertinggal,
    bukan selisih satu-dua test.
    """
    teks = _text(REPO / "README.md")
    m = re.search(r"pytest\s+#\s*(\d+)\s*test", teks)
    assert m, "README tidak lagi menyebut jumlah test dalam format yang dikenali"
    diklaim = int(m.group(1))

    # Dihitung dari berkas, bukan dengan menjalankan pytest di dalam pytest.
    # Fungsi ber-parametrize menghasilkan lebih dari satu test saat dijalankan,
    # jadi jumlah sebenarnya selalu >= jumlah definisi. Yang dicegah di sini
    # adalah angka README yang jauh tertinggal, bukan selisih kecil.
    definisi = 0
    for f in REPO.rglob("test*.py"):
        if ".venv" in f.parts:
            continue
        definisi += len(re.findall(r"^def test_", f.read_text(encoding="utf-8"), re.M))

    assert diklaim >= definisi, (
        f"README mengklaim {diklaim} test, sementara ada {definisi} definisi test "
        "(fungsi ber-parametrize menghasilkan lebih banyak lagi). Perbarui README."
    )
    assert diklaim <= definisi * 3, (
        f"README mengklaim {diklaim} test, jauh di atas {definisi} definisi yang ada. "
        "Perbarui README."
    )


def test_tombol_catatan_di_panduan_sesuai_template():
    """Label tombol di panduan harus benar-benar ada di UI.

    Tombol input catatan pernah berubah tanpa panduannya ikut diperbarui,
    sehingga staf mencari tombol yang sudah tidak ada.
    """
    tpl = (REPO / "templates" / "issues" / "list.html").read_text(encoding="utf-8")
    panduan = _text(REPO / "docs" / "panduan-staf.md")

    for label in ("Catat komplain baru", "Tulis masukan/saran", "Laporkan kerusakan"):
        assert label in tpl, f"Template tidak lagi memuat tombol {label!r}"
        assert label in panduan, f"panduan-staf.md belum menyebut tombol {label!r}"


def test_dokumen_deployment_menyebut_port_yang_dipakai():
    """Port akses klinik harus tercatat, bukan hanya diketahui lisan."""
    teks = _text(REPO / "docs" / "deployment-klinik.md")
    assert "8443" in teks, "URL akses klinik (port 8443) tidak terdokumentasi"
    assert "serve_clinic.sh" in teks


def test_indeks_dokumentasi_menautkan_semua_dokumen_docs():
    """Dokumen baru di docs/ harus muncul di indeks, jika tidak ia tidak akan ditemukan."""
    indeks = _text(REPO / "docs" / "README.md")
    for doc in (REPO / "docs").glob("*.md"):
        if doc.name == "README.md":
            continue
        assert doc.name in indeks, f"{doc.name} belum ditautkan di docs/README.md"
