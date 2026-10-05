"""5 Okt 2026: item Inbox bisa dijadikan kebijakan (tanpa penugasan, tanpa nama pelapor) dan
Direktur Operasional bisa menjadi penerima task di kedua cabang walau perannya tercatat di satu cabang."""
from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic, TaskAudienceType
from core.task_services import create_task, resolve_task_recipients
from direktur import services as direktur
from direktur.models import Decider, DecisionStatus
from issues.models import IssueType
from issues.services import assign_issue, create_issue
from notifications.models import Notification
from reports import triage
from reports.inbox import find_row, inbox_rows
from reports.models import InboxTriage, TriageAction
from reports.services import create_masukan

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, display=None):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=display or name.title())
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
        "hansen": _user(jemur, "hansen1", Role.AOM, display="Hansen"),
        "yohanes": _user(jemur, "yohanes", Role.OWNER),
        "heni": _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT, Role.STAF, display="Heni Pelapor"),
        "yani": _user(jemur, "yani", Role.PERAWAT, Role.STAF),
        "regita": _user(citraland, "regita", Role.SUPERVISOR, Role.STAF),
        "dewi": _user(citraland, "dewi", Role.FRONT_DESK, Role.STAF),
    }


def _masukan_row(people, jemur):
    m = create_masukan(clinic=jemur, user=people["heni"], title="Surat keterangan kontrol",
                       description="Usul Heni: surat kontrol disimpan soft file dan dicetak.")
    return m, find_row(people["hansen"], "masukan", m.pk)


def test_masukan_becomes_policy_announced_to_all_without_reporter(client, people, jemur, citraland):
    hansen = people["hansen"]
    m, row = _masukan_row(people, jemur)
    client.force_login(hansen)
    url = reverse("reports:inbox_triage", args=["masukan", m.pk])
    page = client.get(url).content.decode()
    assert "Jadikan kebijakan" in page and "Nama pelapor dan uraian aslinya tidak ikut" in page

    resp = client.post(url, {"aksi": "kebijakan", "judul_kebijakan": "Surat keterangan kontrol",
                             "isi_kebijakan": "Surat keterangan kontrol disimpan sebagai soft file dan dicetak.",
                             "cabang_kebijakan": "semua", "berlaku": "2026-10-06"})
    assert resp.status_code == 302
    t = InboxTriage.objects.get(source_type="masukan", source_id=m.pk)
    d = t.decision
    assert t.action == TriageAction.KEBIJAKAN and t.task is None
    assert d.status == DecisionStatus.DITETAPKAN and d.is_policy and d.clinic is None
    assert d.decider == Decider.DIREKTUR_OPERASIONAL and str(d.decided_on) == "2026-10-06"
    assert "Heni" not in d.decision_text and "Heni" not in d.background

    # Diumumkan ke semua orang di kedua cabang (bukan ke Direktur yang menetapkan).
    notified = set(Notification.objects.filter(type_code="POLICY_PUBLISHED").values_list("user__username", flat=True))
    assert notified == {"yohanes", "heni", "yani", "regita", "dewi"}
    note = Notification.objects.get(user=people["dewi"], type_code="POLICY_PUBLISHED")
    assert note.title == "Kebijakan baru: Surat keterangan kontrol" and "Heni" not in note.body
    assert note.url == reverse("reports:policies")

    # Item Inbox sudah selesai dipilah.
    assert {r["source_id"]: r["state"] for r in inbox_rows(hansen, only_open=False)
            if r["source_type"] == "masukan"}[m.pk] == "sudah"

    # Staf kedua cabang membaca kebijakan; nama pelapor dan sumbernya tidak tampil.
    for who in ("dewi", "yani"):
        client.force_login(people[who])
        page = client.get(reverse("reports:policies")).content.decode()
        assert "Surat keterangan kontrol disimpan sebagai soft file" in page and "Semua cabang" in page
        assert "Heni" not in page and "SUG-" not in page and "Inbox" not in page.split("<main", 1)[-1]
        assert ">Kebijakan<" in page  # ada di menu
    client.force_login(people["yohanes"])
    assert client.get(reverse("reports:policies")).status_code == 200


