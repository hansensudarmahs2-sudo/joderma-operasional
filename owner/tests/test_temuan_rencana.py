"""Temuan Owner sebagai task besar: batas target, sub task, penutupan oleh Direktur (6 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import ActionItem, ActionItemStatus, Clinic, TaskAssignmentStatus, local_today
from notifications.models import Notification
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


def _temuan(owner, urgent=False, title="Alur pasien baru belum seragam", **kw):
    return services.create_request(actor=owner, kind=RequestKind.TEMUAN, title=title, urgent=urgent, **kw)


def _age(req, days):
    """Mundurkan tanggal catat temuan `days` hari."""
    OwnerRequest.objects.filter(pk=req.pk).update(created_at=timezone.now() - dt.timedelta(days=days))
    req.refresh_from_db()
    return req


# --- Task 1: batas target saat dibuat ------------------------------------------


def test_urgent_finding_gets_three_day_target(yohanes):
    req = _temuan(yohanes, urgent=True)
    assert req.target_date == local_today() + dt.timedelta(days=3)
    assert services.deadline_cap(req) == local_today() + dt.timedelta(days=3)


def test_normal_finding_has_no_target_but_thirty_day_cap(yohanes):
    req = _temuan(yohanes)
    assert req.target_date is None
    assert services.deadline_cap(req) == local_today() + dt.timedelta(days=30)
    assert services.effective_target(req) == local_today() + dt.timedelta(days=30)


def test_cap_counts_from_recorded_date(yohanes):
    req = _age(_temuan(yohanes), 10)
    assert services.recorded_on(req) == local_today() - dt.timedelta(days=10)
    assert services.deadline_cap(req) == local_today() + dt.timedelta(days=20)


def test_finding_target_beyond_cap_is_rejected(yohanes):
    with pytest.raises(ValidationError, match="paling lambat"):
        _temuan(yohanes, target_date=local_today() + dt.timedelta(days=31))
    assert not OwnerRequest.objects.exists()


def test_request_has_no_cap(yohanes):
    req = services.create_request(actor=yohanes, title="Evaluasi paket", target_date=local_today() + dt.timedelta(days=90))
    assert services.deadline_cap(req) is None
    assert services.effective_target(req) == req.target_date


def test_finding_form_has_no_target_field(client, yohanes):
    client.force_login(yohanes)
    body = client.get(reverse("owner:request_new") + "?jenis=TEMUAN").content.decode()
    assert 'name="target"' not in body and "Mendesak" in body
    body = client.get(reverse("owner:request_new")).content.decode()
    assert 'name="target"' in body


def test_owner_posts_urgent_finding_without_target(client, yohanes, jemur):
    client.force_login(yohanes)
    client.post(reverse("owner:request_new"), {"jenis": "TEMUAN", "judul": "Wastafel bocor", "mendesak": "1",
                                               "target": "2099-01-01"})
    req = OwnerRequest.objects.get()
    assert req.urgent and req.target_date == local_today() + dt.timedelta(days=3)


# --- Task 2: status, rencana, penutupan ------------------------------------------


def _sub(req, clinic, status=ActionItemStatus.BARU, title="Sub task"):
    return ActionItem.objects.create(clinic=clinic, title=title, source_type="permintaan_owner", source_id=req.pk,
                                     status=status)


def test_finding_states(jemur, yohanes, hansen):
    req = _temuan(yohanes)
    assert (services.progress(req)["state"], services.progress(req)["label"]) == ("waiting", "Menunggu Direktur")
    a = _sub(req, jemur)
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    assert services.progress(req)["label"] == "Berjalan"
    a.status = ActionItemStatus.SELESAI
    a.save()
    row = services.progress(req)
    assert (row["state"], row["label"]) == ("ready", "Siap ditutup")
    services.complete_finding(req, actor=hansen)
    row = services.progress(req)
    assert (row["state"], row["label"], row["finished_late_by"]) == ("done", "Selesai & terverifikasi", 0)


def test_request_still_done_automatically(jemur, yohanes):
    req = services.create_request(actor=yohanes, title="Evaluasi paket", target_date=local_today() + dt.timedelta(days=5))
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    assert services.progress(req)["label"] == "Selesai"


def test_late_uses_effective_target(yohanes):
    req = _age(_temuan(yohanes), 32)  # batas 30 hari lewat 2 hari
    row = services.progress(req)
    assert row["late"] and row["days_late"] == 2 and not row["target_set"]
    assert row["target"] == local_today() - dt.timedelta(days=2)


def test_complete_rejected_without_or_with_open_subtasks(jemur, yohanes, hansen):
    req = _temuan(yohanes)
    with pytest.raises(ValidationError, match="belum punya sub task"):
        services.complete_finding(req, actor=hansen)
    _sub(req, jemur)
    with pytest.raises(ValidationError, match="belum selesai"):
        services.complete_finding(req, actor=hansen)
    req.refresh_from_db()
    assert req.completed_at is None


def test_only_director_completes_and_owner_is_notified(jemur, yohanes, hansen, desy):
    req = _temuan(yohanes)
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    for user in (yohanes, desy):
        with pytest.raises(PermissionDenied):
            services.complete_finding(req, actor=user)
    services.complete_finding(req, actor=hansen)
    req.refresh_from_db()
    assert req.completed_by == hansen and req.completed_at is not None
    assert Notification.objects.filter(user=yohanes, title__startswith="Temuan selesai").exists()
    with pytest.raises(ValidationError, match="sudah dinyatakan selesai"):
        services.complete_finding(req, actor=hansen)


def test_completed_late_is_reported(jemur, yohanes, hansen):
    req = _age(_temuan(yohanes, urgent=True), 5)  # target = catat + 3 = 2 hari lalu
    OwnerRequest.objects.filter(pk=req.pk).update(target_date=local_today() - dt.timedelta(days=2))
    req.refresh_from_db()
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    services.complete_finding(req, actor=hansen)
    assert services.progress(req)["finished_late_by"] == 2


def test_set_plan_limits(yohanes, hansen):
    req = _temuan(yohanes)
    services.set_plan(req, actor=hansen, plan_title="Membuat alur pasien baru",
                      target_date=local_today() + dt.timedelta(days=14))
    req.refresh_from_db()
    assert req.plan_title == "Membuat alur pasien baru" and req.target_date == local_today() + dt.timedelta(days=14)
    with pytest.raises(ValidationError, match="paling lambat"):
        services.set_plan(req, actor=hansen, plan_title="", target_date=local_today() + dt.timedelta(days=31))
    with pytest.raises(ValidationError, match="sebelum hari ini"):
        services.set_plan(req, actor=hansen, plan_title="", target_date=local_today() - dt.timedelta(days=1))
    with pytest.raises(PermissionDenied):
        services.set_plan(req, actor=yohanes, plan_title="X", target_date=None)


def test_urgent_plan_cannot_exceed_three_days_or_drop_target(yohanes, hansen):
    req = _temuan(yohanes, urgent=True)
    with pytest.raises(ValidationError, match="paling lambat"):
        services.set_plan(req, actor=hansen, plan_title="", target_date=local_today() + dt.timedelta(days=4))
    services.set_plan(req, actor=hansen, plan_title="Bereskan", target_date=None)
    req.refresh_from_db()
    assert req.target_date == local_today() + dt.timedelta(days=3)
    services.set_plan(req, actor=hansen, plan_title="", target_date=local_today() + dt.timedelta(days=1))
    req.refresh_from_db()
    assert req.target_date == local_today() + dt.timedelta(days=1)


def test_unchanged_past_target_does_not_block_plan_title(yohanes, hansen):
    req = _age(_temuan(yohanes, urgent=True), 5)
    OwnerRequest.objects.filter(pk=req.pk).update(target_date=local_today() - dt.timedelta(days=2))
    req.refresh_from_db()
    services.set_plan(req, actor=hansen, plan_title="Alur baru", target_date=req.target_date)
    req.refresh_from_db()
    assert req.plan_title == "Alur baru"


def test_urgent_open_findings_listed_first(jemur, yohanes, hansen):
    late = services.create_request(actor=yohanes, title="Lewat", target_date=local_today() + dt.timedelta(days=1))
    OwnerRequest.objects.filter(pk=late.pk).update(target_date=local_today() - dt.timedelta(days=1))
    normal = _temuan(yohanes, title="Biasa")
    urgent = _temuan(yohanes, urgent=True, title="Mendesak")
    done_urgent = _temuan(yohanes, urgent=True, title="Mendesak selesai")
    _sub(done_urgent, jemur, status=ActionItemStatus.SELESAI)
    services.complete_finding(done_urgent, actor=hansen)
    order = [r["request"].pk for r in services.request_rows(yohanes)]
    assert order == [urgent.pk, late.pk, normal.pk, done_urgent.pk]


# --- Task 3: verifikasi sub task ---------------------------------------------------


def _assigned(req, actor, clinic, person, title="Sub task", source_type="permintaan_owner"):
    from direktur.services import create_task_from_source

    return create_task_from_source(actor=actor, clinic=clinic, title=title, target=f"user:{person.pk}",
                                   source_type=source_type, source_id=req.pk)


def test_director_subtask_on_finding_completes_without_review(jemur, yohanes, hansen):
    from core.task_services import submit_assignment

    req = _temuan(yohanes)
    item = _assigned(req, hansen, jemur, hansen, title="Menulis alur tertulis")
    assert item.is_temuan_subtask and item.effective_review_by == "DIREKTUR"
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=hansen, note="Alur sudah ditulis")
    assignment.refresh_from_db()
    item.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.CONFIRMED and assignment.reviewer is None
    assert item.status == ActionItemStatus.SELESAI
    assert item.task_events.filter(note__contains="tanpa verifikasi").exists()
    assert not Notification.objects.filter(user=yohanes, title__startswith="Menunggu verifikasi").exists()


def test_director_subtask_submit_view_flashes_auto_confirmed_message(client, jemur, yohanes, hansen):
    req = _temuan(yohanes)
    item = _assigned(req, hansen, jemur, hansen, title="Menulis alur tertulis")
    assignment = item.task_assignments.get()
    client.force_login(hansen)
    resp = client.post(reverse("core:assignment_submit", args=[assignment.pk]), {"catatan": "Alur sudah ditulis"},
                       follow=True)
    text = " ".join(str(m) for m in resp.context["messages"])
    assert "Sub task selesai (task Direktur pada temuan, tanpa verifikasi)." in text
    assert "menunggu konfirmasi pemeriksa" not in text


def test_staff_subtask_on_finding_is_reviewed_by_director_not_owner(jemur, yohanes, hansen, desy):
    from core.task_services import can_review_assignment, confirm_assignment, submit_assignment

    req = _temuan(yohanes)
    item = _assigned(req, hansen, jemur, desy, title="Sosialisasi alur ke rekan shift")
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=desy, note="Sudah disosialisasikan")
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED
    assert can_review_assignment(assignment, hansen) and not can_review_assignment(assignment, yohanes)
    assert services.verification_queue(yohanes) == []
    confirm_assignment(assignment, reviewer=hansen)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI


def test_mixed_subtask_on_finding_stays_with_director(jemur, yohanes, hansen, desy):
    from core.models import TaskAudienceType
    from core.task_services import create_task

    req = _temuan(yohanes)
    item = create_task(clinic=jemur, actor=hansen, title="Evaluasi bersama", audience_type=TaskAudienceType.USERS,
                       user_ids=[hansen.pk, desy.pk], source_type="permintaan_owner", source_id=req.pk)
    assert item.effective_review_by == "DIREKTUR" and not item.reviewed_by_dirut


def test_director_task_outside_finding_still_reviewed_by_owner(jemur, yohanes, hansen):
    from core.task_services import submit_assignment

    req = services.create_request(actor=yohanes, title="Evaluasi paket", target_date=local_today() + dt.timedelta(days=5))
    item = _assigned(req, hansen, jemur, hansen, title="Hitung ulang harga")
    assert not item.is_temuan_subtask and item.reviewed_by_dirut
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=hansen)
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED


# --- Task 4: baris sub task --------------------------------------------------------


def test_subtask_rows_labels(jemur, yohanes, hansen, desy):
    from core.task_services import confirm_assignment, submit_assignment

    req = _temuan(yohanes)
    own = _assigned(req, hansen, jemur, hansen, title="Menulis alur")
    staff = _assigned(req, hansen, jemur, desy, title="Sosialisasi")
    labels = {r["task"].title: r["label"] for r in services.subtask_rows(req)}
    assert labels == {"Menulis alur": "Berjalan", "Sosialisasi": "Berjalan"}
    submit_assignment(own.task_assignments.get(), user=hansen)
    a = staff.task_assignments.get()
    submit_assignment(a, user=desy)
    rows = {r["task"].title: r for r in services.subtask_rows(req)}
    assert rows["Menulis alur"]["label"] == "Selesai oleh Direktur"
    assert rows["Sosialisasi"]["label"] == "Menunggu verifikasi"
    confirm_assignment(a, reviewer=hansen)
    rows = {r["task"].title: r for r in services.subtask_rows(req)}
    assert rows["Sosialisasi"]["label"] == "Terverifikasi Direktur"
    assert rows["Sosialisasi"]["people"] == str(desy) and rows["Sosialisasi"]["finished_at"] is not None


# --- Task 5: tampilan -------------------------------------------------------------


def test_detail_shows_subtasks_and_plan_for_owner(client, jemur, yohanes, hansen, desy):
    req = _temuan(yohanes, urgent=True)
    services.set_plan(req, actor=hansen, plan_title="Membuat alur pasien baru", target_date=None)
    _assigned(req, hansen, jemur, desy, title="Sosialisasi alur")
    client.force_login(yohanes)
    body = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert "Membuat alur pasien baru" in body and "Sosialisasi alur" in body and "Desy" in body
    assert "Berjalan" in body and "Mendesak" in body
    assert 'value="rencana"' not in body and 'value="selesai"' not in body


def test_director_sets_plan_and_completes_from_page(client, jemur, yohanes, hansen):
    req = _temuan(yohanes)
    client.force_login(hansen)
    target = (local_today() + dt.timedelta(days=10)).isoformat()
    client.post(reverse("owner:request_detail", args=[req.pk]),
                {"aksi": "rencana", "rencana": "Membuat alur", "target": target})
    req.refresh_from_db()
    assert req.plan_title == "Membuat alur" and req.target_date.isoformat() == target
    body = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert 'value="selesai"' not in body  # belum ada sub task
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    body = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert 'value="selesai"' in body and "Siap ditutup" in body
    client.post(reverse("owner:request_detail", args=[req.pk]), {"aksi": "selesai"})
    req.refresh_from_db()
    assert req.completed_by == hansen


def test_owner_cannot_post_director_actions(client, jemur, yohanes):
    req = _temuan(yohanes)
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    client.force_login(yohanes)
    url = reverse("owner:request_detail", args=[req.pk])
    assert client.post(url, {"aksi": "selesai"}).status_code == 403
    assert client.post(url, {"aksi": "rencana", "rencana": "X", "target": ""}).status_code == 403
    req.refresh_from_db()
    assert req.completed_at is None and req.plan_title == ""


def test_dashboard_shows_cap_and_completion(client, jemur, yohanes, hansen):
    open_one = _temuan(yohanes, title="Belum bertarget")
    done = _temuan(yohanes, title="Sudah beres")
    _sub(done, jemur, status=ActionItemStatus.SELESAI)
    services.complete_finding(done, actor=hansen)
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    cap = services.deadline_cap(open_one)
    assert f"Paling lambat {cap:%d/%m/%Y}" in body
    assert "Selesai &amp; terverifikasi" in body and "tepat waktu" in body and "dr. Hansen" in body


def test_overdue_urgent_plan_can_be_saved_with_past_target(client, jemur, yohanes, hansen):
    req = _age(_temuan(yohanes, urgent=True), 5)
    past = local_today() - dt.timedelta(days=1)  # beda dari cap (2 hari lalu)
    OwnerRequest.objects.filter(pk=req.pk).update(target_date=past)
    client.force_login(hansen)
    url = reverse("owner:request_detail", args=[req.pk])
    for title, raw in (("Rencana A", past.isoformat()), ("Rencana B", "")):
        client.post(url, {"aksi": "rencana", "rencana": title, "target": raw})
        req.refresh_from_db()
        assert req.plan_title == title and req.target_date == past
    body = client.get(url).content.decode()
    tag = body.split('id="target-rencana"')[1].split(">")[0]
    assert "min=" not in tag and "max=" not in tag


def test_lapsed_target_with_future_cap_does_not_block_plan_form(client, jemur, yohanes, hansen):
    req = _temuan(yohanes)
    past = local_today() - dt.timedelta(days=1)
    OwnerRequest.objects.filter(pk=req.pk).update(target_date=past)
    client.force_login(hansen)
    url = reverse("owner:request_detail", args=[req.pk])
    tag = client.get(url).content.decode().split('id="target-rencana"')[1].split(">")[0]
    assert "min=" not in tag and "max=" in tag
    client.post(url, {"aksi": "rencana", "rencana": "Rencana lama", "target": past.isoformat()})
    req.refresh_from_db()
    assert req.plan_title == "Rencana lama" and req.target_date == past


def test_urgent_permintaan_is_not_lifted_above_late_item(jemur, yohanes):
    late = services.create_request(actor=yohanes, title="Lewat", target_date=local_today() + dt.timedelta(days=1))
    OwnerRequest.objects.filter(pk=late.pk).update(target_date=local_today() - dt.timedelta(days=1))
    perm = services.create_request(actor=yohanes, title="Permintaan", target_date=local_today() + dt.timedelta(days=5))
    OwnerRequest.objects.filter(pk=perm.pk).update(urgent=True)
    order = [r["request"].pk for r in services.request_rows(yohanes)]
    assert order == [late.pk, perm.pk]


def test_subtask_without_assignments_done_label(jemur, yohanes):
    req = _temuan(yohanes)
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    assert services.subtask_rows(req)[0]["label"] == "Selesai oleh Direktur"
