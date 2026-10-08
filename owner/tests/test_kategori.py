"""Kategori permintaan/temuan Owner dan task turunannya (keputusan PO 8 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import DEFAULT_TASK_CATEGORIES, ActionItem, ActionItemStatus, Clinic, TaskCategory, local_today
from direktur.services import create_task_from_source
from owner import services
from owner.models import OwnerRequest, RequestKind

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


def _request(owner, category=None, title="Rapikan display produk", kind=RequestKind.PERMINTAAN):
    target = local_today() + dt.timedelta(days=7) if kind == RequestKind.PERMINTAAN else None
    return services.create_request(actor=owner, title=title, target_date=target, kind=kind, category=category)


def _task(req, hansen, jemur, person, title="Langkah 1"):
    return create_task_from_source(
        actor=hansen, clinic=jemur, title=title, target=f"user:{person.pk}",
        source_type="permintaan_owner", source_id=req.pk, source_label=f"P-{req.pk}",
    )


def _form(**extra):
    data = {"judul": "Rapikan gudang", "target": (local_today() + dt.timedelta(days=5)).isoformat()}
    data.update(extra)
    return data


# --- Data awal -----------------------------------------------------------------------


def test_seed_categories_exist_in_order():
    names = list(TaskCategory.objects.order_by("sort_order", "name").values_list("name", flat=True))
    assert names[: len(DEFAULT_TASK_CATEGORIES)] == list(DEFAULT_TASK_CATEGORIES)
    assert names[0] == "Pelayanan pasien" and names[-1] == "Lainnya"
    assert TaskCategory.objects.filter(active=True).count() == 9


# --- Formulir permintaan -----------------------------------------------------------------


def test_request_form_requires_category(client, yohanes):
    client.force_login(yohanes)
    body = client.post(reverse("owner:request_new"), _form()).content.decode()
    assert "Pilih kategori." in body and not OwnerRequest.objects.exists()
    body = client.post(reverse("owner:request_new"), _form(jenis="TEMUAN")).content.decode()
    assert "Pilih kategori." in body and not OwnerRequest.objects.exists()
    cat = _cat("Kebersihan & kerapian")
    res = client.post(reverse("owner:request_new"), _form(kategori=cat.pk))
    req = OwnerRequest.objects.get()
    assert res.status_code == 302 and req.category == cat
    detail = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert "Kebersihan &amp; kerapian" in detail


def test_inactive_category_hidden_and_rejected_via_post(client, yohanes):
    cat = _cat("Pemasaran")
    cat.active = False
    cat.save()
    client.force_login(yohanes)
    page = client.get(reverse("owner:request_new")).content.decode()
    assert f'value="{cat.pk}"' not in page and "Pelayanan pasien" in page
    assert "Atur kategori" in page
    body = client.post(reverse("owner:request_new"), _form(kategori=cat.pk)).content.decode()
    assert "sudah tidak aktif" in body and not OwnerRequest.objects.exists()
    body = client.post(reverse("owner:request_new"), _form(kategori="abc")).content.decode()
    assert "Kategori tidak dikenali." in body and not OwnerRequest.objects.exists()


def test_old_request_without_category_shows_tanpa_kategori(client, yohanes):
    req = _request(yohanes)
    assert req.category is None
    client.force_login(yohanes)
    assert "Tanpa kategori" in client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert "Tanpa kategori" in client.get(reverse("owner:dashboard")).content.decode()


# --- Task mewarisi kategori -----------------------------------------------------------


def test_task_from_request_and_temuan_inherits_category(yohanes, hansen, desy, jemur):
    cat = _cat("Fasilitas & peralatan")
    req = _request(yohanes, category=cat)
    item = _task(req, hansen, jemur, desy)
    assert ActionItem.objects.get(pk=item.pk).category == cat
    temuan = _request(yohanes, category=_cat("Stok & obat"), kind=RequestKind.TEMUAN, title="Obat kedaluwarsa")
    sub = _task(temuan, hansen, jemur, hansen, title="Cek rak")  # sub task Direktur sendiri
    assert ActionItem.objects.get(pk=sub.pk).category.name == "Stok & obat"
    plain = _task(_request(yohanes, title="Tanpa kategori"), hansen, jemur, desy)
    assert ActionItem.objects.get(pk=plain.pk).category is None


def test_task_from_request_detail_form_inherits(client, yohanes, hansen, desy, jemur):
    cat = _cat("SDM & disiplin")
    req = _request(yohanes, category=cat)
    client.force_login(hansen)
    client.post(reverse("owner:request_detail", args=[req.pk]), {
        "aksi": "task", "judul": "Briefing disiplin", "cabang": jemur.pk, "penerima": f"user:{desy.pk}",
    })
    item = ActionItem.objects.get(title="Briefing disiplin")
    assert item.category == cat
    page = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "Kategori: SDM &amp; disiplin" in page


def test_director_changes_task_category(client, yohanes, hansen, desy, jemur):
    req = _request(yohanes, category=_cat("Pemasaran"))
    item = _task(req, hansen, jemur, desy)
    client.force_login(hansen)
    new = _cat("Administrasi & sistem")
    client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "kategori", "kategori": new.pk})
    item.refresh_from_db()
    assert item.category == new
    assert AuditEvent.objects.filter(entity_type="actionitem", entity_id=str(item.pk)).exists()
    # Owner hanya membaca task: tidak boleh mengubah kategori.
    client.force_login(yohanes)
    res = client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "kategori", "kategori": ""})
    assert res.status_code == 403
    item.refresh_from_db()
    assert item.category == new


# --- Daftar Task: saringan Kategori, ringkasan, CSV ---------------------------------------


def test_task_list_category_filter_summary_and_csv(client, yohanes, hansen, desy, jemur):
    cat = _cat("Kebersihan & kerapian")
    with_cat = _task(_request(yohanes, category=cat), hansen, jemur, desy, title="Lantai lengket")
    without = _task(_request(yohanes, title="Lain"), hansen, jemur, desy, title="Pintu macet")
    client.force_login(hansen)
    url = reverse("direktur:tasks")
    page = client.get(url, {"kategori": cat.pk}).content.decode()
    assert "Lantai lengket" in page and "Pintu macet" not in page
    assert "Kategori: Kebersihan &amp; kerapian" in page  # chip ringkasan saringan
    assert 'name="kategori"' in page
    page = client.get(url, {"kategori": "tanpa"}).content.decode()
    assert "Pintu macet" in page and "Lantai lengket" not in page and "Kategori: Tanpa kategori" in page
    page = client.get(url, {"kategori": "x1"}).content.decode()  # tidak valid -> diabaikan
    assert "Pintu macet" in page and "Lantai lengket" in page
    res = client.get(url, {"unduh": "csv"})
    csv = b"".join(res.streaming_content).decode("utf-8")
    header = csv.splitlines()[0]
    assert "Kategori" in header.split(",")
    line = next(row for row in csv.splitlines() if row.startswith(f"{with_cat.pk},"))
    assert "Kebersihan & kerapian" in line
    assert next(row for row in csv.splitlines() if row.startswith(f"{without.pk},"))


# --- Dashboard Owner: Per kategori ---------------------------------------------------------


def test_owner_dashboard_per_category_counts(client, yohanes, hansen, desy, jemur):
    clean = _cat("Kebersihan & kerapian")
    open_req = _request(yohanes, category=clean, title="Buka")
    _task(open_req, hansen, jemur, desy)
    done_req = _request(yohanes, category=clean, title="Beres")
    item = _task(done_req, hansen, jemur, desy)
    ActionItem.objects.filter(pk=item.pk).update(status=ActionItemStatus.SELESAI)
    _request(yohanes, title="Lama tanpa kategori")
    rows = services.category_rows(yohanes)
    assert [(r["name"], r["open"], r["done"]) for r in rows] == [
        ("Kebersihan & kerapian", 1, 1), ("Tanpa kategori", 1, 0)]
    client.force_login(yohanes)
    page = client.get(reverse("owner:dashboard")).content.decode()
    assert "Per kategori" in page and "Pelayanan pasien" not in page.split("Per kategori")[1].split("</section>")[0]


# --- Halaman Atur kategori ----------------------------------------------------------------


def test_settings_page_access(client, yohanes, hansen, desy, jemur):
    url = reverse("direktur:kategori")
    for user in (yohanes, hansen):
        client.force_login(user)
        assert client.get(url).status_code == 200
    staf = _user(jemur, "staf1", Role.STAF)
    spv = _user(jemur, "spv1", Role.SUPERVISOR, Role.STAF)
    for user in (staf, spv, desy):
        client.force_login(user)
        assert client.get(url).status_code == 403
        assert client.post(url, {"aksi": "tambah", "nama": "Ilegal"}).status_code == 403
    assert not TaskCategory.objects.filter(name="Ilegal").exists()


def test_settings_add_rename_reorder_deactivate(client, yohanes, hansen):
    url = reverse("direktur:kategori")
    client.force_login(yohanes)
    client.post(url, {"aksi": "tambah", "nama": "  Keamanan  "})
    cat = TaskCategory.objects.get(name="Keamanan")
    assert cat.active and cat.sort_order > _cat("Lainnya").sort_order
    assert AuditEvent.objects.filter(entity_type="taskcategory", entity_id=str(cat.pk), action="CREATE").exists()
    body = client.post(url, {"aksi": "tambah", "nama": "keamanan"}, follow=True).content.decode()
    assert "sudah ada" in body and TaskCategory.objects.filter(name__iexact="keamanan").count() == 1
    req = _request(yohanes, category=cat)
    client.force_login(hansen)
    client.post(url, {"aksi": "ubah", "kategori": cat.pk, "nama": "Keamanan klinik", "urutan": "5"})
    cat.refresh_from_db()
    assert (cat.name, cat.sort_order, cat.active) == ("Keamanan klinik", 5, False)  # aktif tidak dicentang
    assert AuditEvent.objects.filter(entity_type="taskcategory", entity_id=str(cat.pk), action="UPDATE").exists()
    req.refresh_from_db()
    assert req.category == cat  # data lama tetap
    client.force_login(yohanes)
    assert f'value="{cat.pk}"' not in client.get(reverse("owner:request_new")).content.decode()
    client.post(url, {"aksi": "ubah", "kategori": cat.pk, "nama": "Keamanan klinik", "urutan": "5", "aktif": "1"})
    cat.refresh_from_db()
    assert cat.active
    body = client.post(url, {"aksi": "ubah", "kategori": cat.pk, "nama": "Keamanan klinik", "urutan": "x"},
                       follow=True).content.decode()
    assert "Urutan harus angka" in body


def test_director_menu_links_to_categories(client, hansen):
    client.force_login(hansen)
    assert reverse("direktur:kategori") in client.get(reverse("direktur:overview")).content.decode()
