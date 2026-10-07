"""Projects tahap 2: halaman, menu, kartu staf, bukti wajib, dan label sumber Direktur."""
from __future__ import annotations

import datetime as dt
import io
import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from PIL import Image

from accounts.models import Role, User, UserRole
from core.models import (
    ActionItemStatus, Clinic, TaskAssignmentMode, TaskAssignmentStatus, TaskAudienceType, TaskEvent, TaskEventType,
)
from core.task_services import create_task
from direktur import dashboard
from notifications.models import Notification
from projects import services as ps
from projects.models import Project, ProjectStatus

pytestmark = pytest.mark.django_db

PASSWORD = "TestPassword123!"
IND = TaskAssignmentMode.INDIVIDUAL
BER = TaskAssignmentMode.BERSAMA


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _png(name="bukti.png"):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 30)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _messages(response) -> list[str]:
    return [str(m) for m in response.context["messages"]]


def _nav_labels(body: str) -> list[str]:
    nav = body.split('id="main-nav"', 1)[1].split("</nav>", 1)[0]
    return [re.sub(r"\s+", " ", t).strip() for t in re.findall(r"<a href=\"[^\"]*\"[^>]*>([^<]+)</a>", nav)]


@pytest.fixture
def clinic(db):
    return Clinic.objects.create(code="jemur", name="Jemur", open_time="14:00", close_time="22:00")


@pytest.fixture
def clinic_b(db):
    return Clinic.objects.create(code="kedung", name="Kedung", open_time="14:00", close_time="22:00")


@pytest.fixture
def owner(clinic):
    return _user(clinic, "owner1", Role.OWNER)


@pytest.fixture
def aom1(clinic):
    return _user(clinic, "aom1", Role.AOM)


@pytest.fixture
def spv(clinic):
    return _user(clinic, "spv", Role.SUPERVISOR, Role.STAF)


@pytest.fixture
def sa(clinic):
    return _user(clinic, "staf_a", Role.STAF)


@pytest.fixture
def sb(clinic):
    return _user(clinic, "staf_b", Role.STAF)


@pytest.fixture
def sc(clinic):
    return _user(clinic, "staf_c", Role.STAF)


@pytest.fixture
def sd(clinic):
    return _user(clinic, "staf_d", Role.STAF)


@pytest.fixture
def project(aom1, sa, sb):
    """Dibuat aom1; leader staf A; co-leader staf B."""
    return ps.create_project(actor=aom1, name="Renovasi ruang tunggu", leader=sa, co_leaders=[sb],
                             target_date=dt.date(2026, 12, 31))


def _login(client, user):
    client.force_login(user)
    return client


def _task(project, actor, users, mode=IND, title="Pasang rak"):
    return ps.add_task(project, actor=actor, title=title, user_ids=[u.pk for u in users], mode=mode)


# --- Daftar ----------------------------------------------------------------------------------


def test_list_shows_only_visible_projects(client, project, aom1, owner, sa, sb, sc, sd):
    other = ps.create_project(actor=aom1, name="Project Lain", leader=sc)
    for user in (owner, aom1):
        body = _login(client, user).get(reverse("projects:list")).content.decode()
        assert "Renovasi ruang tunggu" in body and "Project Lain" in body
    for user in (sa, sb):
        body = _login(client, user).get(reverse("projects:list")).content.decode()
        assert "Renovasi ruang tunggu" in body and "Project Lain" not in body
    body = _login(client, sc).get(reverse("projects:list")).content.decode()
    assert "Project Lain" in body and "Renovasi ruang tunggu" not in body
    assert _login(client, sd).get(reverse("projects:list")).status_code == 403
    assert other.pk


def test_list_tabs_and_progress(client, project, aom1, sa):
    ps.cancel_project(ps.create_project(actor=aom1, name="Sudah batal", leader=sa), actor=aom1, note="Tidak jadi")
    _task(project, aom1, [sa])
    body = _login(client, aom1).get(reverse("projects:list")).content.decode()
    assert "Renovasi ruang tunggu" in body and "Sudah batal" not in body
    assert "0 dari 1 task · 0%" in body
    assert "+ Project baru" in body
    body = client.get(reverse("projects:list") + "?semua=1").content.decode()
    assert "Sudah batal" in body and "Renovasi ruang tunggu" not in body
    assert "Dibatalkan" in body


def test_list_empty_state_and_leader_has_no_create_button(client, sa, aom1):
    body = _login(client, aom1).get(reverse("projects:list")).content.decode()
    assert "Belum ada project." in body
    ps.create_project(actor=aom1, name="Satu", leader=sa)
    body = _login(client, sa).get(reverse("projects:list")).content.decode()
    assert "+ Project baru" not in body


def test_list_requires_login(client):
    assert client.get(reverse("projects:list")).status_code == 302


# --- Buat ------------------------------------------------------------------------------------


