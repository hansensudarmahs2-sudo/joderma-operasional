"""Laporan Masuk lintas cabang untuk Direktur dan Owner (masalah nyata 3 Oktober 2026).

Regitta (Citraland) mengirim laporan kerusakan dan masukan, tetapi Direktur (perannya terdaftar
di Jemur) tidak melihatnya: daftar hanya menampilkan cabang aktif, menu Direktur tidak memuat
Komplain/Masukan/Kerusakan, Owner tidak bisa membuka sama sekali, dan notifikasi masukan dikirim
ke pemegang peran AOM *di cabang pengirim* (tidak ada di Citraland).
"""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic, Priority
from issues.models import Issue, IssueStatus, IssueType
from issues.services import create_issue
from notifications.models import Notification
from reports.inbox import inbox_rows
from reports.models import ReportVisibility
from reports.services import create_laporan, create_masukan

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="JoDerma Jemur Andayani")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="JC", name="Joderma Citraland")


@pytest.fixture
def people(jemur, citraland):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM),
        "jean": _user(jemur, "jean", Role.OWNER),
        "regita": _user(citraland, "regita", Role.SUPERVISOR, Role.PERAWAT, Role.STAF),
        "heni": _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT, Role.STAF),
        "yani": _user(jemur, "yani", Role.PERAWAT, Role.STAF),
    }


@pytest.fixture
def citraland_reports(citraland, people):
    r = people["regita"]
    rusak = create_issue(clinic=citraland, issue_type=IssueType.KERUSAKAN, title="AC ruang tindakan bocor",
                         user=r, location="Ruang tindakan", impact="TERBATAS")
    saran = create_issue(clinic=citraland, issue_type=IssueType.MASUKAN, title="Tambah kursi tunggu", user=r)
    keluh = create_issue(clinic=citraland, issue_type=IssueType.KOMPLAIN, title="Pasien menunggu lama",
                         user=r, is_restricted=True, severity=Priority.KRITIS)
    lap = create_laporan(clinic=citraland, user=r, title="Stok tisu habis")
    rahasia = create_laporan(clinic=citraland, user=r, title="Dugaan selisih stok",
                             visibility=ReportVisibility.RAHASIA_AOM)
    msk = create_masukan(clinic=citraland, user=r, title="Usul jadwal piket baru")
    return {"rusak": rusak, "saran": saran, "keluh": keluh, "lap": lap, "rahasia": rahasia, "msk": msk}


def test_director_notified_from_other_branch(people, citraland_reports):
    hansen, jean = people["hansen"], people["jean"]
    refs = set(Notification.objects.filter(user=hansen).values_list("entity_ref", flat=True))
    c = citraland_reports
    assert {f"issue#{c['rusak'].pk}", f"issue#{c['saran'].pk}", f"issue#{c['keluh'].pk}",
            f"laporan#{c['lap'].pk}", f"laporan#{c['rahasia'].pk}", f"masukan#{c['msk'].pk}"} <= refs
    n = Notification.objects.get(user=hansen, entity_ref=f"issue#{c['rusak'].pk}")
    assert "Citraland" in n.title and "Regita" in n.body and n.url.endswith(f"/catatan/{c['rusak'].pk}/")
    secret = Notification.objects.get(user=hansen, entity_ref=f"laporan#{c['rahasia'].pk}")
    assert "Dugaan selisih stok" not in secret.body and "Regita" not in secret.body
    # Owner hanya untuk yang kritis; Koordinator Shift Jemur tidak menerima laporan Citraland.
    assert set(Notification.objects.filter(user=jean).values_list("entity_ref", flat=True)) == {
        f"issue#{c['keluh'].pk}"}
    assert not Notification.objects.filter(user=people["heni"]).exists()


def test_inbox_lists_all_branches_with_reporter(client, people, citraland_reports, jemur):
    create_issue(clinic=jemur, issue_type=IssueType.KERUSAKAN, title="Lampu lobi mati", user=people["heni"],
                 location="Lobi", impact="NORMAL")
    for who in ("hansen", "jean"):
        client.force_login(people[who])
        body = client.get(reverse("reports:inbox")).content.decode()
        for title in ("AC ruang tindakan bocor", "Tambah kursi tunggu", "Pasien menunggu lama", "Stok tisu habis",
                      "Usul jadwal piket baru", "Lampu lobi mati"):
            assert title in body, (who, title)
        assert "Regita" in body and "Heni" in body and "Joderma Citraland" in body


