"""Bintang 1–5 untuk staf pada task yang selesai (keputusan PO 8 Okt 2026)."""
from __future__ import annotations

import datetime as dt
import importlib

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from audit.models import AuditEvent
from core import task_services as ts
from core.models import ActionItemStatus, Clinic, TaskAssignment, TaskAssignmentStatus, TaskAudienceType
from direktur import kpi
from notifications.models import Notification
from projects import services as ps

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title(), **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur", name="Jemur", open_time="14:00", close_time="22:00")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen", Role.AOM)


@pytest.fixture
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER)


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.FRONT_DESK)


@pytest.fixture
def yani(jemur):
    return _user(jemur, "yani", Role.PERAWAT)


def _task(actor, jemur, *people, title="Rapikan meja"):
    return ts.create_task(clinic=jemur, actor=actor, title=title,
                          audience_type=TaskAudienceType.USERS if len(people) > 1 else TaskAudienceType.USER,
                          user_ids=[p.pk for p in people])


def _submitted(actor, jemur, person, title="Rapikan meja"):
    item = _task(actor, jemur, person, title=title)
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=person, note="beres")
    return TaskAssignment.objects.get(pk=a.pk)


# --- Data migration -----------------------------------------------------------------------


def test_migration_rates_existing_confirmed_five_auto(hansen, desy, yohanes, jemur):
    migration = importlib.import_module("core.migrations.0011_kategori_bintang_data")
    done = _task(hansen, jemur, desy, title="Lama").task_assignments.get()
    confirmed_at = timezone.now() - dt.timedelta(days=40)
    TaskAssignment.objects.filter(pk=done.pk).update(status=TaskAssignmentStatus.CONFIRMED, confirmed_at=confirmed_at)
    no_time = _task(hansen, jemur, desy, title="Lama tanpa waktu").task_assignments.get()
    TaskAssignment.objects.filter(pk=no_time.pk).update(status=TaskAssignmentStatus.CONFIRMED, confirmed_at=None)
    director = _task(yohanes, jemur, hansen, title="Kerjaan Direktur").task_assignments.get()
    TaskAssignment.objects.filter(pk=director.pk).update(status=TaskAssignmentStatus.CONFIRMED)
    waiting = _submitted(hansen, jemur, desy, title="Masih diajukan")
    migration.auto_rate_confirmed(django_apps, None)
    done.refresh_from_db()
    assert (done.rating, done.rating_auto, done.rated_by, done.rating_note) == (5, True, None, "")
    assert done.rated_at == confirmed_at
    no_time.refresh_from_db()
    assert no_time.rating == 5 and no_time.rated_at is not None
    director.refresh_from_db()
    waiting.refresh_from_db()
    assert director.rating is None and waiting.rating is None


# --- Konfirmasi ---------------------------------------------------------------------------


def test_confirm_requires_stars_for_staff(hansen, desy, jemur):
    a = _submitted(hansen, jemur, desy)
    with pytest.raises(ValidationError, match="Pilih bintang"):
        ts.confirm_assignment(a, reviewer=hansen)
    with pytest.raises(ValidationError, match="Bintang harus 1–5"):
        ts.confirm_assignment(a, reviewer=hansen, rating=6)
    for low in (1, 2, 3):
        with pytest.raises(ValidationError, match="Tulis alasan untuk bintang 1–3"):
            ts.confirm_assignment(a, reviewer=hansen, rating=low, rating_note="  ")
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.SUBMITTED and a.rating is None
    ts.confirm_assignment(a, reviewer=hansen, rating=4)
    a.refresh_from_db()
    assert (a.status, a.rating, a.rated_by, a.rating_auto, a.rating_note) == (
        TaskAssignmentStatus.CONFIRMED, 4, hansen, False, "")
    assert a.rated_at == a.confirmed_at