def test_new_project_by_owner_and_aom(client, clinic, owner, aom1, sa, sb):
    for user in (owner, aom1):
        assert _login(client, user).get(reverse("projects:new")).status_code == 200
    response = client.post(reverse("projects:new"), {
        "nama": "Cetak brosur", "uraian": "Untuk Oktober", "target": "2026-12-01", "cabang": str(clinic.pk),
        "leader": str(sa.pk), "co_leaders": [str(sb.pk)],
    }, follow=True)
    project = Project.objects.get(name="Cetak brosur")
    assert response.redirect_chain[-1][0] == reverse("projects:detail", args=[project.pk])
    assert project.leader == sa and list(project.co_leaders.all()) == [sb] and project.clinic == clinic
    assert project.target_date == dt.date(2026, 12, 1) and project.created_by == aom1
    assert "Project dibuat; leader dan co-leader diberi tahu." in _messages(response)


def test_new_project_forbidden_for_staff_and_supervisor(client, sa, spv):
    for user in (sa, spv):
        _login(client, user)
        assert client.get(reverse("projects:new")).status_code == 403
        assert client.post(reverse("projects:new"), {"nama": "X", "leader": str(user.pk)}).status_code == 403
    assert not Project.objects.exists()


def test_new_project_validation_errors_keep_values(client, aom1, sa):
    _login(client, aom1)
    response = client.post(reverse("projects:new"), {"nama": "  ", "uraian": "Tetap ada", "leader": str(sa.pk)})
    assert response.status_code == 200
    assert "Nama project wajib diisi." in _messages(response)
    assert "Tetap ada" in response.content.decode()
    response = client.post(reverse("projects:new"), {"nama": "Tanpa leader", "uraian": "x"})
    assert response.status_code == 200 and "Project leader wajib dipilih." in _messages(response)
    response = client.post(reverse("projects:new"), {"nama": "Tgl", "leader": str(sa.pk), "target": "bukan-tanggal"})
    assert response.status_code == 200 and "Target tidak valid." in _messages(response)
    assert not Project.objects.exists()


def test_new_project_rejects_unknown_clinic(client, aom1, sa, clinic_b):
    clinic_b.active = False
    clinic_b.save()
    _login(client, aom1)
    response = client.post(reverse("projects:new"), {"nama": "Z", "leader": str(sa.pk), "cabang": str(clinic_b.pk)})
    assert response.status_code == 200 and not Project.objects.exists()


# --- Detail ----------------------------------------------------------------------------------


def test_detail_access(client, project, owner, aom1, sa, sb, sc, spv, sd):
    url = reverse("projects:detail", args=[project.pk])
    for user in (owner, aom1, sa, sb):
        assert _login(client, user).get(url).status_code == 200
    for user in (sc, spv, sd):
        assert _login(client, user).get(url).status_code == 403
    assert _login(client, sc).post(url, {"aksi": "tutup"}).status_code == 403
    client.logout()
    assert client.get(url).status_code == 302


def test_detail_phone_layout_has_data_labels(client, project, aom1, sa):
    _task(project, aom1, [sa])
    body = _login(client, aom1).get(reverse("projects:detail", args=[project.pk])).content.decode()
    assert '<table class="responsive">' in body
    for label in ("Task", "Penerima", "Status", "Target", "Prioritas", "Bukti"):
        assert f'data-label="{label}"' in body


def test_add_task_individual_and_shared(client, project, sa, sb, sc, sd):
    url = reverse("projects:detail", args=[project.pk])
    _login(client, sa)
    response = client.post(url, {
        "aksi": "tambah_task", "judul": "Cat dinding", "uraian": "Warna putih", "penerima": [str(sc.pk), str(sd.pk)],
        "mode": "INDIVIDUAL", "target": "2026-12-15", "prioritas": "TINGGI", "cabang": "",
    }, follow=True)
    assert "Task ditambahkan dan penerima diberi tahu." in _messages(response)
    item = project.tasks().get(title="Cat dinding")
    assert item.assignment_mode == IND and item.task_assignments.count() == 2
    assert item.source_type == "proyek" and item.source_id == project.pk and item.priority == "TINGGI"
    assert item.due_at and timezone_local_date(item.due_at) == dt.date(2026, 12, 15)
    client.post(url, {"aksi": "tambah_task", "judul": "Ambil kunci", "penerima": [str(sc.pk), str(sd.pk)],
                      "mode": "BERSAMA"})
    shared = project.tasks().get(title="Ambil kunci")
    assert shared.assignment_mode == BER
    body = client.get(url).content.decode()
    assert "Cat dinding" in body and "Ambil kunci" in body
    assert "salah satu: Staf_C, Staf_D" in body and "0/2 selesai" in body
    assert "Cukup satu orang" in body


def timezone_local_date(value):
    from django.utils import timezone

    return timezone.localtime(value).date()