def test_policy_for_one_branch_only_reaches_that_branch(people, jemur, citraland):
    issue = create_issue(clinic=citraland, issue_type=IssueType.MASUKAN, title="Antrean pagi menumpuk",
                         user=people["dewi"], description="Dewi: antrean pagi menumpuk")
    row = find_row(people["hansen"], "issue", issue.pk)
    triage.to_policy(row, actor=people["hansen"], title="Nomor antrean dibuka 11.30",
                     text="Nomor antrean mulai dibagikan 11.30.", clinic="asal")
    notified = set(Notification.objects.filter(type_code="POLICY_PUBLISHED").values_list("user__username", flat=True))
    assert notified == {"regita", "dewi"}
    issue.refresh_from_db()
    assert "dijadikan kebijakan" in issue.updates.last().note
    with pytest.raises(ValidationError):
        triage.to_policy(row, actor=people["hansen"], title="Tanpa isi", text=" ")
    with pytest.raises(Exception):
        triage.to_policy(row, actor=people["heni"], title="x", text="y")


def test_policy_page_scoped_to_own_branch(client, people, jemur, citraland):
    for clinic, title in ((jemur, "Aturan khusus Jemur"), (citraland, "Aturan khusus Citraland"), (None, "Aturan umum")):
        d = direktur.create_decision(actor=people["hansen"], title=title, decider=Decider.DIREKTUR_OPERASIONAL,
                                     clinic=clinic)
        direktur.settle_decision(d, actor=people["hansen"], decision_text=f"Isi {title}", is_policy=True)
    plain = direktur.create_decision(actor=people["hansen"], title="Keputusan biasa",
                                     decider=Decider.DIREKTUR_OPERASIONAL)
    direktur.settle_decision(plain, actor=people["hansen"], decision_text="Bukan kebijakan")
    client.force_login(people["dewi"])
    page = client.get(reverse("reports:policies")).content.decode()
    assert "Aturan khusus Citraland" in page and "Aturan umum" in page
    assert "Aturan khusus Jemur" not in page and "Keputusan biasa" not in page
    # Menetapkan ulang kebijakan yang sama tidak mengumumkan dua kali.
    before = Notification.objects.filter(type_code="POLICY_PUBLISHED").count()
    d = plain.__class__.objects.get(title="Aturan umum")
    direktur.settle_decision(d, actor=people["hansen"], decision_text="Isi baru", is_policy=True)
    assert Notification.objects.filter(type_code="POLICY_PUBLISHED").count() == before


def test_director_is_recipient_at_both_branches(client, people, jemur, citraland):
    hansen = people["hansen"]
    for clinic in (jemur, citraland):
        assert f"user:{hansen.pk}" in dict(direktur.target_choices(clinic)), clinic
        assert resolve_task_recipients(clinic=clinic, audience_type=TaskAudienceType.USER,
                                       user_ids=[hansen.pk]) == [hansen]
    # Staf cabang lain tetap tidak bisa dipilih.
    assert f"user:{people['regita'].pk}" not in dict(direktur.target_choices(jemur))
    with pytest.raises(ValidationError):
        resolve_task_recipients(clinic=jemur, audience_type=TaskAudienceType.USER, user_ids=[people["regita"].pk])

    # Task untuk Direktur di Citraland, dibuat oleh Supervisor Citraland, tampil di Tugas saya.
    task = create_task(clinic=citraland, actor=people["regita"], title="Tanda tangan SOP Citraland",
                       audience_type=TaskAudienceType.USER, user_ids=[hansen.pk])
    assert [a.assignee for a in task.task_assignments.all()] == [hansen]
    client.force_login(hansen)
    assert "Tanda tangan SOP Citraland" in client.get(reverse("core:action_items")).content.decode()

    # Form "Semua cabang" di halaman pilah: Direktur ada di pilihan PIC kedua cabang.
    m, _ = _masukan_row(people, jemur)
    page = client.get(reverse("reports:inbox_triage", args=["masukan", m.pk]) + "?cabang=semua").content.decode()
    assert page.count(f'value="user:{hansen.pk}"') == 2

    # Komplain/masukan/kerusakan Citraland bisa ditugaskan ke Direktur.
    issue = create_issue(clinic=citraland, issue_type=IssueType.KERUSAKAN, title="Kursi rusak",
                         user=people["dewi"], location="Lobi", impact="TERBATAS")
    assign_issue(issue, supervisor=people["regita"], assignee=hansen)
    with pytest.raises(ValidationError):
        assign_issue(issue, supervisor=people["regita"], assignee=people["yani"])