def test_low_rating_with_note_and_notification(hansen, desy, jemur):
    a = _submitted(hansen, jemur, desy)
    Notification.objects.all().delete()
    ts.confirm_assignment(a, reviewer=hansen, rating=2, rating_note="Masih berdebu di sudut")
    a.refresh_from_db()
    assert a.rating == 2 and a.rating_note == "Masih berdebu di sudut"
    n = Notification.objects.get(user=desy)
    assert n.type_code == "TASK_RATED"
    assert n.title.startswith("Task dinilai: ★★☆☆☆") and "Rapikan meja" in n.title
    assert n.body == "Masih berdebu di sudut"
    assert n.url == reverse("core:today") + "#nilai-saya"


def test_director_or_owner_assignee_confirmed_without_stars(hansen, yohanes, jemur):
    a = _submitted(yohanes, jemur, hansen, title="Kerjaan Direktur")  # diperiksa Dirut/Owner
    ts.confirm_assignment(a, reviewer=yohanes)
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and a.rating is None
    assert Notification.objects.filter(user=hansen, type_code="TASK_CONFIRMED").exists()
    assert not ts.needs_rating(hansen) and not ts.needs_rating(yohanes)


def test_owner_verifier_gives_stars(client, hansen, yohanes, desy, jemur):
    """Task yang pemeriksanya ditetapkan Dirut: Owner yang mengonfirmasi juga memberi bintang."""
    item = _task(hansen, jemur, desy, title="Diperiksa Dirut")
    item.review_by = "DIRUT"
    item.save()
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=desy, note="beres")
    client.force_login(yohanes)
    url = reverse("direktur:task_detail", args=[item.pk])
    page = client.get(url).content.decode()
    assert 'name="bintang"' in page and "5 bintang" in page
    client.post(url, {"aksi": "konfirmasi", "assignment": a.pk})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.SUBMITTED  # tanpa bintang ditolak
    client.post(url, {"aksi": "konfirmasi", "assignment": a.pk, "bintang": "5"})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and a.rating == 5 and a.rated_by == yohanes


def test_confirm_via_core_view_with_stars(client, jemur, desy):
    spv = _user(jemur, "spv", Role.SUPERVISOR, Role.PIC)
    a = _submitted(spv, jemur, desy)
    client.force_login(spv)
    page = client.get(reverse("core:action_items")).content.decode()
    assert 'name="bintang"' in page and "1 bintang" in page
    client.post(reverse("core:assignment_confirm", args=[a.pk]), {"bintang": "3"})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.SUBMITTED
    client.post(reverse("core:assignment_confirm", args=[a.pk]), {"bintang": "3", "catatan_bintang": "Kurang rapi"})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and (a.rating, a.rating_note) == (3, "Kurang rapi")


# --- Tutup task -------------------------------------------------------------------------


def test_close_task_applies_rating_to_all(hansen, desy, yani, jemur):
    item = _task(hansen, jemur, desy, yani, title="Bersama")
    with pytest.raises(ValidationError, match="Pilih bintang"):
        ts.close_task(item, actor=hansen, note="beres")
    with pytest.raises(ValidationError, match="Tulis alasan"):
        ts.close_task(item, actor=hansen, note="beres", rating=1)
    ts.close_task(item, actor=hansen, note="beres", rating=4, rating_note="")
    rows = list(item.task_assignments.order_by("assignee__username"))
    assert [(a.status, a.rating, a.rated_by) for a in rows] == [
        (TaskAssignmentStatus.CONFIRMED, 4, hansen), (TaskAssignmentStatus.CONFIRMED, 4, hansen)]
    assert Notification.objects.filter(type_code="TASK_RATED").count() == 2


def test_close_task_via_view_shows_picker(client, hansen, desy, jemur):
    item = _task(hansen, jemur, desy)
    client.force_login(hansen)
    url = reverse("direktur:task_detail", args=[item.pk])
    assert "Bintang untuk Desy" in client.get(url).content.decode()
    client.post(url, {"aksi": "selesai", "catatan": "dicek bersama", "bintang": "5"})
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI and item.task_assignments.get().rating == 5


# --- Task project: belum dinilai, dinilai pengatur ---------------------------------------


@pytest.fixture
def project(hansen, desy):
    return ps.create_project(actor=hansen, name="Renovasi", leader=desy, target_date=dt.date(2099, 12, 31))