def test_add_task_errors_show_messages(client, project, sa, sc, clinic_b):
    url = reverse("projects:detail", args=[project.pk])
    _login(client, sa)
    response = client.post(url, {"aksi": "tambah_task", "judul": "Tanpa penerima", "mode": "INDIVIDUAL"}, follow=True)
    assert "Pilih minimal satu penerima." in _messages(response)
    response = client.post(url, {"aksi": "tambah_task", "judul": "Cabang asing", "penerima": [str(sc.pk)],
                                 "cabang": str(clinic_b.pk)}, follow=True)
    assert response.status_code == 200 and any("cabang" in m.lower() for m in _messages(response))
    response = client.post(url, {"aksi": "tambah_task", "judul": "Bad", "penerima": ["abc"]}, follow=True)
    assert "Penerima tidak dikenali." in _messages(response)
    assert not project.tasks().exists()


def test_add_task_permission_denied_is_readable_message(client, project, sa, sc, monkeypatch):
    def deny(*args, **kwargs):
        raise PermissionDenied("Anda tidak memiliki akses ke cabang ini.")

    monkeypatch.setattr(ps, "add_task", deny)
    response = _login(client, sa).post(reverse("projects:detail", args=[project.pk]), {
        "aksi": "tambah_task", "judul": "X", "penerima": [str(sc.pk)]}, follow=True)
    assert response.status_code == 200
    assert "Anda tidak memiliki akses ke cabang ini." in _messages(response)


def test_add_task_forbidden_for_outsider_and_closed_project(client, project, aom1, sa, sc, sd):
    url = reverse("projects:detail", args=[project.pk])
    assert _login(client, sd).post(url, {"aksi": "tambah_task", "judul": "X", "penerima": [str(sc.pk)]}
                                   ).status_code == 403
    ps.close_project(project, actor=aom1)
    body = _login(client, sa).get(url).content.decode()
    assert 'id="tambah-task"' not in body
    response = client.post(url, {"aksi": "tambah_task", "judul": "X", "penerima": [str(sc.pk)]}, follow=True)
    assert "Project ini sudah ditutup atau dibatalkan." in _messages(response)


def test_detail_shows_evidence_count_and_gallery(client, project, aom1, sa, sc):
    item = _task(project, aom1, [sc])
    _login(client, sc)
    assignment = item.task_assignments.get()
    client.post(reverse("core:assignment_submit", args=[assignment.pk]), {"catatan": "ok", "foto": _png()})
    body = _login(client, sa).get(reverse("projects:detail", args=[project.pk])).content.decode()
    assert re.search(r'data-label="Bukti">\s*1\s*</td>', body)
    assert "Bukti dari staf" in body and "photo-thumbs" in body
    assert "Belum ada bukti." not in body


# --- Pengaturan ------------------------------------------------------------------------------


def test_co_leader_cannot_change_project_settings(client, project, sb, sc):
    url = reverse("projects:detail", args=[project.pk])
    _login(client, sb)
    for data in ({"aksi": "ubah", "uraian": "x", "target": "2027-01-01"},
                 {"aksi": "tambah_coleader", "user": str(sc.pk)},
                 {"aksi": "ganti_leader", "leader": str(sc.pk)},
                 {"aksi": "tutup"}, {"aksi": "batalkan", "alasan": "x"}):
        assert client.post(url, data).status_code == 403, data
    project.refresh_from_db()
    assert project.target_date == dt.date(2026, 12, 31) and project.status == ProjectStatus.AKTIF
    body = client.get(url).content.decode()
    assert "Pengaturan project" not in body


def test_leader_edits_project_and_co_leaders(client, project, sa, sb, sc):
    url = reverse("projects:detail", args=[project.pk])
    _login(client, sa)
    response = client.post(url, {"aksi": "ubah", "uraian": "Uraian baru", "target": "2027-02-02"}, follow=True)
    project.refresh_from_db()
    assert project.description == "Uraian baru" and project.target_date == dt.date(2027, 2, 2)
    assert "Project diperbarui." in _messages(response)
    client.post(url, {"aksi": "tambah_coleader", "user": str(sc.pk)})
    assert sc in project.co_leaders.all()
    client.post(url, {"aksi": "hapus_coleader", "user": str(sb.pk)})
    assert sb not in project.co_leaders.all()
    # Leader tidak boleh mengganti leader atau menutup project (hanya pembuat/Owner/Direktur).
    assert client.post(url, {"aksi": "ganti_leader", "leader": str(sc.pk)}).status_code == 403
    assert client.post(url, {"aksi": "batalkan", "alasan": "x"}).status_code == 403