def test_inbox_filters(people, citraland_reports, citraland, jemur):
    hansen = people["hansen"]
    create_issue(clinic=jemur, issue_type=IssueType.KERUSAKAN, title="Lampu lobi mati", user=people["heni"],
                 location="Lobi", impact="NORMAL")
    assert {r["title"] for r in inbox_rows(hansen, clinic=jemur)} == {"Lampu lobi mati"}
    assert {r["title"] for r in inbox_rows(hansen, kind="KERUSAKAN")} == {"AC ruang tindakan bocor",
                                                                          "Lampu lobi mati"}
    assert [r["title"] for r in inbox_rows(hansen, q="kursi")] == ["Tambah kursi tunggu"]
    assert [r["title"] for r in inbox_rows(hansen, q="heni")] == ["Lampu lobi mati"]  # cari nama pelapor
    issue = citraland_reports["saran"]
    issue.status = IssueStatus.SELESAI
    issue.save()
    assert "Tambah kursi tunggu" not in {r["title"] for r in inbox_rows(hansen)}
    assert "Tambah kursi tunggu" in {r["title"] for r in inbox_rows(hansen, only_open=False)}


def test_inbox_forbidden_for_staff_and_coordinator(client, people):
    for who in ("yani", "heni", "regita"):
        client.force_login(people[who])
        assert client.get(reverse("reports:inbox")).status_code == 403


def test_menus_and_dashboards_show_inbox(client, people, citraland_reports):
    client.force_login(people["hansen"])
    body = client.get(reverse("direktur:overview")).content.decode()
    assert 'href="/laporan/masuk/">Inbox</a>' in body and 'id="laporan-masuk"' in body
    assert "Joderma Citraland 6" in body
    client.force_login(people["jean"])
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Inbox" in body and 'id="laporan-masuk"' in body


def test_owner_reads_details_but_cannot_change(client, people, citraland_reports):
    c = citraland_reports
    client.force_login(people["jean"])
    page = client.get(reverse("issues:detail", args=[c["keluh"].pk])).content.decode()
    assert "Pasien menunggu lama" in page and "Regita" in page and "Tampilan baca saja" in page
    assert "Ubah status" not in page and "Penugasan" not in page
    assert client.post(reverse("issues:detail", args=[c["keluh"].pk])).status_code == 403
    assert client.post(reverse("issues:status", args=[c["keluh"].pk]), {"status": "DITINJAU"}).status_code == 403
    assert Issue.objects.get(pk=c["keluh"].pk).status == IssueStatus.BARU
    page = client.get(reverse("reports:laporan_page_detail", args=[c["lap"].pk])).content.decode()
    assert "Stok tisu habis" in page and "Ubah status" not in page
    assert client.post(reverse("reports:laporan_page_detail", args=[c["lap"].pk]),
                       {"status": "CLOSED"}).status_code == 403
    page = client.get(reverse("reports:masukan_page_detail", args=[c["msk"].pk])).content.decode()
    assert "Usul jadwal piket baru" in page
    assert client.post(reverse("reports:masukan_page_detail", args=[c["msk"].pk]),
                       {"aksi": "arsip", "alasan": "x"}).status_code == 403


def test_director_can_act_on_other_branch(client, people, citraland_reports):
    c = citraland_reports
    client.force_login(people["hansen"])
    page = client.get(reverse("issues:detail", args=[c["rusak"].pk])).content.decode()
    assert "Ubah status" in page and "Joderma Citraland" in page and "oleh <strong>Regita</strong>" in page
    page = client.get(reverse("reports:masukan_page_detail", args=[c["msk"].pk])).content.decode()
    assert "Usul jadwal piket baru" in page


def test_issue_list_shows_reporter_and_restricted_for_director(client, people, citraland_reports, citraland):
    client.force_login(people["hansen"])
    client.post(reverse("accounts:switch_clinic"), {"cabang": citraland.pk})
    body = client.get(reverse("issues:list")).content.decode()
    assert "Pasien menunggu lama" in body  # terbatas, tetap terlihat Direktur
    assert "<th>Pelapor</th>" in body and "Regita" in body


def test_same_day_reports_in_both_branches_get_distinct_numbers(people, jemur, citraland):
    """Sebelumnya urutan nomor dihitung per cabang: kerusakan kedua cabang pada hari yang sama sama-sama
    DMG-<tanggal>-001 dan yang kedua gagal tersimpan (nomor unik)."""
    a = create_issue(clinic=jemur, issue_type=IssueType.KERUSAKAN, title="Lampu lobi", user=people["heni"],
                     location="Lobi", impact="NORMAL")
    b = create_issue(clinic=citraland, issue_type=IssueType.KERUSAKAN, title="AC bocor", user=people["regita"],
                     location="Ruang 2", impact="TERBATAS")
    assert a.number != b.number and a.number.endswith("-001") and b.number.endswith("-002")