def test_director_sees_own_task_and_staff_reports(client, people, jemur):
    """5 Okt 2026: task untuk Direktur sendiri tampil di Ringkasan dan bisa diajukan selesai dari detail task;
    komplain/masukan/kerusakan/laporan staf ada di menu Direktur."""
    from core.models import TaskAssignmentStatus

    hansen = people["hansen"]
    task = create_task(clinic=jemur, actor=hansen, title="Evaluasi alur surat kontrol",
                       audience_type=TaskAudienceType.USER, user_ids=[hansen.pk])
    client.force_login(hansen)
    page = client.get(reverse("direktur:overview")).content.decode()
    assert "Tugas saya" in page and "Evaluasi alur surat kontrol" in page
    for label in ("Komplain", "Kerusakan", "Laporan staf", "Masukan privat staf"):
        assert f">{label}<" in page, label

    url = reverse("direktur:task_detail", args=[task.pk])
    page = client.get(url).content.decode()
    assert "Ajukan selesai" in page and "Anda penerimanya" in page
    a = task.task_assignments.get()
    resp = client.post(reverse("core:assignment_submit", args=[a.pk]),
                       {"catatan": "Sudah disosialisasikan, evaluasi menyusul", "next": url})
    assert resp["Location"] == url
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.SUBMITTED
    page = client.get(url).content.decode()
    assert "Ajukan selesai</summary>" not in page

    # Staf lain tidak melihat tombol ajukan di task orang lain; Ringkasan Owner tanpa Tugas saya.
    client.force_login(people["yohanes"])
    assert "Tugas saya" not in client.get(reverse("owner:dashboard")).content.decode()


def test_director_lists_show_all_branches(client, people, jemur, citraland):
    """5 Okt 2026: masukan Citraland (SUG-…) tidak terlihat Direktur karena daftar mengikuti cabang aktif."""
    from reports.services import create_laporan

    sug = create_issue(clinic=citraland, issue_type=IssueType.MASUKAN, title="Operasional kemas dan kirim barang",
                       user=people["regita"])
    create_issue(clinic=jemur, issue_type=IssueType.MASUKAN, title="Masukan Jemur", user=people["yani"])
    create_laporan(clinic=citraland, user=people["dewi"], title="Laporan Citraland")
    create_masukan(clinic=citraland, user=people["dewi"], title="Masukan privat Citraland")
    client.force_login(people["hansen"])
    page = client.get(reverse("issues:list") + "?tipe=MASUKAN").content.decode()
    assert sug.number in page and "Masukan Jemur" in page and "Semua cabang" in page
    page = client.get(reverse("issues:list") + f"?tipe=MASUKAN&cabang={jemur.pk}").content.decode()
    assert sug.number not in page and "Masukan Jemur" in page
    page = client.get(reverse("reports:laporan_page")).content.decode()
    assert "Laporan Citraland" in page and "Laporan staf" in page and "Dewi" in page
    page = client.get(reverse("reports:masukan_page")).content.decode()
    assert "Masukan privat Citraland" in page and "Masukan privat staf" in page
    # Staf tetap hanya cabangnya sendiri, tanpa pilihan cabang.
    client.force_login(people["yani"])
    page = client.get(reverse("issues:list") + "?tipe=MASUKAN&cabang=semua").content.decode()
    assert sug.number not in page and "Masukan Jemur" in page and 'name="cabang"' not in page