def test_admin_changes_leader_closes_and_cancels(client, project, aom1, owner, sa, sc):
    url = reverse("projects:detail", args=[project.pk])
    _login(client, owner)
    client.post(url, {"aksi": "ganti_leader", "leader": str(sc.pk)})
    project.refresh_from_db()
    assert project.leader == sc
    item = _task(project, aom1, [sa])
    response = client.post(url, {"aksi": "tutup", "catatan": "Beres"}, follow=True)
    assert "Masih ada task yang belum selesai." in _messages(response)
    project.refresh_from_db()
    assert project.status == ProjectStatus.AKTIF
    response = client.post(url, {"aksi": "batalkan", "alasan": "  "}, follow=True)
    assert "Alasan pembatalan wajib diisi." in _messages(response)
    client.post(url, {"aksi": "batalkan", "alasan": "Anggaran dicabut"})
    project.refresh_from_db()
    item.refresh_from_db()
    assert project.status == ProjectStatus.DIBATALKAN and item.status == ActionItemStatus.BATAL


def test_close_project_when_all_done(client, project, aom1, sa):
    url = reverse("projects:detail", args=[project.pk])
    item = _task(project, aom1, [sa])
    _login(client, sa)
    client.post(reverse("core:assignment_submit", args=[item.task_assignments.get().pk]), {"foto": _png()})
    response = _login(client, aom1).post(url, {"aksi": "tutup", "catatan": "Selesai semua"}, follow=True)
    assert "Project ditutup." in _messages(response)
    project.refresh_from_db()
    assert project.status == ProjectStatus.SELESAI and project.close_note == "Selesai semua"


def test_unknown_action_is_message(client, project, aom1):
    response = _login(client, aom1).post(reverse("projects:detail", args=[project.pk]), {"aksi": "ngawur"},
                                         follow=True)
    assert "Aksi tidak dikenali." in _messages(response)


# --- Detail task -----------------------------------------------------------------------------


def test_task_detail_access_and_404(client, project, aom1, sa, sb, sc, spv):
    item = _task(project, aom1, [sc])
    other = ps.create_project(actor=aom1, name="Lain", leader=sa)
    url = reverse("projects:task_detail", args=[project.pk, item.pk])
    for user in (aom1, sa, sb):
        assert _login(client, user).get(url).status_code == 200
    for user in (sc, spv):  # penerima dan supervisor bukan pengatur project
        assert _login(client, user).get(url).status_code == 403
    _login(client, aom1)
    assert client.get(reverse("projects:task_detail", args=[other.pk, item.pk])).status_code == 404
    assert client.get(reverse("projects:task_detail", args=[project.pk, 99999])).status_code == 404


def test_reopen_flow_from_task_detail(client, project, aom1, sa, sb, sc):
    item = _task(project, aom1, [sc])
    assignment = item.task_assignments.get()
    _login(client, sc)
    client.post(reverse("core:assignment_submit", args=[assignment.pk]), {"catatan": "Sudah", "foto": _png()})
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.CONFIRMED
    url = reverse("projects:task_detail", args=[project.pk, item.pk])
    body = _login(client, sa).get(url).content.decode()
    assert "Batalkan selesai (revisi)" in body and "Catatan: Sudah" in body and "photo-thumbs" in body
    # Penerima (bukan pengatur) tidak bisa membatalkan selesai.
    assert _login(client, sc).post(url, {"aksi": "revisi", "assignment": str(assignment.pk), "catatan": "x"}
                                   ).status_code == 403
    _login(client, sb)
    response = client.post(url, {"aksi": "revisi", "assignment": str(assignment.pk), "catatan": " "}, follow=True)
    assert "Tulis catatan revisi." in _messages(response)
    response = client.post(url, {"aksi": "revisi", "assignment": str(assignment.pk), "catatan": "Foto buram"},
                           follow=True)
    assignment.refresh_from_db()
    item.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.REVISION_REQUIRED and assignment.revision_note == "Foto buram"
    assert item.status == ActionItemStatus.DIKERJAKAN
    body = response.content.decode()
    assert "Foto buram" in body and "Diminta revisi" in body
    assert Notification.objects.filter(user=sc, type_code="TASK_REVISION").exists()
    # Tombol revisi hilang karena tidak ada penerima yang sudah selesai.
    assert "Batalkan selesai (revisi)" not in body


def test_reopen_unknown_assignment_and_other_task(client, project, aom1, sc, sd):
    item = _task(project, aom1, [sc])
    other = _task(project, aom1, [sd], title="Task lain")
    url = reverse("projects:task_detail", args=[project.pk, item.pk])
    _login(client, aom1)
    response = client.post(url, {"aksi": "revisi", "assignment": str(other.task_assignments.get().pk),
                                 "catatan": "x"}, follow=True)
    assert "Penerima tidak ditemukan." in _messages(response)
    response = client.post(url, {"aksi": "revisi", "assignment": "abc", "catatan": "x"}, follow=True)
    assert "Penerima tidak ditemukan." in _messages(response)


