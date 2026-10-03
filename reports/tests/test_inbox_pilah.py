"""Paket B tahap 2: Inbox satu pintu dengan pilah oleh Direktur Operasional, dan temuan Owner."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core.models import ActionItem, Clinic
from direktur import dashboard
from direktur import services as direktur
from direktur.models import Decider
from issues.models import Issue, IssueStatus, IssueType, IssueUpdate
from issues.services import create_issue
from notifications.models import Notification
from owner.models import OwnerRequest, RequestKind
from owner.services import create_request, progress
from reports import triage
from reports.inbox import find_row, inbox_rows, open_counts
from reports.models import ForwardTo, InboxTriage, TriageAction

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
        "yohanes": _user(jemur, "yohanes", Role.OWNER),
        "heni": _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT, Role.STAF),
        "yani": _user(jemur, "yani", Role.PERAWAT, Role.STAF),
        "regita": _user(citraland, "regita", Role.SUPERVISOR, Role.STAF),
    }


def _rows(user, **kw):
    return {r["title"]: r for r in inbox_rows(user, **kw)}


def _damage(clinic, user, title="AC ruang tindakan bocor"):
    return create_issue(clinic=clinic, issue_type=IssueType.KERUSAKAN, title=title, user=user,
                        location="Ruang tindakan", impact="TERBATAS")


# --- Temuan Owner ---------------------------------------------------------------

def test_owner_finding_without_target_reaches_inbox(people, jemur):
    y, h = people["yohanes"], people["hansen"]
    finding = create_request(actor=y, kind=RequestKind.TEMUAN, title="Tempat sampah lobi penuh", clinic=jemur,
                             urgent=True)
    assert finding.target_date is None and progress(finding)["late"] is False
    with pytest.raises(ValidationError):
        create_request(actor=y, title="Permintaan tanpa target")
    note = Notification.objects.get(user=h, entity_ref=f"permintaan_owner:{finding.pk}")
    assert note.title == "Temuan Owner baru (mendesak): Tempat sampah lobi penuh" and "tanpa target" in note.body
    row = _rows(h)["Tempat sampah lobi penuh"]
    assert row["kind_label"] == "Temuan Owner" and row["state"] == "belum" and row["critical"]
    assert row["clinic"] == jemur and row["reporter"] == "Yohanes"


def test_owner_finding_form(client, people, jemur):
    client.force_login(people["yohanes"])
    page = client.get(reverse("owner:request_new"), {"jenis": "TEMUAN"}).content.decode()
    assert "Catat temuan" in page and 'name="target" required' not in page
    res = client.post(reverse("owner:request_new"), {"jenis": "TEMUAN", "judul": "Kursi tunggu sobek",
                                                     "cabang": jemur.pk, "mendesak": "1"})
    req = OwnerRequest.objects.get(title="Kursi tunggu sobek")
    assert res.status_code == 302 and req.kind == RequestKind.TEMUAN and req.clinic == jemur and req.urgent
    dash = client.get(reverse("owner:dashboard")).content.decode()
    assert "Kursi tunggu sobek" in dash and "Tanpa target" in dash and "Mendesak" in dash
    # Permintaan biasa tetap wajib target.
    client.post(reverse("owner:request_new"), {"jenis": "PERMINTAAN", "judul": "Tanpa target"})
    assert not OwnerRequest.objects.filter(title="Tanpa target").exists()


# --- Pilah ----------------------------------------------------------------------------

def test_assign_issue_creates_task_and_moves_status(people, jemur, citraland):
    h = people["hansen"]
    issue = _damage(citraland, people["regita"])
    row = find_row(h, "issue", issue.pk)
    t = triage.assign(row, actor=h, clinic=citraland, title="Servis AC ruang tindakan",
                      target=f"user:{people['regita'].pk}", priority="TINGGI")
    task = t.task
    assert task.source_type == "issue" and task.source_id == issue.pk and task.priority == "TINGGI"
    assert dashboard.reporters([task])[task.pk] == people["regita"]
    assert dashboard.source_url(task) == reverse("issues:detail", args=[issue.pk])
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITUGASKAN  # Baru -> Ditriase -> Ditugaskan
    assert IssueUpdate.objects.filter(issue=issue, note__contains="Servis AC ruang tindakan").exists()
    assert "AC ruang tindakan bocor" not in _rows(h, state="belum")
    assert _rows(h, state="sudah")["AC ruang tindakan bocor"]["triage"].task == task
    assert AuditEvent.objects.filter(entity_type="inboxtriage", entity_id=str(t.pk)).exists()


def test_forward_is_watched_until_closed(people, jemur):
    h = people["hansen"]
    issue = create_issue(clinic=jemur, issue_type=IssueType.KOMPLAIN, title="Harga krim naik tanpa info",
                         user=people["heni"])
    row = find_row(h, "issue", issue.pk)
    with pytest.raises(ValidationError):
        triage.forward(row, actor=h, to=ForwardTo.LAINNYA)
    triage.forward(row, actor=h, to=ForwardTo.APOTEKER, note="dikirim ke apt. Elvira")
    issue.refresh_from_db()
    assert issue.status == IssueStatus.DITINJAU
    assert _rows(h, state="dipantau")["Harga krim naik tanpa info"]["triage"].forwarded_to == ForwardTo.APOTEKER
    assert open_counts(h)["watching"] == 1


def test_to_meeting_and_dismiss(people, jemur):
    h = people["hansen"]
    a = _damage(jemur, people["heni"], "Ganti vendor limbah?")
    b = _damage(jemur, people["heni"], "Lampu kedip sekali")
    t = triage.to_meeting(find_row(h, "issue", a.pk), actor=h)
    assert t.decision.decider == Decider.RAPAT_BERSAMA and t.decision.clinic == jemur
    assert t.decision.reference == a.number
    assert [r["decision"] for r in dashboard.meeting_agenda(h)["rapat"]] == [t.decision]
    with pytest.raises(ValidationError):
        triage.dismiss(find_row(h, "issue", b.pk), actor=h, reason=" ")
    triage.dismiss(find_row(h, "issue", b.pk), actor=h, reason="sudah normal")
    b.refresh_from_db()
    assert b.status == IssueStatus.BARU  # status tidak diubah; alasan tercatat di riwayat
    assert IssueUpdate.objects.filter(issue=b, note__contains="sudah normal").exists()
    assert set(_rows(h, state="belum")) == set()


def test_retriage_replaces_result(people, jemur):
    h = people["hansen"]
    issue = _damage(jemur, people["heni"])
    row = find_row(h, "issue", issue.pk)
    triage.forward(row, actor=h, to=ForwardTo.KEUANGAN)
    triage.assign(find_row(h, "issue", issue.pk), actor=h, clinic=jemur, title="Servis AC",
                  target=f"user:{people['heni'].pk}")
    t = InboxTriage.objects.get(source_type="issue", source_id=issue.pk)
    assert t.action == TriageAction.TUGASKAN and t.forwarded_to == "" and t.task is not None


def test_owner_request_assign_then_more_tasks(client, people, jemur):
    h, y = people["hansen"], people["yohanes"]
    req = create_request(actor=y, title="Rapikan display produk", target_date=dt.date.today() + dt.timedelta(days=7))
    triage.assign(find_row(h, "permintaan_owner", req.pk), actor=h, clinic=jemur, title="Langkah 1: foto display",
                  target=f"user:{people['yani'].pk}")
    assert progress(req)["state"] == "running" and progress(req)["total"] == 1
    client.force_login(h)
    page = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert "Tambah task" in page and "Diputuskan dan ditugaskan" in page
    client.post(reverse("owner:request_detail", args=[req.pk]), {
        "aksi": "task", "cabang": jemur.pk, "judul": "Langkah 2: susun ulang rak",
        "penerima": f"user:{people['yani'].pk}", "prioritas": "SEDANG"})
    assert progress(req)["total"] == 2
    task = ActionItem.objects.get(title="Langkah 2: susun ulang rak")
    assert task.source_type == "permintaan_owner" and dashboard.reporters([task])[task.pk] == y
    client.force_login(y)
    assert "Tambah task" not in client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    client.post(reverse("owner:request_detail", args=[req.pk]), {
        "aksi": "task", "cabang": jemur.pk, "judul": "Dari Owner", "penerima": f"user:{people['yani'].pk}"})
    assert not ActionItem.objects.filter(title="Dari Owner").exists()


def test_director_notes_only_for_author(people, jemur):
    h, y = people["hansen"], people["yohanes"]
    note = direktur.create_note(author=h, body="Cek stok masker besok", clinic=jemur)
    assert _rows(h)["Cek stok masker besok"]["kind"] == "CATATAN"
    assert "Cek stok masker besok" not in _rows(y)
    other = _user(jemur, "direktur2", Role.AOM)
    assert "Cek stok masker besok" not in _rows(other)
    t = triage.assign(find_row(h, "catatan_direktur", note.pk), actor=h, clinic=jemur, title="Cek stok masker",
                      target=f"user:{people['heni'].pk}")
    note.refresh_from_db()
    assert note.converted_task == t.task and t.task.source_type == "catatan_direktur"


def test_handled_items_count_as_triaged(people, jemur):
    from issues.services import change_status

    h = people["hansen"]
    issue = create_issue(clinic=jemur, issue_type=IssueType.KOMPLAIN, title="Antrian lama", user=people["heni"])
    change_status(issue, user=people["heni"], to_status=IssueStatus.DITINJAU)
    row = _rows(h, state="sudah")["Antrian lama"]
    assert row["triage"] is None and "ditangani di cabang" in row["handled"]


def test_triage_page_and_permissions(client, people, jemur):
    h = people["hansen"]
    issue = _damage(jemur, people["heni"])
    url = reverse("reports:inbox_triage", args=["issue", issue.pk])
    client.force_login(h)
    inbox = client.get(reverse("reports:inbox")).content.decode()
    assert url in inbox and "Belum dipilah · 1" in inbox
    page = client.get(url).content.decode()
    for text in ("Putuskan dan tugaskan", "Teruskan dan pantau", "Bawa ke rapat Kamis", "Tidak ditindaklanjuti",
                 "Apoteker (apotek, stok, harga obat)", "kas sampai Rp1 juta"):
        assert text in page
    res = client.post(url, {"aksi": "tugaskan", "cabang": jemur.pk, "judul": "Servis AC",
                            "penerima": f"user:{people['heni'].pk}", "prioritas": "SEDANG"})
    assert res.status_code == 302 and ActionItem.objects.filter(title="Servis AC", source_type="issue").exists()
    overview = client.get(reverse("direktur:overview")).content.decode()
    assert "semua sudah dipilah" in overview
    assert client.get(reverse("reports:inbox_triage", args=["xx", 1])).status_code == 404
    for who in ("yohanes", "heni"):
        client.force_login(people[who])
        assert client.get(url).status_code in (302, 403)
        client.post(url, {"aksi": "tidak", "alasan": "x"})
    assert InboxTriage.objects.get(source_type="issue", source_id=issue.pk).action == TriageAction.TUGASKAN
    with pytest.raises(PermissionDenied):
        triage.dismiss(find_row(h, "issue", issue.pk), actor=people["yohanes"], reason="x")
    client.force_login(people["yohanes"])
    page = client.get(reverse("reports:inbox"), {"pilah": "semua"}).content.decode()
    assert "AC ruang tindakan bocor" in page and "Catatan Direktur" not in page and url not in page
