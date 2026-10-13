"""Dashboard Owner: kartu berita per bidang, saringan daftar, dan Atur tampilan (keputusan PO 13 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import ActionItem, Clinic, Priority, TaskCategory, local_today
from direktur import services as direktur
from direktur.models import Decider, Decision
from direktur.services import create_task_from_source
from owner import services, tampilan
from owner.models import DashboardLayout, OwnerRequest, RequestKind

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.PIC, Role.FRONT_DESK, display_name="Desy")


def _cat(name):
    return TaskCategory.objects.get(name=name)


def _req(owner, title, category=None, *, urgent=False, days=10, kind=RequestKind.PERMINTAAN):
    """Permintaan dengan target `days` hari dari sekarang (negatif = sudah lewat)."""
    req = services.create_request(actor=owner, title=title, target_date=None if kind == RequestKind.TEMUAN else local_today() + dt.timedelta(days=30),
                                  kind=kind, urgent=urgent, category=_cat(category) if category else None)
    OwnerRequest.objects.filter(pk=req.pk).update(target_date=local_today() + dt.timedelta(days=days))
    return OwnerRequest.objects.get(pk=req.pk)


def _task(req, hansen, jemur, person, priority=Priority.SEDANG):
    return create_task_from_source(
        actor=hansen, clinic=jemur, title=f"Langkah {req.title}", target=f"user:{person.pk}", priority=priority,
        source_type="permintaan_owner", source_id=req.pk, source_label=f"P-{req.pk}",
    )


def _cards(user):
    return tampilan.news_cards(services.all_progress(user))


# --- Kartu berita ------------------------------------------------------------------------------


def test_categories_map_to_areas(yohanes):
    for name, area in [("Fasilitas & peralatan", "sarana"), ("Kebersihan & kerapian", "sarana"),
                       ("Pelayanan pasien", "alur"), ("Administrasi & sistem", "alur"),
                       ("SDM & disiplin", "sdm"), ("Keuangan & kas", "lainnya"), ("Stok & obat", "lainnya"),
                       ("Pemasaran", "lainnya"), ("Lainnya", "lainnya")]:
        assert tampilan.area_of(OwnerRequest(category=_cat(name))) == area
    assert tampilan.area_of(OwnerRequest()) == "lainnya"  # tanpa kategori
    renamed = TaskCategory.objects.create(name="Kategori baru")
    assert tampilan.area_of(OwnerRequest(category=renamed)) == "lainnya"


def test_card_headline_is_most_important(yohanes, hansen, desy, jemur):
    _req(yohanes, "Lampu parkir mati", "Fasilitas & peralatan", days=2)
    _req(yohanes, "Wastafel retak", "Fasilitas & peralatan", days=-4)
    _req(yohanes, "AC bocor", "Fasilitas & peralatan", urgent=True, days=5)
    _req(yohanes, "Kursi roda", "Kebersihan & kerapian", days=20)
    sarana = _cards(yohanes)[0]
    assert sarana["key"] == "sarana" and sarana["count"] == 4 and sarana["level"] == "merah"
    assert sarana["top"]["request"].title == "AC bocor" and sarana["reason"] == "Mendesak"
    assert [r["request"].title for r in sarana["next"]] == ["Wastafel retak", "Lampu parkir mati"]
    assert sarana["more"] == 1


def test_late_beats_high_priority_beats_nearest_target(yohanes, hansen, desy, jemur):
    near = _req(yohanes, "Antrean sore", "Pelayanan pasien", days=1)
    high = _req(yohanes, "SOP biaya", "Pelayanan pasien", days=25)
    _task(high, hansen, jemur, desy, priority=Priority.TINGGI)
    _task(near, hansen, jemur, desy)
    late = _req(yohanes, "Form rujukan", "Administrasi & sistem", days=-1)
    alur = _cards(yohanes)[1]
    assert [alur["top"]["request"].pk] + [r["request"].pk for r in alur["next"]] == [late.pk, high.pk, near.pk]
    rows = {r["request"].pk: r for r in services.all_progress(yohanes)}
    assert tampilan.reason(rows[high.pk]) == ("Prioritas tinggi", "warn")
    assert tampilan.reason(rows[late.pk]) == ("Lewat 1 hari", "err")


def test_card_levels(yohanes):
    _req(yohanes, "Seragam", "SDM & disiplin", days=5)
    _req(yohanes, "Jadwal pelatihan", "Pelayanan pasien", days=20)
    cards = {c["key"]: c for c in _cards(yohanes)}
    assert cards["sdm"]["level"] == "kuning" and cards["alur"]["level"] == "biru"


def test_empty_area_replaced_by_busiest_other_category(yohanes):
    _req(yohanes, "AC bocor", "Fasilitas & peralatan")
    _req(yohanes, "Seragam", "SDM & disiplin")
    _req(yohanes, "Selisih komisi", "Keuangan & kas")
    _req(yohanes, "Setoran telat", "Keuangan & kas")
    _req(yohanes, "Obat hampir habis", "Stok & obat")
    cards = _cards(yohanes)
    assert [c["key"] for c in cards] == ["sarana", f"kat-{_cat('Keuangan & kas').pk}", "sdm", "lainnya"]
    assert cards[1]["label"] == "Keuangan & kas" and cards[1]["replaces"] == "Alur dan SOP" and cards[1]["count"] == 2
    assert cards[3]["count"] == 1 and cards[3]["top"]["request"].title == "Obat hampir habis"


def test_empty_area_without_replacement_is_green(yohanes):
    _req(yohanes, "AC bocor", "Fasilitas & peralatan")
    cards = _cards(yohanes)
    assert [c["key"] for c in cards] == ["sarana", "alur", "sdm", "lainnya"]
    assert [c["empty"] for c in cards] == [False, True, True, True]
    assert cards[1]["level"] == "hijau"


def test_only_open_requests_count(yohanes, hansen, desy, jemur):
    done = _req(yohanes, "Sudah beres", "Fasilitas & peralatan")
    item = _task(done, hansen, jemur, desy)
    ActionItem.objects.filter(pk=item.pk).update(status="SELESAI")
    assert _cards(yohanes) == []


def test_page_shows_cards_and_all_clear(client, yohanes):
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Tidak ada temuan atau permintaan yang terbuka" in body and 'class="dash-nav"' in body
    _req(yohanes, "AC ruang tindakan bocor", "Fasilitas & peralatan", urgent=True, kind=RequestKind.TEMUAN)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "news-merah" in body and "AC ruang tindakan bocor" in body and "?bidang=sarana#bag-permintaan" in body
    assert body.index('id="ringkasan"') < body.index('id="bag-permintaan"')


# --- Saringan daftar ---------------------------------------------------------------------------


def test_list_filter_by_area_and_category(client, yohanes):
    _req(yohanes, "AC bocor", "Fasilitas & peralatan")
    _req(yohanes, "Seragam lusuh", "SDM & disiplin")
    _req(yohanes, "Selisih komisi", "Keuangan & kas")
    client.force_login(yohanes)
    url = reverse("owner:dashboard")
    body = client.get(url, {"bidang": "sdm"}).content.decode()
    listed = body[body.index('id="bag-permintaan"'):]
    assert "Seragam lusuh" in listed and "AC bocor" not in listed and "Selisih komisi" not in listed
    body = client.get(url, {"bidang": f"kat-{_cat('Keuangan & kas').pk}"}).content.decode()
    listed = body[body.index('id="bag-permintaan"'):]
    assert "Selisih komisi" in listed and "Seragam lusuh" not in listed
    body = client.get(url, {"bidang": "ngawur"}).content.decode()
    listed = body[body.index('id="bag-permintaan"'):]
    assert "Seragam lusuh" in listed and "AC bocor" in listed  # saringan tak dikenal diabaikan


def test_list_sorted_by_importance(client, yohanes):
    _req(yohanes, "Biasa saja", "Pemasaran", days=20)
    _req(yohanes, "Sudah lewat", "Pemasaran", days=-3)
    _req(yohanes, "Darurat", "Pemasaran", urgent=True, days=15)
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    listed = body[body.index('id="bag-permintaan"'):]
    assert listed.index("Darurat") < listed.index("Sudah lewat") < listed.index("Biasa saja")


# --- Atur tampilan -----------------------------------------------------------------------------


def _order(body):
    keys = [k for k in tampilan.SECTION_KEYS if f'id="bag-{k}"' in body]
    return sorted(keys, key=lambda k: body.index(f'id="bag-{k}"'))


def test_default_layout_shows_sections_in_default_order(client, yohanes):
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert _order(body) == ["inbox", "cabang", "matriks", "agenda", "capaian"]  # bagian lain kosong, tidak ditampilkan
    assert "Atur tampilan" in body


def test_owner_saves_order_and_hidden_sections(client, yohanes):
    client.force_login(yohanes)
    order = ["capaian", "cabang", "matriks"] + [k for k in tampilan.SECTION_KEYS if k not in ("capaian", "cabang", "matriks")]
    shown = [k for k in tampilan.SECTION_KEYS if k != "matriks"]
    res = client.post(reverse("owner:dashboard_layout"), {"urutan": order, "tampil": shown})
    assert res.status_code == 302
    saved = DashboardLayout.objects.get(user=yohanes).sections
    assert [s["key"] for s in saved] == order and not next(s for s in saved if s["key"] == "matriks")["shown"]
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert _order(body) == ["capaian", "cabang", "inbox", "agenda"]
    assert AuditEvent.objects.filter(entity_type="dashboardlayout", entity_id=str(yohanes.pk)).exists()
    client.post(reverse("owner:dashboard_layout"), {"aksi": "bawaan"})
    assert not DashboardLayout.objects.filter(user=yohanes).exists()
    assert _order(client.get(reverse("owner:dashboard")).content.decode()) == ["inbox", "cabang", "matriks", "agenda", "capaian"]


def test_layout_ignores_unknown_keys_and_appends_new_sections(yohanes):
    DashboardLayout.objects.create(user=yohanes, sections=[{"key": "capaian", "shown": False}, {"key": "hantu"}, "x"])
    layout = tampilan.layout_for(yohanes)
    assert [s["key"] for s in layout][0] == "capaian" and not layout[0]["shown"]
    assert len(layout) == len(tampilan.SECTION_KEYS) and all(s["shown"] for s in layout[1:])
    tampilan.save_layout(yohanes, ["hantu", "agenda"], {"agenda"})
    saved = DashboardLayout.objects.get(user=yohanes).sections
    assert saved[0] == {"key": "agenda", "shown": True} and len(saved) == len(tampilan.SECTION_KEYS)
    assert all(not s["shown"] for s in saved[1:])


def test_hidden_section_with_late_item_flagged_in_nav(client, yohanes, hansen, jemur):
    d = direktur.create_decision(actor=hansen, title="Lembur hari raya", decider=Decider.OWNER, clinic=jemur,
                                 background="Perlu putusan.")
    Decision.objects.filter(pk=d.pk).update(needed_by=local_today() - dt.timedelta(days=1))
    client.force_login(yohanes)
    tampilan.save_layout(yohanes, list(tampilan.SECTION_KEYS), set(tampilan.SECTION_KEYS) - {"keputusan"})
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert 'id="bag-keputusan"' not in body
    assert "?tampil=keputusan#bag-keputusan" in body and "Keputusan · 1 lewat" in body
    body = client.get(reverse("owner:dashboard"), {"tampil": "keputusan"}).content.decode()
    assert 'id="bag-keputusan"' in body and "Lembur hari raya" in body


def test_hidden_section_without_problem_not_flagged(client, yohanes):
    client.force_login(yohanes)
    tampilan.save_layout(yohanes, list(tampilan.SECTION_KEYS), set(tampilan.SECTION_KEYS) - {"capaian"})
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert 'id="bag-capaian"' not in body and "tampil=capaian" not in body


def test_only_owner_can_arrange(client, hansen, desy, yohanes):
    url = reverse("owner:dashboard_layout")
    for who in (hansen, desy):
        client.force_login(who)
        assert client.post(url, {"urutan": ["capaian"], "tampil": []}).status_code == 403
    assert not DashboardLayout.objects.exists()
    client.force_login(hansen)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Atur tampilan" not in body
    client.force_login(desy)
    assert client.get(reverse("owner:dashboard")).status_code == 403
    client.force_login(yohanes)
    assert client.get(url).status_code == 302  # GET tidak mengubah apa pun


def test_layout_is_per_user(client, yohanes, jemur):
    jean = _user(jemur, "jean", Role.OWNER, display_name="Jean")
    tampilan.save_layout(yohanes, list(tampilan.SECTION_KEYS), set())
    client.force_login(jean)
    assert _order(client.get(reverse("owner:dashboard")).content.decode()) == ["inbox", "cabang", "matriks", "agenda", "capaian"]



def test_list_does_not_repeat_late_tag(client, yohanes):
    _req(yohanes, "Telat biasa", "Pemasaran", days=-2)
    _req(yohanes, "Telat mendesak", "Pemasaran", urgent=True, days=-1)
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    listed = body[body.index('id="bag-permintaan"'):]
    assert "Lewat 2 hari" not in listed  # kolom kanan sudah menandai "Lewat target"
    assert '<span class="tag err">Mendesak</span>' in listed


def test_nav_alert_words(client, yohanes):
    from owner.views import ALERT_WORDS

    assert ALERT_WORDS == {"inbox": "kritis", "cabang": "merah"}
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    nav = body[body.index('class="dash-nav"'):body.index('id="ringkasan"')]
    assert "#bag-cabang" in nav and "lewat</span>" not in nav.split("#bag-cabang")[1].split("</a>")[0]