def test_cancel_task_from_task_detail(client, project, aom1, sa, sc):
    item = _task(project, aom1, [sc])
    url = reverse("projects:task_detail", args=[project.pk, item.pk])
    _login(client, sa)
    response = client.post(url, {"aksi": "batal_task", "alasan": ""}, follow=True)
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.status == ActionItemStatus.DIKERJAKAN or item.status == ActionItemStatus.BARU
    client.post(url, {"aksi": "batal_task", "alasan": "Tidak perlu lagi"})
    item.refresh_from_db()
    assert item.status == ActionItemStatus.BATAL
    body = client.get(url).content.decode()  # task batal tetap dapat dilihat
    assert "Batal" in body and "Batalkan task" not in body


# --- Bukti wajib & kartu staf ------------------------------------------------------------------


def test_submit_project_task_requires_evidence_file(client, project, aom1, sc):
    item = _task(project, aom1, [sc])
    assignment = item.task_assignments.get()
    _login(client, sc)
    url = reverse("core:assignment_submit", args=[assignment.pk])
    response = client.post(url, {"catatan": "Sudah selesai"}, follow=True)
    assert "Bukti wajib: lampirkan foto atau dokumen." in _messages(response)
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.OPEN
    assert not TaskEvent.objects.filter(assignment=assignment, event_type=TaskEventType.SUBMITTED).exists()
    response = client.post(url, {"catatan": "", "foto": _png()}, follow=True)
    assignment.refresh_from_db()
    item.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.CONFIRMED and item.status == ActionItemStatus.SELESAI
    assert "Task selesai dan tercatat di project." in _messages(response)


def test_submit_project_task_with_pdf_document(client, project, aom1, sc):
    item = _task(project, aom1, [sc])
    assignment = item.task_assignments.get()
    pdf = SimpleUploadedFile("bukti.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", content_type="application/pdf")
    _login(client, sc)
    response = client.post(reverse("core:assignment_submit", args=[assignment.pk]), {"foto": pdf}, follow=True)
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.CONFIRMED, _messages(response)


def test_non_project_submit_still_needs_note_not_file(client, clinic, spv, sb):
    item = create_task(clinic=clinic, actor=spv, title="Biasa", audience_type=TaskAudienceType.USER, user_ids=[sb.pk])
    assignment = item.task_assignments.get()
    _login(client, sb)
    url = reverse("core:assignment_submit", args=[assignment.pk])
    response = client.post(url, {"catatan": ""}, follow=True)
    assert "Tulis catatan bukti: apa yang sudah dikerjakan." in _messages(response)
    client.post(url, {"catatan": "Beres"})
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED


def test_shared_project_task_submit_auto_claims(client, project, aom1, sc, sd):
    item = _task(project, aom1, [sc, sd], mode=BER)
    assignment = item.task_assignments.get(assignee=sc)
    _login(client, sc)
    client.post(reverse("core:assignment_submit", args=[assignment.pk]), {"foto": _png()})
    assignment.refresh_from_db()
    item.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.CONFIRMED and assignment.claimed_by == sc
    assert item.status == ActionItemStatus.SELESAI


def test_staff_card_shows_project_tag_and_required_evidence(client, clinic, project, aom1, spv, sc):
    _task(project, aom1, [sc])
    create_task(clinic=clinic, actor=spv, title="Tugas biasa", audience_type=TaskAudienceType.USER, user_ids=[sc.pk])
    body = _login(client, sc).get(reverse("core:today")).content.decode()
    assert "Project: Renovasi ruang tunggu" in body
    assert "Tandai selesai" in body and "Selesai — lampirkan bukti (wajib)" in body
    # Hanya input berkas task project yang wajib; task biasa tetap opsional.
    assert len(re.findall(r'data-photo="1" required', body)) == 1
    assert body.count("Ajukan selesai") == 1


def test_staff_card_shared_project_task_can_submit_unclaimed(client, project, aom1, sc, sd):
    _task(project, aom1, [sc, sd], mode=BER)
    body = _login(client, sc).get(reverse("core:today")).content.decode()
    assert "Tandai selesai" in body and "Ambil task" in body


def test_staff_card_shows_revision_note_for_project_task(client, project, aom1, sa, sc):
    item = _task(project, aom1, [sc])
    assignment = item.task_assignments.get()
    _login(client, sc)
    client.post(reverse("core:assignment_submit", args=[assignment.pk]), {"foto": _png()})
    assignment.refresh_from_db()
    ps.reopen_assignment(assignment, actor=sa, note="Foto kurang jelas")
    body = client.get(reverse("core:today")).content.decode()
    assert "Catatan revisi: Foto kurang jelas" in body and "Perlu revisi" in body
    assert "Project: Renovasi ruang tunggu" in body