def test_project_auto_confirm_is_unrated_then_manager_rates(client, project, hansen, desy, yani, jemur):
    item = ps.add_task(project, actor=hansen, title="Cat dinding", user_ids=[yani.pk], clinic=jemur)
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=yani, note="")
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and a.rating is None
    url = reverse("projects:task_detail", args=[project.pk, item.pk])
    client.force_login(desy)  # Project leader staf
    page = client.get(url).content.decode()
    assert "Belum dinilai" in page and "Beri bintang" in page
    client.post(url, {"aksi": "nilai", "assignment": a.pk, "bintang": "2"})
    a.refresh_from_db()
    assert a.rating is None  # bintang 2 tanpa alasan ditolak
    client.post(url, {"aksi": "nilai", "assignment": a.pk, "bintang": "5"})
    a.refresh_from_db()
    assert (a.rating, a.rated_by, a.rating_auto) == (5, desy, False)
    assert Notification.objects.filter(user=yani, type_code="TASK_RATED").exists()


def test_project_recipient_cannot_rate(client, project, hansen, yani, jemur):
    other = _user(jemur, "rina", Role.STAF)
    item = ps.add_task(project, actor=hansen, title="Pasang rak", user_ids=[yani.pk, other.pk], clinic=jemur)
    mine = item.task_assignments.get(assignee=yani)
    theirs = item.task_assignments.get(assignee=other)
    ts.submit_assignment(mine, user=yani, note="")
    ts.submit_assignment(theirs, user=other, note="")
    url = reverse("projects:task_detail", args=[project.pk, item.pk])
    client.force_login(yani)
    for a in (mine, theirs):
        assert client.post(url, {"aksi": "nilai", "assignment": a.pk, "bintang": "5"}).status_code == 403
    with pytest.raises(PermissionDenied):
        ts.rate_assignment(mine, actor=yani, rating=5)
    assert not TaskAssignment.objects.filter(rating__isnull=False).exists()


def test_reopen_clears_rating(project, hansen, desy, yani, jemur):
    item = ps.add_task(project, actor=hansen, title="Ganti lampu", user_ids=[yani.pk], clinic=jemur)
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=yani, note="")
    ts.rate_assignment(a, actor=hansen, rating=3, note="Kabel berantakan")
    ps.reopen_assignment(TaskAssignment.objects.get(pk=a.pk), actor=desy, note="Rapikan kabel")
    a.refresh_from_db()
    assert (a.rating, a.rating_note, a.rated_by, a.rated_at) == (None, "", None, None)
    ts.submit_assignment(a, user=yani, note="")
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED and a.rating is None


# --- Nilai kemudian / ubah bintang --------------------------------------------------------


def test_rerate_overwrites_and_is_audited(client, hansen, desy, jemur):
    a = _submitted(hansen, jemur, desy)
    ts.confirm_assignment(a, reviewer=hansen, rating=5)
    client.force_login(hansen)
    url = reverse("direktur:task_detail", args=[a.action_item_id])
    assert "Ubah bintang" in client.get(url).content.decode()
    client.post(url, {"aksi": "nilai", "assignment": a.pk, "bintang": "3", "catatan_bintang": "Ternyata belum rapi"})
    a.refresh_from_db()
    assert (a.rating, a.rating_note) == (3, "Ternyata belum rapi")
    events = AuditEvent.objects.filter(entity_type="bintang_task", entity_id=str(a.pk)).order_by("pk")
    assert events.count() == 2
    last = events.last()
    assert last.actor == hansen and last.before_json["rating"] == 5 and last.after_json["rating"] == 3


def test_rate_later_unrated_confirmed(hansen, desy, jemur):
    a = _task(hansen, jemur, desy).task_assignments.get()
    TaskAssignment.objects.filter(pk=a.pk).update(status=TaskAssignmentStatus.CONFIRMED, confirmed_at=timezone.now())
    with pytest.raises(PermissionDenied):
        ts.rate_assignment(a, actor=desy, rating=5)
    ts.rate_assignment(a, actor=hansen, rating=4)
    a.refresh_from_db()
    assert a.rating == 4
    open_a = _task(hansen, jemur, desy, title="Belum selesai").task_assignments.get()
    with pytest.raises(ValidationError, match="sudah selesai"):
        ts.rate_assignment(open_a, actor=hansen, rating=4)


