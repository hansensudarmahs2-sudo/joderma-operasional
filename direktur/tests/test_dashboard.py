"""Ringkasan (bird view), matriks Eisenhower, kanban, dan register keputusan."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import PicAssignment, PicFunction, Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import (
    ActionItem,
    ActionItemStatus,
    Clinic,
    ClinicConfig,
    Priority,
    TaskAssignmentStatus,
    TaskAudienceType,
)
from core.task_services import confirm_assignment, create_task, submit_assignment
from direktur import dashboard, services
from direktur.management.commands.seed_audit_direktur import seed
from direktur.models import AuditItem, CheckResult, Decider, Decision, DecisionStatus

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


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
def owner(jemur):
    return _user(jemur, "owner", [Role.OWNER])


@pytest.fixture
def staf(jemur):
    return _user(jemur, "staf", [Role.STAF])


def _task(clinic, actor, assignee, title, **kw):
    return create_task(
        clinic=clinic, actor=actor, title=title,
        audience_type=TaskAudienceType.USER, user_ids=[assignee.pk], **kw,
    )


# --- Kanban ----------------------------------------------------------------------

def test_kanban_columns_follow_assignment_state(jemur, director, staf):
    new = _task(jemur, director, staf, "Baru")
    doing = _task(jemur, director, staf, "Dikerjakan")
    a = doing.task_assignments.get()
    a.status = TaskAssignmentStatus.IN_PROGRESS
    a.save()
    waiting = _task(jemur, director, staf, "Menunggu")
    submit_assignment(waiting.task_assignments.get(), user=staf)
    done = _task(jemur, director, staf, "Selesai")
    submit_assignment(done.task_assignments.get(), user=staf)
    confirm_assignment(done.task_assignments.get(), reviewer=director, rating=5)
    cancelled = _task(jemur, director, staf, "Batal")
    cancelled.status = ActionItemStatus.BATAL
    cancelled.save()

    board = {col["key"]: [c["item"].title for c in col["cards"]] for col in dashboard.kanban(director)}
    assert board["BARU"] == ["Baru"]
    assert board["DIKERJAKAN"] == ["Dikerjakan"]
    assert board["MENUNGGU"] == ["Menunggu"]
    assert board["SELESAI"] == ["Selesai"]
    assert "Batal" not in sum(board.values(), [])


def test_kanban_filters_by_clinic_and_source(jemur, citraland, director, staf):
    staf_ctl = _user(citraland, "staf_ctl", [Role.STAF])
    _task(jemur, director, staf, "Task Jemur")
    _task(citraland, director, staf_ctl, "Task Citraland")
    only_ctl = dashboard.kanban(director, clinic_id=citraland.pk)
    titles = [c["item"].title for col in only_ctl for c in col["cards"]]
    assert titles == ["Task Citraland"]
    assert all(c["item"].source_type == "manual"
               for col in dashboard.kanban(director, source="manual") for c in col["cards"])
    assert sum(col["count"] for col in dashboard.kanban(director, source="audit_direktur")) == 0


# --- Eisenhower -------------------------------------------------------------------

def test_quadrants_from_priority_and_due(jemur, director, staf):
    now = timezone.now()
    soon = now + dt.timedelta(hours=10)
    later = now + dt.timedelta(days=10)
    _task(jemur, director, staf, "I-tinggi-mendesak", priority=Priority.TINGGI, due_at=soon)
    _task(jemur, director, staf, "I-kritis-tanpa-target", priority=Priority.KRITIS)
    _task(jemur, director, staf, "II-tinggi-nanti", priority=Priority.TINGGI, due_at=later)
    _task(jemur, director, staf, "III-sedang-mendesak", priority=Priority.SEDANG, due_at=soon)
    _task(jemur, director, staf, "IV-sedang-nanti", priority=Priority.SEDANG, due_at=later)
    quads = {q["key"]: sorted(c["item"].title for c in q["cards"]) for q in dashboard.eisenhower(director)}
    assert quads["I"] == ["I-kritis-tanpa-target", "I-tinggi-mendesak"]
    assert quads["II"] == ["II-tinggi-nanti"]
    assert quads["III"] == ["III-sedang-mendesak"]
    assert quads["IV"] == ["IV-sedang-nanti"]


def test_urgent_threshold_is_configurable(jemur, director, staf):
    _task(jemur, director, staf, "Tiga hari lagi", priority=Priority.TINGGI,
          due_at=timezone.now() + dt.timedelta(hours=72))
    assert dashboard.eisenhower(director)[1]["count"] == 1  # II
    ClinicConfig.set(jemur, "dashboard.urgent_hours", 96)
    assert dashboard.eisenhower(director)[0]["count"] == 1  # I


# --- Bird view --------------------------------------------------------------------

def test_bird_view_green_when_nothing_open(jemur, citraland, director):
    bird = dashboard.bird_view(director)
    assert {c["level"] for c in bird["cards"]} == {"hijau"}
    assert bird["any_problem"] is False


def test_bird_view_red_for_overdue_task_and_finding_without_recipient(jemur, citraland, director, staf):
    seed()
    _task(jemur, director, staf, "Lewat", due_at=timezone.now() - dt.timedelta(hours=1))
    services.record_check(
        item=AuditItem.objects.get(code="harian-limbah"), clinic=citraland, actor=director,
        result=CheckResult.TEMUAN, note="Bak penuh",
    )
    cards = {c["clinic"].code: c for c in dashboard.bird_view(director)["cards"]}
    assert cards["jemur-andayani"]["level"] == "merah"
    assert "1 task lewat target" in cards["jemur-andayani"]["reasons"]
    assert cards["citraland"]["level"] == "merah"
    assert "1 temuan tanpa penerima" in cards["citraland"]["reasons"]


def test_bird_view_yellow_for_open_finding_with_recipient(jemur, director):
    seed()
    heni = _user(jemur, "heni", [Role.SUPERVISOR, Role.PIC])
    PicAssignment.objects.create(user=heni, clinic=jemur, function=PicFunction.SHIFT_COORDINATOR,
                                 starts_on="2026-09-01", active=True)
    services.record_check(
        item=AuditItem.objects.get(code="harian-sdm"), clinic=jemur, actor=director,
        result=CheckResult.TEMUAN, note="Papan istirahat kosong",
    )
    card = next(c for c in dashboard.bird_view(director)["cards"] if c["clinic"] == jemur)
    assert card["level"] == "kuning"
    assert "1 temuan Direktur terbuka" in card["reasons"]


def test_bird_view_decisions_pending_and_overdue(jemur, director):
    today = dt.date(2026, 9, 29)
    services.create_decision(actor=director, title="Nasib uang keep", decider=Decider.OWNER,
                             needed_by=today - dt.timedelta(days=1))
    services.create_decision(actor=director, title="Jam buka Citraland", decider=Decider.DIRUT)
    bird = dashboard.bird_view(director, today)
    assert len(bird["pending_decisions"]) == 2
    assert [d.title for d in bird["late_decisions"]] == ["Nasib uang keep"]
    card = bird["cards"][0]
    assert card["level"] == "merah"
    assert "1 keputusan lewat tenggat" in card["reasons"]
    assert "1 keputusan menggantung" in card["reasons"]


# --- Keputusan --------------------------------------------------------------------

def test_decision_lifecycle_and_audit(jemur, director):
    d = services.create_decision(actor=director, title="Aturan keep antrian", decider=Decider.OWNER,
                                 clinic=jemur, reference="KP-200")
    assert d.status == DecisionStatus.MENUNGGU and str(d) == "KP-200 · Aturan keep antrian"
    with pytest.raises(ValidationError):
        services.settle_decision(d, actor=director, decision_text="")
    services.settle_decision(d, actor=director, decision_text="Hangus setelah 7 hari", is_policy=True)
    d.refresh_from_db()
    assert d.status == DecisionStatus.DITETAPKAN and d.is_policy and d.decided_on
    assert d in dashboard.recent_policies(director)
    assert AuditEvent.objects.filter(entity_type="decision", action=AuditAction.APPROVE).exists()


def test_decision_cancel_requires_reason(director):
    d = services.create_decision(actor=director, title="X", decider=Decider.OWNER)
    with pytest.raises(ValidationError):
        services.cancel_decision(d, actor=director, reason="")
    services.cancel_decision(d, actor=director, reason="Tidak relevan lagi")
    d.refresh_from_db()
    assert d.status == DecisionStatus.DIBATALKAN
    with pytest.raises(ValidationError):
        services.settle_decision(d, actor=director, decision_text="y")
    assert Decision.objects.count() == 1  # tidak dihapus


def test_owner_cannot_write_decisions(owner, director):
    with pytest.raises(PermissionDenied):
        services.create_decision(actor=owner, title="X", decider=Decider.OWNER)
    d = services.create_decision(actor=director, title="X", decider=Decider.OWNER)
    with pytest.raises(PermissionDenied):
        services.settle_decision(d, actor=owner, decision_text="y")


# --- HTTP -------------------------------------------------------------------------

OVERVIEW_PAGES = ["direktur:overview", "direktur:kanban", "direktur:matrix", "direktur:gantt",
                  "direktur:decisions", "direktur:team"]


@pytest.mark.parametrize("name", OVERVIEW_PAGES)
def test_pages_open_for_director_and_owner(client, name, director, owner):
    # Owner melihat Ringkasan lewat Dashboard Owner (owner:dashboard), bukan halaman Direktur.
    users = (director,) if name == "direktur:overview" else (director, owner)
    for user in users:
        client.force_login(user)
        assert client.get(reverse(name)).status_code == 200


@pytest.mark.parametrize("name", OVERVIEW_PAGES)
def test_pages_forbidden_for_staff_and_supervisor(client, name, jemur, staf):
    supervisor = _user(jemur, "spv", [Role.SUPERVISOR, Role.PIC])
    for user in (staf, supervisor):
        client.force_login(user)
        assert client.get(reverse(name)).status_code == 403


def test_owner_sees_no_action_forms(client, jemur, director, owner, staf):
    seed()
    services.record_check(
        item=AuditItem.objects.get(code="harian-limbah"), clinic=jemur, actor=director,
        result=CheckResult.TEMUAN, note="x",
    )
    d = services.create_decision(actor=director, title="Perkara", decider=Decider.OWNER)
    client.force_login(owner)
    team = client.get(reverse("direktur:team")).content.decode()
    assert "Tandai selesai" not in team and "Task baru" not in team
    detail = client.get(reverse("direktur:decision_detail", args=[d.pk])).content.decode()
    assert "Tetapkan" not in detail
    assert "Catat perkara baru" not in client.get(reverse("direktur:decisions")).content.decode()
    # Owner tetap tidak dapat membuka halaman kerja Direktur.
    assert client.get(reverse("direktur:checklist")).status_code == 403
    assert client.get(reverse("direktur:notes")).status_code == 403


def test_owner_post_to_decisions_is_forbidden(client, director, owner):
    d = services.create_decision(actor=director, title="Perkara", decider=Decider.OWNER)
    client.force_login(owner)
    assert client.post(reverse("direktur:decisions"), {"perkara": "x", "pemutus": "OWNER"}).status_code == 403
    assert client.post(reverse("direktur:decision_detail", args=[d.pk]), {"isi": "y"}).status_code == 403
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU


def test_director_creates_and_settles_decision_over_http(client, jemur, director):
    client.force_login(director)
    client.post(reverse("direktur:decisions"), {
        "perkara": "Imbalan koordinator", "pemutus": "DIRUT", "tenggat": "2026-10-05", "cabang": jemur.pk,
    })
    d = Decision.objects.get()
    assert d.clinic == jemur and d.needed_by == dt.date(2026, 10, 5)
    client.post(reverse("direktur:decision_detail", args=[d.pk]),
                {"isi": "Rp500.000/bulan", "kebijakan": "1", "tanggal": "2026-09-29"})
    d.refresh_from_db()
    assert d.status == DecisionStatus.DITETAPKAN and d.is_policy
    body = client.get(reverse("direktur:decisions") + "?status=KEBIJAKAN").content.decode()
    assert "Imbalan koordinator" in body
    assert dashboard.headline_counts(director)["policies"] == 1


def test_overview_page_shows_sections(client, jemur, citraland, owner, director, staf):
    _task(jemur, director, staf, "Susun jadwal piket", priority=Priority.TINGGI,
          due_at=timezone.now() + dt.timedelta(hours=5))
    client.force_login(owner)
    body = client.get(reverse("owner:dashboard")).content.decode()  # isi yang sama dengan Ringkasan Direktur
    for text in ("Yang belum selesai", "Keputusan menggantung", "Kebijakan baru", "Jadwal task",
                 "Kerjakan sekarang", "Menunggu konfirmasi", "Susun jadwal piket", "Per cabang", "Citraland"):
        assert text in body
    # Halaman utama tidak memuat daftar kanban penuh; detail ada di halaman terpisah.
    assert "Kanban lengkap" not in body


def test_owner_nav_shows_overview_links_only(client, owner):
    client.force_login(owner)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert reverse("direktur:kanban") in body and reverse("direktur:decisions") in body
    assert reverse("direktur:checklist") not in body


def test_headline_counts(jemur, director, staf):
    now = timezone.now()
    _task(jemur, director, staf, "Lewat", due_at=now - dt.timedelta(hours=2))
    _task(jemur, director, staf, "Minggu ini", due_at=now + dt.timedelta(days=3))
    waiting = _task(jemur, director, staf, "Menunggu")
    submit_assignment(waiting.task_assignments.get(), user=staf)
    services.create_decision(actor=director, title="X", decider=Decider.OWNER)
    counts = dashboard.headline_counts(director)
    assert counts["open"] == 3 and counts["overdue"] == 1
    assert counts["waiting"] == 1 and counts["due_week"] == 1 and counts["decisions"] == 1


def test_matrix_page_focuses_one_quadrant(client, jemur, director, staf):
    _task(jemur, director, staf, "Kritis", priority=Priority.KRITIS)
    _task(jemur, director, staf, "Biasa")
    client.force_login(director)
    body = client.get(reverse("direktur:matrix"), {"kuadran": "I"}).content.decode()
    assert "Kritis" in body and "Biasa" not in body and "Tampilkan keempat kuadran" in body


def test_gantt_rows_and_states(client, jemur, director, staf, owner):
    now = timezone.now()
    _task(jemur, director, staf, "Lewat", due_at=now - dt.timedelta(days=1))
    _task(jemur, director, staf, "Berjalan", due_at=now + dt.timedelta(days=5))
    _task(jemur, director, staf, "Tanpa target")
    _task(jemur, director, staf, "Jauh", due_at=now + dt.timedelta(days=60))
    chart = dashboard.gantt(director)
    states = {r["item"].title: r["state"] for r in chart["rows"]}
    assert states == {"Lewat": "late", "Berjalan": "open", "Tanpa target": "nodue", "Jauh": "open"}
    for r in chart["rows"]:
        assert 0 <= r["left"] <= 100 and 0 < r["width"] <= 100 - r["left"] + 0.01
    far = next(r for r in chart["rows"] if r["item"].title == "Jauh")
    assert round(far["left"] + far["width"]) == 100  # dipotong di ujung jendela
    assert 0 < chart["today_left"] < 100
    # Task lewat target memanjang sampai hari ini, bukan berhenti di targetnya.
    ActionItem.objects.filter(title="Lewat").update(created_at=now - dt.timedelta(days=4))
    late = next(r for r in dashboard.gantt(director)["rows"] if r["item"].title == "Lewat")
    assert abs(late["left"] + late["width"] - chart["today_left"]) < 0.5
    client.force_login(owner)
    body = client.get(reverse("direktur:gantt")).content.decode()
    assert "Tanpa target" in body and "Berjalan" in body


def test_gantt_positions_are_not_localized(client, jemur, director, staf, owner):
    """LANGUAGE_CODE="id" memformat desimal dengan koma; CSS butuh titik."""
    import re
    _task(jemur, director, staf, "Berjalan", due_at=timezone.now() + dt.timedelta(days=5))
    client.force_login(owner)
    body = client.get(reverse("direktur:gantt")).content.decode()
    assert not re.search(r"(left|width):\d+,\d", body)
    assert re.search(r"left:\d+(\.\d+)?%;width:\d+(\.\d+)?%", body)


def test_gantt_groups_tasks_under_owner_request(client, jemur, citraland, director, staf, owner):
    """Fase 6: satu baris per Permintaan Owner beserta task turunannya; target Owner ditandai."""
    import re

    from owner.models import SOURCE_TYPE
    from owner.services import create_request

    today = timezone.localdate()
    now = timezone.now()
    req = create_request(actor=owner, title="Ganti tirai ruang facial", target_date=today + dt.timedelta(days=5),
                         clinic=jemur)
    empty = create_request(actor=owner, title="Cek CCTV", target_date=today + dt.timedelta(days=2))
    late = create_request(actor=owner, title="Rapikan gudang", target_date=today, clinic=jemur)
    type(late).objects.filter(pk=late.pk).update(target_date=today - dt.timedelta(days=1),
                                                 created_at=now - dt.timedelta(days=4))
    child = _task(jemur, director, staf, "Pesan tirai", due_at=now + dt.timedelta(days=3),
                  source_type=SOURCE_TYPE, source_id=req.pk)
    UserRole.objects.create(user=staf, clinic=citraland, role=Role.STAF)
    _task(citraland, director, staf, "Tirai Citraland", due_at=now + dt.timedelta(days=4),
          source_type=SOURCE_TYPE, source_id=req.pk)
    _task(jemur, director, staf, "Task biasa", due_at=now + dt.timedelta(days=1))

    chart = dashboard.gantt(director)
    groups = {g["request"].title: g for g in chart["requests"]}
    assert set(groups) == {"Ganti tirai ruang facial", "Cek CCTV", "Rapikan gudang"}
    assert [g["request"].title for g in chart["requests"]][0] == "Rapikan gudang"  # lewat target paling atas
    assert groups["Rapikan gudang"]["state"] == "late" and groups["Cek CCTV"]["children"] == []
    tirai = groups["Ganti tirai ruang facial"]
    assert {r["item"].title for r in tirai["children"]} == {"Pesan tirai", "Tirai Citraland"}
    assert tirai["target_left"] is not None and tirai["state"] == "open"
    # Task turunan tidak digambar dua kali di kelompok cabang.
    assert [r["item"].title for r in chart["rows"]] == ["Task biasa"]

    # Saringan cabang: task turunan cabang lain disembunyikan; sumber lain: tanpa kelompok permintaan.
    jemur_only = dashboard.gantt(director, clinic_id=jemur.pk)
    tirai = next(g for g in jemur_only["requests"] if g["request"].pk == req.pk)
    assert [r["item"].pk for r in tirai["children"]] == [child.pk]
    assert dashboard.gantt(director, source="manual")["requests"] == []

    client.force_login(owner)
    body = client.get(reverse("direktur:gantt") + "?sumber=permintaan_owner").content.decode()
    assert "Permintaan Owner" in body and "↳ Pesan tirai" in body and "belum dipecah menjadi task" in body
    assert "Task biasa" not in body and re.search(r'class="gantt-target" style="left:\d+(\.\d+)?%"', body)
    dash = client.get(reverse("owner:dashboard")).content.decode()
    assert "?sumber=permintaan_owner" in dash