def test_staff_card_project_lookup_is_one_query(client, project, aom1, sc):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from core.task_services import my_tasks

    def project_queries():
        with CaptureQueriesContext(connection) as ctx:
            rows = my_tasks(sc)
        return len(rows), sum('FROM "projects_project"' in q["sql"] for q in ctx.captured_queries)

    _task(project, aom1, [sc], title="Task 0")
    n1, q1 = project_queries()
    for n in (1, 2):
        _task(project, aom1, [sc], title=f"Task {n}")
    n3, q3 = project_queries()
    assert (n1, n3) == (1, 3)
    assert q1 == q3 == 1
    assert [r["project"] for r in my_tasks(sc)] == ["Renovasi ruang tunggu"] * 3


def test_submit_with_invalid_file_changes_nothing(client, project, aom1, sc, sd):
    item = _task(project, aom1, [sc, sd], mode=BER)
    assignment = item.task_assignments.get(assignee=sc)
    _login(client, sc)
    bad = SimpleUploadedFile("catatan.txt", b"halo", content_type="text/plain")
    response = client.post(reverse("core:assignment_submit", args=[assignment.pk]), {"catatan": "x", "foto": bad},
                           follow=True)
    assert "Lampiran harus foto, PDF, atau DOCX." in _messages(response)
    assignment.refresh_from_db()
    item.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.OPEN and assignment.claimed_by_id is None
    assert item.status == ActionItemStatus.BARU
    assert not TaskEvent.objects.filter(action_item=item).exclude(event_type=TaskEventType.SENT).exists()


def test_action_items_page_requires_file_for_project_tasks(client, clinic, project, aom1, spv, sc):
    _task(project, aom1, [sc])
    create_task(clinic=clinic, actor=spv, title="Tugas biasa", audience_type=TaskAudienceType.USER, user_ids=[sc.pk])
    body = _login(client, sc).get(reverse("core:action_items")).content.decode()
    assert body.count("Tandai selesai") == 1 and body.count("Ajukan selesai") == 1
    assert len(re.findall(r'aria-label="Bukti \(wajib\): foto atau dokumen" required', body)) == 1


def test_remove_deactivated_co_leader(client, project, sa, sb):
    sb.is_active = False
    sb.save()
    response = _login(client, sa).post(reverse("projects:detail", args=[project.pk]),
                                       {"aksi": "hapus_coleader", "user": str(sb.pk)}, follow=True)
    assert "Co-project leader dihapus." in _messages(response)
    assert sb not in project.co_leaders.all()


def test_people_excludes_admin_only_users(client, clinic, project, aom1, sa):
    admin = _user(clinic, "admin1", Role.ADMIN)
    both = _user(clinic, "admin_staf", Role.ADMIN, Role.STAF)
    body = _login(client, aom1).get(reverse("projects:detail", args=[project.pk])).content.decode()
    assert f'value="{admin.pk}"' not in body and f'value="{both.pk}"' in body
    body = client.get(reverse("projects:new")).content.decode()
    assert f'value="{admin.pk}"' not in body and f'value="{both.pk}"' in body


# --- Menu, notifikasi, Direktur -----------------------------------------------------------------


def test_menu_projects_visibility(client, project, owner, aom1, sa, sb, sc, spv):
    assert "Projects" in _nav_labels(_login(client, owner).get(reverse("owner:dashboard")).content.decode())
    assert "Projects" in _nav_labels(_login(client, aom1).get(reverse("direktur:overview")).content.decode())
    for user in (sa, sb):
        assert "Projects" in _nav_labels(_login(client, user).get(reverse("core:today")).content.decode())
    for user in (sc, spv):
        assert "Projects" not in _nav_labels(_login(client, user).get(reverse("core:today")).content.decode())
    ps.cancel_project(project, actor=aom1, note="Batal")
    assert "Projects" not in _nav_labels(_login(client, sa).get(reverse("core:today")).content.decode())


def test_menu_projects_for_supervisor_leader(client, clinic, aom1, spv):
    ps.create_project(actor=aom1, name="Dipimpin SPV", leader=spv)
    body = _login(client, spv).get(reverse("core:dashboard")).content.decode()
    assert "Projects" in _nav_labels(body)
    assert _login(client, spv).get(reverse("projects:list")).status_code == 200


def test_owner_can_open_project_pages(client, project, owner, aom1, sc):
    item = _task(project, aom1, [sc])
    _login(client, owner)
    assert client.get(reverse("projects:list")).status_code == 200
    assert client.get(reverse("projects:new")).status_code == 200
    assert client.get(reverse("projects:detail", args=[project.pk])).status_code == 200
    assert client.get(reverse("projects:task_detail", args=[project.pk, item.pk])).status_code == 200


def test_notification_urls_resolve(client, project, aom1, sa, sc):
    note = Notification.objects.get(user=sa, type_code="PROJECT_ROLE")
    assert note.url == reverse("projects:detail", args=[project.pk])
    item = _task(project, aom1, [sc])
    _login(client, sc)
    client.post(reverse("core:assignment_submit", args=[item.task_assignments.get().pk]), {"foto": _png()})
    done = Notification.objects.get(user=sa, type_code="PROJECT_TASK_DONE")
    assert done.url == reverse("projects:task_detail", args=[project.pk, item.pk])
    assert _login(client, sa).get(done.url).status_code == 200