# --- Siapa melihat ------------------------------------------------------------------------


def test_staff_sees_own_rating_not_others(client, hansen, desy, yani, jemur):
    mine = _submitted(hansen, jemur, desy, title="Punya Desy")
    ts.confirm_assignment(mine, reviewer=hansen, rating=2, rating_note="Telat lapor")
    theirs = _submitted(hansen, jemur, yani, title="Punya Yani")
    ts.confirm_assignment(theirs, reviewer=hansen, rating=5)
    client.force_login(desy)
    page = client.get(reverse("core:today")).content.decode()
    assert 'id="nilai-saya"' in page and "Punya Desy" in page and "Telat lapor" in page
    assert "Punya Yani" not in page
    assert "rata-rata <strong>2,0</strong>" in page  # format angka Indonesia
    assert client.get(reverse("direktur:task_detail", args=[theirs.action_item_id])).status_code == 403


# --- KPI ----------------------------------------------------------------------------------


def test_kpi_average_includes_auto_and_csv(client, hansen, yohanes, desy, yani, jemur):
    for rating in (4, 2):
        a = _submitted(hansen, jemur, desy, title=f"Task {rating}")
        ts.confirm_assignment(a, reviewer=hansen, rating=rating, rating_note="cukup")
    auto = _task(hansen, jemur, desy, title="Lama").task_assignments.get()
    TaskAssignment.objects.filter(pk=auto.pk).update(
        status=TaskAssignmentStatus.CONFIRMED, confirmed_at=timezone.now(), rating=5, rating_auto=True)
    director = _submitted(yohanes, jemur, hansen, title="Direktur")
    ts.confirm_assignment(director, reviewer=yohanes)
    first = timezone.localdate().replace(day=1)
    rows = {p.user.username: p for p in kpi.compose([jemur], first)}
    assert rows["desy"].rating_avg == round(11 / 3, 1) and rows["desy"].rating_count == 3
    assert "yani" not in rows or rows["yani"].rating_avg is None
    assert rows.get("hansen") is None or rows["hansen"].rating_count == 0
    client.force_login(hansen)
    page = client.get(reverse("direktur:kpi")).content.decode()
    assert "Bintang rata-rata" in page and "3 dinilai" in page
    csv = client.get(reverse("direktur:kpi"), {"unduh": "csv"}).content.decode("utf-8-sig")
    header, *lines = csv.splitlines()
    assert header.endswith("Bintang rata-rata,Task dinilai")
    desy_line = next(line for line in lines if ",desy," in line)
    assert desy_line.endswith(f"{round(11 / 3, 1)},3")


# --- Review 9 Okt 2026: audit, task bersama, hak menilai -----------------------------------


def _audit_csv(response):
    return b"".join(response.streaming_content).decode("utf-8")


def test_rating_audit_hidden_from_supervisor_and_admin(client, hansen, desy, jemur):
    from accounts.models import Capability, UserCapability

    a = _submitted(hansen, jemur, desy, title="Rapikan arsip")
    ts.confirm_assignment(a, reviewer=hansen, rating=2, rating_note="Catatan bintang rahasia")
    spv = _user(jemur, "spv", Role.SUPERVISOR, Role.STAF)
    admin = _user(jemur, "superadmin", Role.ADMIN)
    UserCapability.objects.create(user=admin, capability=Capability.ADMIN_FULL_ACCESS)
    for viewer in (spv, admin):
        client.force_login(viewer)
        page = client.get(reverse("audit:log")).content.decode()
        assert "Catatan bintang rahasia" not in page and "rating" not in page and "bintang_task" not in page
        page = client.get(reverse("audit:log"), {"entitas": "bintang"}).content.decode()
        assert "Catatan bintang rahasia" not in page
    client.force_login(spv)
    assert client.get(reverse("audit:export")).status_code == 403
    client.force_login(admin)
    csv = _audit_csv(client.get(reverse("audit:export")))
    assert "Catatan bintang rahasia" not in csv and "bintang_task" not in csv
    client.force_login(hansen)  # Owner tidak membuka menu Audit sama sekali (tampilan Owner)
    assert "Catatan bintang rahasia" in client.get(reverse("audit:log")).content.decode()
    assert "Catatan bintang rahasia" in _audit_csv(client.get(reverse("audit:export")))


