"""Tahap 3 paket F: KPI per staf per bulan (angka per metrik, tanpa skor gabungan)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from audit.models import AuditAction, AuditEvent as AuditLog
from checklists.models import ChecklistArea, ChecklistResponse, ChecklistRun, ChecklistSession, ChecklistTemplate
from checklists.models import ResponseResult
from core.models import ActionItem, Clinic, ClinicConfig, DayStatus, OperationalDay, TaskAssignment
from core.models import TaskAssignmentStatus, TaskEvent, TaskEventType, local_today
from direktur import kpi
from jadwal.models import DutyAssignment, DutyGroup, DutyPortion, DutyRoster, DutyStatus
from jejak.models import Confidence, Event, PresenceStamp

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _at(day, hh, mm, ss=0):
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hh, mm, ss)), timezone.get_current_timezone())


@pytest.fixture
def month():
    return kpi.shift_month(local_today().replace(day=1), -1)


@pytest.fixture
def setup(month):
    jemur = Clinic.objects.create(code="jemur", name="JoDerma Jemur", open_time="12:00", close_time="21:00")
    people = {
        "hansen": _user(jemur, "hansen1", Role.AOM),
        "jean": _user(jemur, "jean", Role.OWNER),
        "ani": _user(jemur, "ani", Role.FRONT_DESK, Role.STAF),
        "budi": _user(jemur, "budi", Role.PERAWAT, Role.STAF),
    }
    day = month + dt.timedelta(days=2)
    op = OperationalDay.objects.create(clinic=jemur, date=day, status=DayStatus.CLOSED)
    tpl = ChecklistTemplate.objects.create(clinic=jemur, name="Akses umum", area=ChecklistArea.AKSES_UMUM, version=1)
    opening = ChecklistRun.objects.create(operational_day=op, template=tpl, area=tpl.area,
                                          session=ChecklistSession.OPENING, template_snapshot={})
    tpl2 = ChecklistTemplate.objects.create(clinic=jemur, name="Lain", area=ChecklistArea.RUANG_TINDAKAN, version=1)
    anytime = ChecklistRun.objects.create(operational_day=op, template=tpl2, area=tpl2.area,
                                          session=ChecklistSession.ANYTIME, template_snapshot={})
    portion = DutyPortion.objects.create(clinic=jemur, code="opening-1", name="Opening · Pintu", group=DutyGroup.OPENING)
    DutyAssignment.objects.create(portion=portion, clinic=jemur, date=day, user=people["ani"])
    DutyRoster.objects.create(user=people["ani"], date=day, home_clinic=jemur, clinic=jemur, status=DutyStatus.MASUK)

    def resp(run, label, who=None, at=None, portion_code="opening-1"):
        return ChecklistResponse.objects.create(
            run=run, item_snapshot={}, label=label, portion=portion_code,
            result=ResponseResult.OK if who else ResponseResult.BELUM, checked_by=who, checked_at=at)

    resp(opening, "Pintu", people["ani"], _at(day, 11, 50))  # tepat waktu
    resp(opening, "Lampu", people["ani"], _at(day, 12, 20))  # lewat 12.15
    resp(opening, "AC", people["budi"], _at(day, 11, 55))  # diambil alih budi
    resp(opening, "Kursi")  # belum dicek
    # Penutupan tidak punya batas jam (menunggu pasien terakhir, keputusan 4 Okt): butir penutupan
    # yang diisi lewat tengah malam tidak memengaruhi angka tepat waktu.
    tpl3 = ChecklistTemplate.objects.create(clinic=jemur, name="Tutup", area=ChecklistArea.KEBERSIHAN, version=1)
    closing = ChecklistRun.objects.create(operational_day=op, template=tpl3, area=tpl3.area,
                                          session=ChecklistSession.CLOSING, template_snapshot={})
    resp(closing, "Kunci pintu", people["ani"], _at(day + dt.timedelta(days=1), 0, 40), portion_code="")
    for i in range(5):  # budi: 5 butir dalam 40 detik -> satu tanda centang massal
        resp(anytime, f"Rak {i}", people["budi"], _at(day, 14, 0, i * 10), portion_code="")

    for conf in (Confidence.KUAT, Confidence.KUAT, Confidence.LEMAH):
        s = PresenceStamp.objects.create(user=people["ani"], clinic=jemur, event=Event.CHECKLIST, confidence=conf)
        PresenceStamp.objects.filter(pk=s.pk).update(created_at=_at(day, 12, 0))
    s = PresenceStamp.objects.create(user=people["jean"], clinic=jemur, event=Event.LOGIN, confidence=Confidence.KUAT)
    PresenceStamp.objects.filter(pk=s.pk).update(created_at=_at(day, 12, 0))

    def task(title, due, status):
        item = ActionItem.objects.create(clinic=jemur, title=title, source_type="manual", due_at=due,
                                         created_by=people["hansen"])
        return TaskAssignment.objects.create(action_item=item, assignee=people["ani"], status=status)

    done = task("Rapikan rak", _at(day, 18, 0), TaskAssignmentStatus.SUBMITTED)
    for kind, at in ((TaskEventType.SUBMITTED, _at(day, 17, 0)), (TaskEventType.REVISION_REQUESTED, _at(day, 19, 0)),
                     (TaskEventType.SUBMITTED, _at(day + dt.timedelta(days=1), 10, 0))):
        ev = TaskEvent.objects.create(action_item=done.action_item, assignment=done, event_type=kind)
        TaskEvent.objects.filter(pk=ev.pk).update(created_at=at)
    task("Ganti label", _at(day, 18, 0), TaskAssignmentStatus.OPEN)
    return {"clinic": jemur, "day": day, **people}


def test_helpers():
    assert kpi.parse_month("2026-10") == dt.date(2026, 10, 1)
    assert kpi.parse_month("bukan") == local_today().replace(day=1)
    assert kpi.shift_month(dt.date(2026, 1, 1), -1) == dt.date(2025, 12, 1)
    assert kpi.month_end(dt.date(2026, 2, 1)) == dt.date(2026, 2, 28)
    t0 = timezone.now()
    burst = [t0 + dt.timedelta(seconds=s) for s in (0, 10, 20, 30, 40)]
    spread = [t0 + dt.timedelta(minutes=m) for m in (5, 7, 9, 11)]
    assert [b["count"] for b in kpi.find_bursts(burst + spread, 5, 60)] == [5]
    assert kpi.find_bursts(burst[:4], 5, 60) == []


def test_metrics(setup, month):
    rows = {p.user.username: p for p in kpi.compose([setup["clinic"]], month)}
    assert set(rows) == {"ani", "budi"}  # Owner tidak dihitung; Direktur tanpa data tidak tampil
    ani, budi = rows["ani"], rows["budi"]
    assert (ani.duty_days, ani.items, ani.filled, ani.taken_over) == (1, 4, 3, 1)
    assert ani.filled_pct == 75
    assert (ani.opening_own, ani.opening_late, ani.opening_pct) == (2, 1, 50)
    assert (ani.stamps_total, ani.stamps_good, ani.stamps_pct) == (3, 2, 67)
    # Pengajuan pertama 17.00 sebelum target 18.00 tetap dihitung tepat walau ada revisi.
    assert (ani.tasks_due, ani.tasks_on_time, ani.tasks_late, ani.tasks_pending, ani.revisions) == (2, 1, 0, 1, 1)
    assert ani.bursts == 0
    assert (budi.items, budi.filled_pct, budi.opening_own, budi.opening_late, budi.bursts) == (0, None, 1, 0, 1)
    row = ani.days[setup["day"]]
    assert row.taken_over_by == {"Budi"} and row.portions == ["Opening · Pintu"]

    # Toleransi diubah per cabang lewat Konfigurasi: 30 menit -> butir 12.20 jadi tepat waktu.
    ClinicConfig.set(setup["clinic"], kpi.OPEN_TOLERANCE_KEY, 30)
    ani = next(p for p in kpi.compose([setup["clinic"]], month) if p.user.username == "ani")
    assert ani.opening_late == 0
    # Bulan yang belum datang kosong.
    assert kpi.compose([setup["clinic"]], kpi.shift_month(month, 2)) == []


def test_today_counts_only_after_day_closed(setup):
    clinic, ani = setup["clinic"], setup["ani"]
    today = local_today()
    op = OperationalDay.objects.create(clinic=clinic, date=today, status=DayStatus.OPEN)
    tpl = ChecklistTemplate.objects.create(clinic=clinic, name="Hari ini", area=ChecklistArea.KOMPUTER_SISTEM, version=1)
    run = ChecklistRun.objects.create(operational_day=op, template=tpl, area=tpl.area,
                                      session=ChecklistSession.OPENING, template_snapshot={})
    ChecklistResponse.objects.create(run=run, item_snapshot={}, label="PC", portion="opening-1")
    DutyAssignment.objects.create(portion=DutyPortion.objects.get(code="opening-1"), clinic=clinic, date=today, user=ani)
    first = today.replace(day=1)
    p = next((p for p in kpi.compose([clinic], first) if p.user == ani), None)
    assert p is not None and p.items == 0
    op.status = DayStatus.CLOSED
    op.save()
    p = next(p for p in kpi.compose([clinic], first) if p.user == ani)
    assert (p.items, p.filled) == (1, 0)


def test_pages_access_and_csv(client, setup, month):
    q = f"?bulan={month:%Y-%m}"
    client.force_login(setup["hansen"])
    body = client.get(reverse("direktur:kpi") + q).content.decode()
    assert "Ani" in body and "Budi" in body and "75%" in body and "1× centang massal" in body
    assert "Jean" not in body
    detail = client.get(reverse("direktur:kpi_staff", args=[setup["ani"].pk]) + q).content.decode()
    assert "1 dari 2 terlambat" in detail and "batas 12.15" in detail and "Rapikan rak" in detail and "Belum diajukan" in detail
    resp = client.get(reverse("direktur:kpi") + q + "&unduh=csv")
    assert resp["Content-Type"].startswith("text/csv")
    lines = resp.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Bulan,Username,Nama,Hari jaga")
    assert any(line.startswith(f"{month:%Y-%m},ani,Ani,1,4,3,75,1,2,1,50,3,2,67,2,1,0,1,50,1,0") for line in lines)
    assert AuditLog.objects.filter(action=AuditAction.EXPORT, entity_type="kpi").exists()

    client.force_login(setup["jean"])  # Owner: baca saja
    assert client.get(reverse("direktur:kpi") + q).status_code == 200
    assert client.get(reverse("direktur:kpi_staff", args=[setup["ani"].pk]) + q).status_code == 200
    client.force_login(setup["ani"])  # staf tidak melihat KPI selama uji coba
    assert client.get(reverse("direktur:kpi") + q).status_code == 403
    assert client.get(reverse("direktur:kpi_staff", args=[setup["ani"].pk]) + q).status_code == 403