def test_direktur_task_list_labels_project_source(client, project, aom1, sc):
    item = _task(project, aom1, [sc])
    assert dashboard.source_group(item) == "proyek"
    assert dict(dashboard.SOURCE_CHOICES)["proyek"] == "Project"
    assert dashboard.source_url(item) == reverse("projects:detail", args=[project.pk])
    body = _login(client, aom1).get(reverse("direktur:tasks")).content.decode()
    assert "Jemur · Project" in body
    filtered = client.get(reverse("direktur:tasks") + "?sumber=proyek").content.decode()
    assert "Pasang rak" in filtered


# --- Gelombang perbaikan (review akhir) ----------------------------------------------------------


@pytest.fixture
def pair(clinic):
    """Dua penerima; penerima lain urut lebih dulu menurut username, pengambil terakhir."""
    return _user(clinic, "aaa_lain", Role.STAF), _user(clinic, "zzz_pengambil", Role.STAF)


def _claim(user, item):
    from core.task_services import claim_shared_task

    claim_shared_task(item.task_assignments.get(assignee=user), user=user)


def test_claimer_submits_own_assignment_from_action_items_project(client, project, aom1, pair):
    other, claimer = pair
    item = _task(project, aom1, [other, claimer], mode=BER)
    _claim(claimer, item)
    own = item.task_assignments.get(assignee=claimer)
    theirs = item.task_assignments.get(assignee=other)
    body = _login(client, claimer).get(reverse("core:action_items")).content.decode()
    assert reverse("core:assignment_submit", args=[own.pk]) in body
    assert reverse("core:assignment_submit", args=[theirs.pk]) not in body
    client.post(reverse("core:assignment_submit", args=[own.pk]), {"foto": _png()})
    own.refresh_from_db()
    item.refresh_from_db()
    assert own.status == TaskAssignmentStatus.CONFIRMED and item.status == ActionItemStatus.SELESAI


def test_claimer_cannot_act_on_other_recipients_assignment(client, project, aom1, pair):
    from django.core.exceptions import ValidationError

    from core.task_services import report_blocker, report_progress, submit_assignment

    other, claimer = pair
    item = _task(project, aom1, [other, claimer], mode=BER)
    _claim(claimer, item)
    theirs = item.task_assignments.get(assignee=other)
    for call in (lambda: submit_assignment(theirs, user=claimer, note="x"),
                 lambda: report_progress(theirs, user=claimer, note="x"),
                 lambda: report_blocker(theirs, user=claimer, reason="x")):
        with pytest.raises(PermissionDenied):
            call()
    # Penerima lain tidak boleh bertindak setelah task diambil.
    with pytest.raises(ValidationError):
        submit_assignment(theirs, user=other, note="x")


def test_claimer_submits_own_assignment_from_action_items_plain(client, clinic, spv, pair):
    other, claimer = pair
    item = create_task(clinic=clinic, actor=spv, title="Bersama biasa", audience_type=TaskAudienceType.USERS,
                       user_ids=[other.pk, claimer.pk], mode=BER)
    _claim(claimer, item)
    own = item.task_assignments.get(assignee=claimer)
    theirs = item.task_assignments.get(assignee=other)
    body = _login(client, claimer).get(reverse("core:action_items")).content.decode()
    assert reverse("core:assignment_submit", args=[own.pk]) in body
    assert reverse("core:assignment_submit", args=[theirs.pk]) not in body
    client.post(reverse("core:assignment_submit", args=[own.pk]), {"catatan": "Beres"})
    own.refresh_from_db()
    theirs.refresh_from_db()
    assert own.status == TaskAssignmentStatus.SUBMITTED and theirs.status == TaskAssignmentStatus.OPEN


def test_leader_gets_blocker_and_comment_notifications_with_working_links(client, project, aom1, sa, sb, sc):
    from core.task_services import add_task_comment, report_blocker

    item = _task(project, aom1, [sc])
    assignment = item.task_assignments.get()
    report_blocker(assignment, user=sc, reason="Vendor belum datang")
    add_task_comment(item, actor=sc, note="Mohon arahan")
    url = reverse("projects:task_detail", args=[project.pk, item.pk])
    for leader in (sa, sb):
        for code in ("TASK_BLOCKED", "TASK_COMMENT"):
            note = Notification.objects.get(user=leader, type_code=code)
            assert note.url == url
        assert _login(client, leader).get(url).status_code == 200
    # Direktur tetap ke halaman Direktur.
    assert Notification.objects.get(user=aom1, type_code="TASK_BLOCKED").url == reverse(
        "direktur:task_detail", args=[item.pk])