def test_reopen_does_not_leak_rating_in_actionitem_audit(project, hansen, desy, yani, jemur):
    item = ps.add_task(project, actor=hansen, title="Ganti kunci", user_ids=[yani.pk], clinic=jemur)
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=yani, note="")
    ts.rate_assignment(a, actor=hansen, rating=3, note="Kurang rapi")
    ps.reopen_assignment(TaskAssignment.objects.get(pk=a.pk), actor=desy, note="Ulangi")
    for ev in AuditEvent.objects.exclude(entity_type="bintang_task"):
        assert "bintang" not in str(ev.after_json) and "rating" not in str(ev.after_json)
    assert AuditEvent.objects.filter(entity_type="bintang_task", entity_id=str(a.pk)).count() == 2


def test_close_shared_task_rates_only_claimer(hansen, desy, yani, jemur):
    item = ts.create_task(clinic=jemur, actor=hansen, title="Cukup satu", audience_type=TaskAudienceType.USERS,
                          user_ids=[desy.pk, yani.pk], mode="BERSAMA")
    ts.claim_shared_task(item.task_assignments.get(assignee=desy), user=desy)
    Notification.objects.all().delete()
    ts.close_task(item, actor=hansen, note="beres", rating=4)
    rows = {a.assignee.username: a for a in item.task_assignments.all()}
    assert rows["desy"].rating == 4 and rows["yani"].rating is None
    assert list(Notification.objects.filter(type_code="TASK_RATED").values_list("user__username", flat=True)) == ["desy"]


def test_close_unclaimed_shared_task_rates_nobody(client, hansen, desy, yani, jemur):
    item = ts.create_task(clinic=jemur, actor=hansen, title="Belum diambil", audience_type=TaskAudienceType.USERS,
                          user_ids=[desy.pk, yani.pk], mode="BERSAMA")
    client.force_login(hansen)
    url = reverse("direktur:task_detail", args=[item.pk])
    page = client.get(url).content.decode()
    assert "tidak ada yang dinilai" in page and 'name="bintang"' not in page
    ts.close_task(item, actor=hansen, note="beres")  # tanpa bintang: tidak ada yang dinilai
    assert not TaskAssignment.objects.filter(action_item=item, rating__isnull=False).exists()
    a = item.task_assignments.get(assignee=yani)
    ts.rate_assignment(a, actor=hansen, rating=5)
    a.refresh_from_db()
    assert a.rating == 5


def test_dirut_reviewed_task_only_owner_rates(hansen, yohanes, desy, jemur):
    item = _task(hansen, jemur, desy, title="Diperiksa Dirut")
    item.review_by = "DIRUT"
    item.save()
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=desy, note="beres")
    ts.confirm_assignment(a, reviewer=yohanes, rating=5)
    with pytest.raises(PermissionDenied):
        ts.rate_assignment(a, actor=hansen, rating=1, note="timpa")
    ts.rate_assignment(a, actor=yohanes, rating=4)
    a.refresh_from_db()
    assert a.rating == 4 and a.rated_by == yohanes


def test_former_project_manager_loses_rating_right(project, hansen, desy, yani, jemur):
    sb = _user(jemur, "rudi", Role.STAF)
    project.co_leaders.add(sb)
    item = ps.add_task(project, actor=hansen, title="Pasang tirai", user_ids=[yani.pk], clinic=jemur)
    a = item.task_assignments.get()
    ts.submit_assignment(a, user=yani, note="")
    ts.rate_assignment(a, actor=sb, rating=4)
    TaskAssignment.objects.filter(pk=a.pk).update(reviewer=sb)
    project.co_leaders.remove(sb)
    with pytest.raises(PermissionDenied):
        ts.rate_assignment(TaskAssignment.objects.get(pk=a.pk), actor=sb, rating=1, note="x")
