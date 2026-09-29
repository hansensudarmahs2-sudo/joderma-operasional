"""Peran Direktur Operasional: checklist audit, catatan, task, Team Viewer."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.urls import reverse

from accounts.models import PicAssignment, PicFunction, Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import ActionItemStatus, Clinic, TaskAssignmentStatus, TaskAudienceType
from core.services import get_or_create_day
from core.task_services import create_task
from direktur import services
from direktur.management.commands.seed_audit_direktur import seed
from direktur.models import AuditCheck, AuditItem, Cadence, CheckResult, DirectorNote, NoteSource, period_start
from direktur.seed_data import BULANAN, HARIAN, MINGGUAN

pytestmark = pytest.mark.django_db

PASSWORD = "TestPassword123!"
MONDAY = dt.date(2026, 9, 28)


def _user(clinic, username, roles):
    user = User.objects.create_user(username=username, password=PASSWORD, display_name=username.title())
    for role in roles:
        UserRole.objects.create(user=user, clinic=clinic, role=role)
    return user


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="citraland", name="Citraland")


@pytest.fixture
def director(jemur):
    return _user(jemur, "direktur", [Role.AOM])


@pytest.fixture
def heni(jemur):
    user = _user(jemur, "heni", [Role.SUPERVISOR, Role.PIC])
    PicAssignment.objects.create(
        user=user, clinic=jemur, function=PicFunction.SHIFT_COORDINATOR, starts_on="2026-09-01", active=True
    )
    return user


@pytest.fixture
def items(db):
    seed()
    return {i.code: i for i in AuditItem.objects.all()}


# --- Periode dan seed ----------------------------------------------------------------

def test_period_start_per_cadence():
    friday = dt.date(2026, 10, 2)
    assert period_start(Cadence.HARIAN, friday) == friday
    assert period_start(Cadence.MINGGUAN, friday) == MONDAY
    assert period_start(Cadence.BULANAN, friday) == dt.date(2026, 10, 1)


def test_seed_is_idempotent_and_matches_documents():
    first = seed()
    assert first["created"] == len(HARIAN) + len(MINGGUAN) + len(BULANAN)
    assert AuditItem.objects.filter(cadence=Cadence.HARIAN).count() == 8
    assert AuditItem.objects.filter(cadence=Cadence.MINGGUAN).count() == 13
    assert AuditItem.objects.filter(cadence=Cadence.BULANAN).count() == 1
    second = seed()
    assert second == {"created": 0, "updated": 0, "unchanged": first["created"]}
    # Pemeriksaan bulanan emergency kit dipindah dari butir mingguan #9.
    weekly_kit = AuditItem.objects.get(code="mingguan-emergency-kit")
    assert not weekly_kit.points.filter(text__icontains="bulanan").exists()
    assert AuditItem.objects.get(code="bulanan-emergency-kit").points.count() == 1


def test_seed_dry_run_writes_nothing_and_update_restores_text():
    stats = seed(dry_run=True)
    assert stats["created"] > 0 and AuditItem.objects.count() == 0
    seed()
    item = AuditItem.objects.get(code="harian-kas")
    item.title = "Disunting admin"
    item.save()
    seed()
    assert AuditItem.objects.get(code="harian-kas").title == "Disunting admin"
    seed(update=True)
    assert AuditItem.objects.get(code="harian-kas").title == "Kas"


def test_seed_command_runs():
    call_command("seed_audit_direktur", "--dry-run")
    assert AuditItem.objects.count() == 0
    call_command("seed_audit_direktur")
    assert AuditItem.objects.count() == 22


def test_citraland_only_item_not_shown_for_jemur(items, jemur, citraland):
    jemur_codes = {r["item"].code for r in services.board(jemur, Cadence.HARIAN, MONDAY)}
    ctl_codes = {r["item"].code for r in services.board(citraland, Cadence.HARIAN, MONDAY)}
    assert "harian-kesiapan-buka-citraland" not in jemur_codes
    assert "harian-kesiapan-buka-citraland" in ctl_codes
    with pytest.raises(ValidationError):
        services.record_check(
            item=items["harian-kesiapan-buka-citraland"],
            clinic=jemur,
            actor=_user(jemur, "aom2", [Role.AOM]),
            result=CheckResult.SESUAI,
            today=MONDAY,
        )


# --- Checklist Direktur ------------------------------------------------------------

def test_record_check_marks_item_done_for_period(items, jemur, director):
    before = services.pending_summary(jemur, MONDAY)[Cadence.HARIAN]
    services.record_check(
        item=items["harian-limbah"], clinic=jemur, actor=director, result=CheckResult.SESUAI, today=MONDAY
    )
    after = services.pending_summary(jemur, MONDAY)[Cadence.HARIAN]
    assert len(after["pending"]) == len(before["pending"]) - 1
    # Hari berikutnya butir harian kembali "belum dicek".
    tomorrow = services.pending_summary(jemur, MONDAY + dt.timedelta(days=1))[Cadence.HARIAN]
    assert len(tomorrow["pending"]) == len(before["pending"])


def test_weekly_check_counts_for_whole_week_then_resets(items, jemur, director):
    item = items["mingguan-audit-wa"]
    services.record_check(item=item, clinic=jemur, actor=director, result=CheckResult.SESUAI, today=MONDAY)
    friday = MONDAY + dt.timedelta(days=4)
    assert item not in services.pending_summary(jemur, friday)[Cadence.MINGGUAN]["pending"]
    next_week = MONDAY + dt.timedelta(days=7)
    assert item in services.pending_summary(jemur, next_week)[Cadence.MINGGUAN]["pending"]


def test_finding_requires_note_and_creates_one_task_for_pic(items, jemur, director, heni):
    item = items["harian-limbah"]
    with pytest.raises(ValidationError):
        services.record_check(item=item, clinic=jemur, actor=director, result=CheckResult.TEMUAN, today=MONDAY)

    check = services.record_check(
        item=item, clinic=jemur, actor=director, result=CheckResult.TEMUAN,
        note="Freezer tidak terkunci", today=MONDAY,
    )
    assert check.finding is not None
    assert check.finding.source_type == services.FINDING_SOURCE
    assert list(check.finding.task_assignments.values_list("assignee__username", flat=True)) == ["heni"]

    again = services.record_check(
        item=item, clinic=jemur, actor=director, result=CheckResult.TEMUAN,
        note="Freezer tidak terkunci (ulang)", today=MONDAY,
    )
    assert again.finding_id == check.finding_id
    assert AuditCheck.objects.count() == 1
    assert check.finding.task_assignments.count() == 1


def test_finding_without_pic_holder_is_recorded_without_recipient(items, citraland):
    director = _user(citraland, "aom_ctl", [Role.AOM])
    check = services.record_check(
        item=items["harian-limbah"], clinic=citraland, actor=director,
        result=CheckResult.TEMUAN, note="Bak limbah penuh", today=MONDAY,
    )
    assert check.finding is not None
    assert check.finding.task_assignments.count() == 0
    assert check.finding in services.open_findings(citraland)


def test_changing_result_requires_reason_and_is_audited(items, jemur, director):
    item = items["harian-sdm"]
    services.record_check(item=item, clinic=jemur, actor=director, result=CheckResult.SESUAI, today=MONDAY)
    with pytest.raises(ValidationError):
        services.record_check(
            item=item, clinic=jemur, actor=director, result=CheckResult.TIDAK_BERLAKU, today=MONDAY
        )
    services.record_check(
        item=item, clinic=jemur, actor=director, result=CheckResult.TIDAK_BERLAKU,
        reason="Salah pilih", today=MONDAY,
    )
    assert AuditEvent.objects.filter(action=AuditAction.CORRECTION, entity_type="auditcheck").exists()


def test_snapshot_keeps_history_after_item_edit(items, jemur, director):
    item = items["harian-obat"]
    check = services.record_check(item=item, clinic=jemur, actor=director, result=CheckResult.SESUAI, today=MONDAY)
    item.title = "Obat (diubah)"
    item.save()
    check.refresh_from_db()
    assert check.item_snapshot["title"] == "Obat"


def test_non_director_cannot_record(items, jemur, heni):
    with pytest.raises(PermissionDenied):
        services.record_check(
            item=items["harian-limbah"], clinic=jemur, actor=heni, result=CheckResult.SESUAI, today=MONDAY
        )


def test_close_finding(items, jemur, director):
    check = services.record_check(
        item=items["harian-komplain"], clinic=jemur, actor=director,
        result=CheckResult.TEMUAN, note="Komplain WA belum dicatat", today=MONDAY,
    )
    with pytest.raises(ValidationError):
        services.close_finding(check.finding, actor=director, note="")
    services.close_finding(check.finding, actor=director, note="Sudah dicatat")
    check.finding.refresh_from_db()
    assert check.finding.status == ActionItemStatus.SELESAI
    assert check.finding not in services.open_findings(jemur)


def test_direct_suggestions_stable_per_day_and_clinic_scoped(items, jemur):
    first = services.direct_check_suggestions(jemur, MONDAY)
    assert len(first) == 3
    assert first == services.direct_check_suggestions(jemur, MONDAY)
    for _ in range(30):
        picks = services.direct_check_suggestions(jemur, MONDAY + dt.timedelta(days=_))
        assert all(p["item"].code != "harian-kesiapan-buka-citraland" for p in picks)


# --- Catatan dan task --------------------------------------------------------------

def test_strip_wa_prefix_and_title():
    assert services.strip_wa_prefix("[27/09/26 10.15] Heni: Freezer penuh") == "Freezer penuh"
    assert services.strip_wa_prefix("27/09/2026, 10:15 - Heni: Freezer penuh") == "Freezer penuh"
    assert services.strip_wa_prefix("Catatan biasa: tanpa waktu") == "Catatan biasa: tanpa waktu"
    assert services.suggest_title("\n\n[27/09/26 10.15] Heni: Kotak jarum hampir penuh\nbaris 2") == (
        "Kotak jarum hampir penuh"
    )


def test_note_convert_to_task_once(jemur, director, heni):
    note = services.create_note(
        author=director, body="[27/09/26 10.15] Heni: Kotak jarum hampir penuh", source=NoteSource.PASTE_WA
    )
    item = services.convert_note(
        note, user=director, clinic=jemur, title="", target=f"pic:{PicFunction.SHIFT_COORDINATOR}"
    )
    note.refresh_from_db()
    assert note.converted_task == item
    assert note.clinic == jemur
    assert item.title == "Kotak jarum hampir penuh"
    assert item.source_type == services.NOTE_SOURCE and item.source_id == note.pk
    assert item.task_assignments.get().assignee == heni
    with pytest.raises(ValidationError):
        services.convert_note(note, user=director, clinic=jemur, title="x", target=f"user:{heni.pk}")


def test_note_is_private_to_author(jemur, director):
    other = _user(jemur, "aom_lain", [Role.AOM])
    note = services.create_note(author=director, body="Rahasia")
    with pytest.raises(PermissionDenied):
        services.set_note_archived(note, user=other, archived=True)
    assert list(services.notes_for(other)) == []


def test_archive_and_restore_note(director):
    note = services.create_note(author=director, body="Cek AC ruang facial")
    services.set_note_archived(note, user=director, archived=True)
    assert note not in services.notes_for(director)
    assert note in services.notes_for(director, archived=True)
    services.set_note_archived(note, user=director, archived=False)
    assert note in services.notes_for(director)
    assert DirectorNote.objects.count() == 1  # tidak pernah dihapus


def test_manual_task_requires_target(jemur, director, heni):
    with pytest.raises(ValidationError):
        services.create_manual_task(actor=director, clinic=jemur, title="Rapat PIC", target="")
    item = services.create_manual_task(actor=director, clinic=jemur, title="Rapat PIC", target=f"user:{heni.pk}")
    assert item.task_assignments.get().assignee == heni


# --- HTTP ----------------------------------------------------------------------------

# Halaman Tim sekarang juga dibaca Owner (lihat test_dashboard.py); yang di bawah khusus Direktur.
DIRECTOR_URLS = [
    ("direktur:checklist", {}),
    ("direktur:notes", {}),
    ("direktur:task_new", {}),
]


@pytest.mark.parametrize("name,kwargs", DIRECTOR_URLS)
def test_pages_forbidden_for_non_director(client, jemur, heni, name, kwargs):
    owner = _user(jemur, "owner", [Role.OWNER])
    for user in (heni, owner):
        client.force_login(user)
        assert client.get(reverse(name, kwargs=kwargs)).status_code == 403


def test_post_endpoints_forbidden_for_non_director(client, items, jemur, director, heni):
    note = services.create_note(author=director, body="x")
    check = services.record_check(
        item=items["harian-limbah"], clinic=jemur, actor=director,
        result=CheckResult.TEMUAN, note="y", today=MONDAY,
    )
    client.force_login(heni)
    urls = [
        reverse("direktur:record", args=[items["harian-sdm"].pk]),
        reverse("direktur:finding_close", args=[check.finding_id]),
        reverse("direktur:note_archive", args=[note.pk]),
        reverse("direktur:note_convert", args=[note.pk]),
    ]
    for url in urls:
        assert client.post(url, {"cabang": jemur.pk, "hasil": "SESUAI", "catatan": "z"}).status_code == 403


def test_pages_require_login(client):
    response = client.get(reverse("direktur:team"))
    assert response.status_code == 302


def test_director_checklist_page_and_record(client, items, jemur, director):
    client.force_login(director)
    response = client.get(reverse("direktur:checklist"), {"cabang": jemur.pk})
    body = response.content.decode()
    assert response.status_code == 200
    assert "Belum dicek" in body and "Saran cek langsung" in body
    assert "Kesiapan buka Citraland" not in body

    response = client.post(
        reverse("direktur:record", args=[items["harian-kas"].pk]),
        {"cabang": jemur.pk, "hasil": "SESUAI", "langsung": "1"},
    )
    assert response.status_code == 302
    check = AuditCheck.objects.get(item=items["harian-kas"], clinic=jemur)
    assert check.direct is True


def test_director_weekly_tab(client, items, jemur, director):
    client.force_login(director)
    response = client.get(reverse("direktur:checklist"), {"cabang": jemur.pk, "siklus": "MINGGUAN"})
    assert "Audit WA" in response.content.decode()


def test_notes_flow_over_http(client, jemur, director, heni):
    client.force_login(director)
    client.post(reverse("direktur:notes"), {"isi": "Lampu hall mati", "sumber": "MANUAL", "cabang": jemur.pk})
    note = DirectorNote.objects.get()
    assert "Lampu hall mati" in client.get(reverse("direktur:notes")).content.decode()
    page = client.get(reverse("direktur:note_convert", args=[note.pk]))
    assert page.status_code == 200 and "Lampu hall mati" in page.content.decode()
    client.post(
        reverse("direktur:note_convert", args=[note.pk]),
        {"cabang": jemur.pk, "judul": "Ganti lampu hall", "penerima": f"user:{heni.pk}"},
    )
    note.refresh_from_db()
    assert note.converted_task.title == "Ganti lampu hall"


def test_other_director_cannot_open_foreign_note(client, jemur, director):
    other = _user(jemur, "aom_lain", [Role.AOM])
    note = services.create_note(author=director, body="Milik direktur")
    client.force_login(other)
    assert client.get(reverse("direktur:note_convert", args=[note.pk])).status_code == 404
    assert client.post(reverse("direktur:note_archive", args=[note.pk])).status_code == 404


def test_finding_close_rejects_external_redirect(client, items, jemur, director):
    check = services.record_check(
        item=items["harian-limbah"], clinic=jemur, actor=director,
        result=CheckResult.TEMUAN, note="y", today=MONDAY,
    )
    client.force_login(director)
    response = client.post(
        reverse("direktur:finding_close", args=[check.finding_id]),
        {"catatan": "beres", "next": "https://contoh.invalid/"},
    )
    assert response["Location"] == reverse("direktur:team")


def test_team_viewer_shows_what_is_not_done(client, template, jemur, citraland, director, heni):
    # `template` fixture memakai cabang conftest; buat hari & run untuk cabang Jemur sendiri.
    from checklists.models import ChecklistArea, ChecklistTemplate, ChecklistTemplateItem

    tpl = ChecklistTemplate.objects.create(
        clinic=jemur, name="Koordinator Shift buka", area=ChecklistArea.AKSES_UMUM, version=1
    )
    ChecklistTemplateItem.objects.create(template=tpl, label="Cek komputer", required=True, sort_order=1)
    get_or_create_day(jemur, user=heni)
    staf = _user(jemur, "staf_jmr", [Role.STAF])
    create_task(
        clinic=jemur, actor=director, title="Rapikan gudang BHP",
        audience_type=TaskAudienceType.USER, user_ids=[staf.pk],
    )
    client.force_login(director)
    response = client.get(reverse("direktur:team"))
    body = response.content.decode()
    assert response.status_code == 200
    assert "Jemur Andayani" in body and "Citraland" in body
    assert "Rapikan gudang BHP" in body
    assert "Koordinator Shift buka" in body
    assert "Belum ditetapkan" in body  # PIC Citraland kosong
    assert "Belum ada sesi hari operasional" in body  # Citraland belum dibuka


def test_team_viewer_moves_confirmed_task_out_of_open(jemur, director):
    staf = _user(jemur, "staf2", [Role.STAF])
    item = create_task(
        clinic=jemur, actor=director, title="Isi log limbah",
        audience_type=TaskAudienceType.USER, user_ids=[staf.pk],
    )
    assignment = item.task_assignments.get()
    assignment.status = TaskAssignmentStatus.CONFIRMED
    from django.utils import timezone

    assignment.confirmed_at = timezone.now()
    assignment.save()
    overview = {c["clinic"].code: c for c in services.team_overview(director)}
    person = next(p for p in overview["jemur-andayani"]["people"] if p["user"] == staf)
    assert person["open"] == [] and len(person["done"]) == 1