def test_leader_replies_from_task_detail(client, project, aom1, sa, sc):
    item = _task(project, aom1, [sc])
    url = reverse("projects:task_detail", args=[project.pk, item.pk])
    body = _login(client, sa).get(url).content.decode()
    assert 'name="aksi" value="komentar"' in body
    response = client.post(url, {"aksi": "komentar", "catatan": "Silakan lanjut"}, follow=True)
    assert "Balasan terkirim." in _messages(response) and "Silakan lanjut" in response.content.decode()
    assert item.task_events.filter(event_type=TaskEventType.COMMENT, actor=sa).exists()
    assert Notification.objects.filter(user=sc, type_code="TASK_COMMENT").exists()
    response = client.post(url, {"aksi": "komentar", "catatan": " "}, follow=True)
    assert "Catatan kosong." in _messages(response)
    assert _login(client, sc).post(url, {"aksi": "komentar", "catatan": "x"}).status_code == 403


def test_action_item_update_cannot_bypass_project_evidence(client, project, aom1, sa, sc):
    item = _task(project, aom1, [sc])
    _login(client, sa)
    url = reverse("core:action_item_update", args=[item.pk])
    response = client.post(url, {"status": "SELESAI", "catatan": ""}, follow=True)
    item.refresh_from_db()
    assert item.status != ActionItemStatus.SELESAI
    assert "Task project diselesaikan lewat Tandai selesai dengan bukti." in _messages(response)
    response = client.post(url, {"status": "BATAL"}, follow=True)
    item.refresh_from_db()
    assert item.status != ActionItemStatus.BATAL and "Batalkan lewat halaman project." in _messages(response)
    client.post(url, {"status": "DIKERJAKAN", "catatan": "jalan"})
    item.refresh_from_db()
    assert item.status == ActionItemStatus.DIKERJAKAN and item.progress_note == "jalan"
    # Penerima biasa (bukan pengatur) juga tidak bisa menyelesaikan lewat jalur ini.
    _login(client, sc).post(url, {"status": "SELESAI"})
    item.refresh_from_db()
    assert item.status != ActionItemStatus.SELESAI


def test_action_item_update_cannot_revive_cancelled_project_task(client, project, aom1, sa, sc):
    item = _task(project, aom1, [sc])
    ps.cancel_project_task(item, actor=aom1, reason="Batal")
    _login(client, sa).post(reverse("core:action_item_update", args=[item.pk]), {"status": "BARU"})
    item.refresh_from_db()
    assert item.status == ActionItemStatus.BATAL


def test_action_item_update_rejects_unknown_status(client, clinic, spv, sb):
    item = create_task(clinic=clinic, actor=spv, title="Biasa", audience_type=TaskAudienceType.USER, user_ids=[sb.pk])
    response = _login(client, spv).post(reverse("core:action_item_update", args=[item.pk]), {"status": "NGAWUR"},
                                        follow=True)
    item.refresh_from_db()
    assert item.status != "NGAWUR" and "Status tidak dikenali." in _messages(response)


def test_owner_is_not_a_task_recipient(client, project, owner, aom1, sa, sc):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="Owner tidak dapat menjadi penerima task."):
        _task(project, aom1, [owner, sc])
    assert not project.tasks().exists()
    assert _task(project, aom1, [aom1]).pk  # Direktur boleh menjadi penerima
    body = _login(client, aom1).get(reverse("projects:detail", args=[project.pk])).content.decode()
    penerima = body.split('id="t-penerima"', 1)[1].split("</select>", 1)[0]
    assert f'value="{owner.pk}"' not in penerima and f'value="{sc.pk}"' in penerima
    leader = body.split('id="p-leader"', 1)[1].split("</select>", 1)[0]
    assert f'value="{owner.pk}"' in leader


def test_direktur_task_page_uses_project_submit_form(client, project, aom1):
    item = _task(project, aom1, [aom1])
    body = _login(client, aom1).get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "Tandai selesai" in body and "Ajukan selesai" not in body
    assert re.search(r'data-photo="1" required', body)


def test_cancelling_claimer_frees_shared_task(client, project, aom1, pair):
    from core.task_services import cancel_assignment, claim_shared_task

    other, claimer = pair
    item = _task(project, aom1, [other, claimer], mode=BER)
    _claim(claimer, item)
    cancel_assignment(item.task_assignments.get(assignee=claimer), actor=aom1, reason="Cuti")
    assert not item.task_assignments.filter(claimed_by__isnull=False).exists()
    claim_shared_task(item.task_assignments.get(assignee=other), user=other)
    assert item.task_assignments.get(assignee=other).claimed_by == other


def test_cancelling_non_claimer_keeps_claim(client, project, aom1, pair):
    from core.task_services import cancel_assignment

    other, claimer = pair
    item = _task(project, aom1, [other, claimer], mode=BER)
    _claim(claimer, item)
    cancel_assignment(item.task_assignments.get(assignee=other), actor=aom1, reason="Salah orang")
    assert item.task_assignments.get(assignee=claimer).claimed_by == claimer
