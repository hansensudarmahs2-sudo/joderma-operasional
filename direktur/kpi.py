"""KPI per staf (tahap 3 paket F, K-016): angka per metrik per bulan, tanpa skor gabungan.

Keputusan product owner 3 Okt 2026 untuk masa uji coba:
- empat metrik: kelengkapan porsi, pembukaan tepat waktu, jejak di klinik, task;
- ditampilkan sebagai angka per metrik, tanpa skor gabungan dan tanpa peringkat;
- hanya Direktur Operasional dan Owner yang melihat;
- toleransi jam buka 15 menit, periode bulanan, tanda "centang massal" bila >= 5 butir dalam
  60 detik (tanda untuk dicek, bukan pengurang nilai). Nilai dapat diubah per cabang di
  Konfigurasi (`kpi.*`).

Definisi:
- **Kelengkapan porsi**: butir checklist dari porsi yang ditugaskan kepadanya (Pembagian Tugas)
  yang terisi. "Diambil alih" = terisi oleh orang yang tidak ditugaskan di porsi itu hari itu.
  Hari ini baru dihitung bila hari operasionalnya sudah ditutup.
- **Pembukaan tepat waktu**: butir sesi Pembukaan yang ia isi sendiri, selesai sebelum jam buka
  cabang + toleransi. Penutupan sengaja tanpa batas jam: tutup bisa molor menunggu pasien terakhir
  (keputusan product owner 4 Okt 2026). Jangan menambah tenggat penutupan tanpa keputusan baru.
- **Jejak di klinik**: persentase jejak Kuat + Sedang dari seluruh jejaknya.
- **Task**: task individual (atau task bersama yang ia ambil) dengan target pada bulan itu yang
  sudah lewat: diajukan sebelum target, terlambat, atau belum diajukan; plus jumlah diminta revisi
  pada bulan itu. Task yang dibatalkan atau sedang menunggu keputusan bersama tidak dihitung.
- **Bintang rata-rata** (8 Okt 2026): rata-rata bintang 1–5 pada assignment yang dikonfirmasi
  (`confirmed_at`) pada bulan itu, disertai jumlahnya ("n dinilai"). Bintang otomatis 5 untuk task
  lama (`rating_auto`) **ikut** dihitung (keputusan PO). Yang belum dinilai (mis. task project yang
  belum diberi bintang pengaturnya) tidak dihitung. Direktur Operasional dan Owner tidak dinilai,
  jadi tidak pernah punya angka ini. Tetap tanpa skor gabungan: bintang tampil sebagai metrik sendiri.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import F, Min, Q
from django.utils import timezone

from core.models import ClinicConfig, local_today

OPEN_TOLERANCE_KEY = "kpi.open_tolerance_minutes"
BULK_ITEMS_KEY = "kpi.bulk_items"
BULK_SECONDS_KEY = "kpi.bulk_seconds"


def parse_month(raw: str | None) -> dt.date:
    """'2026-10' -> 1 Okt 2026. Tidak valid atau kosong -> bulan ini."""
    try:
        year, month = (int(x) for x in (raw or "").split("-")[:2])
        return dt.date(year, month, 1)
    except (TypeError, ValueError):
        return local_today().replace(day=1)


def month_end(first: dt.date) -> dt.date:
    return first.replace(day=calendar.monthrange(first.year, first.month)[1])


def shift_month(first: dt.date, delta: int) -> dt.date:
    index = first.year * 12 + first.month - 1 + delta
    return dt.date(index // 12, index % 12 + 1, 1)


def _aware(day: dt.date, time: dt.time) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, time), timezone.get_current_timezone())


def pct(part: int, whole: int) -> int | None:
    return round(part * 100 / whole) if whole else None


def find_bursts(times: list[dt.datetime], min_items: int, seconds: int) -> list[dict]:
    """Kelompok >= min_items centangan dalam rentang `seconds` detik. Tidak tumpang tindih."""
    times = sorted(times)
    bursts, i, window = [], 0, dt.timedelta(seconds=seconds)
    while i < len(times):
        j = i
        while j + 1 < len(times) and times[j + 1] - times[i] <= window:
            j += 1
        if j - i + 1 >= min_items:
            bursts.append({"start": times[i], "end": times[j], "count": j - i + 1})
            i = j + 1
        else:
            i += 1
    return bursts


@dataclass
class DayRow:
    date: dt.date
    clinic: object = None
    duty: str = ""
    portions: list = field(default_factory=list)
    items: int = 0
    filled: int = 0
    taken_over: int = 0
    taken_over_by: set = field(default_factory=set)
    opening_own: int = 0
    opening_late: int = 0
    latest_opening: dt.datetime | None = None
    opening_deadline: dt.datetime | None = None
    stamps: dict = field(default_factory=lambda: {"KUAT": 0, "SEDANG": 0, "LEMAH": 0})
    bursts: list = field(default_factory=list)


@dataclass
class StaffKpi:
    user: object
    duty_days: int = 0
    items: int = 0
    filled: int = 0
    taken_over: int = 0
    opening_own: int = 0
    opening_late: int = 0
    stamps_total: int = 0
    stamps_good: int = 0
    tasks_due: int = 0
    tasks_on_time: int = 0
    tasks_late: int = 0
    tasks_pending: int = 0
    revisions: int = 0
    bursts: int = 0
    rating_sum: int = 0
    rating_count: int = 0
    days: dict = field(default_factory=dict)
    tasks: list = field(default_factory=list)

    def day(self, date, clinic=None) -> DayRow:
        row = self.days.get(date)
        if row is None:
            row = self.days[date] = DayRow(date=date, clinic=clinic)
        elif clinic is not None and row.clinic is None:
            row.clinic = clinic
        return row

    @property
    def filled_pct(self):
        return pct(self.filled, self.items)

    @property
    def opening_on_time(self) -> int:
        return self.opening_own - self.opening_late

    @property
    def opening_pct(self):
        return pct(self.opening_on_time, self.opening_own)

    @property
    def stamps_pct(self):
        return pct(self.stamps_good, self.stamps_total)

    @property
    def tasks_pct(self):
        return pct(self.tasks_on_time, self.tasks_due)

    @property
    def rating_avg(self) -> float | None:
        return round(self.rating_sum / self.rating_count, 1) if self.rating_count else None

    @property
    def day_rows(self) -> list[DayRow]:
        return [self.days[d] for d in sorted(self.days)]


def _is_counted_person(user) -> bool:
    from core import peran

    return user.is_active and peran.persona(user) not in {peran.OWNER, peran.ADMIN}


def compose(clinics, first: dt.date, *, only_user=None) -> list[StaffKpi]:
    """Hitung KPI per staf untuk bulan `first` di cabang `clinics`."""
    from checklists.models import ChecklistResponse, ChecklistSession, ResponseResult
    from core.models import ActionItemStatus, DayStatus, OperationalDay, TaskAssignment, TaskAssignmentMode
    from core.models import TaskAssignmentStatus, TaskEvent, TaskEventType
    from jadwal.models import WORKING_STATUSES, DutyAssignment, DutyRoster
    from jejak.models import Confidence, PresenceStamp

    clinics = list(clinics)
    today = local_today()
    last = month_end(first)
    upto = min(last, today)
    start_at, end_at = _aware(first, dt.time.min), _aware(last + dt.timedelta(days=1), dt.time.min)
    now = timezone.now()
    people: dict[int, StaffKpi] = {}

    def person(user) -> StaffKpi | None:
        if only_user is not None and user.pk != only_user.pk:
            return None
        if user.pk not in people:
            if not _is_counted_person(user):
                return None
            people[user.pk] = StaffKpi(user=user)
        return people[user.pk]

    if first > today:
        return []

    # Hari jaga
    for r in DutyRoster.objects.filter(date__range=(first, upto), clinic__in=clinics,
                                       status__in=WORKING_STATUSES).select_related("user", "clinic"):
        p = person(r.user)
        if p:
            p.duty_days += 1
            p.day(r.date, r.clinic).duty = r.get_status_display()

    # Hari yang dinilai untuk kelengkapan: sebelum hari ini, atau hari ini bila sudah ditutup.
    days = {
        (d.clinic_id, d.date): d
        for d in OperationalDay.objects.filter(clinic__in=clinics, date__range=(first, upto))
        if d.date < today or d.status == DayStatus.CLOSED
    }
    assigned = defaultdict(set)  # (clinic_id, date, portion_code) -> {user_id}
    assignments = list(
        DutyAssignment.objects.filter(clinic__in=clinics, date__range=(first, upto))
        .select_related("user", "portion", "clinic")
    )
    for a in assignments:
        assigned[(a.clinic_id, a.date, a.portion.code)].add(a.user_id)
    responses = defaultdict(list)  # (clinic_id, date, portion_code) -> [response]
    if days:
        for resp in (ChecklistResponse.objects.filter(run__operational_day__in=days.values())
                     .exclude(portion="").select_related("run__operational_day", "checked_by")):
            day = resp.run.operational_day
            responses[(day.clinic_id, day.date, resp.portion)].append(resp)
    for a in assignments:
        p = person(a.user)
        if not p:
            continue
        row = p.day(a.date, a.clinic)
        if a.portion.name not in row.portions:
            row.portions.append(a.portion.name)
        team = assigned[(a.clinic_id, a.date, a.portion.code)]
        for resp in responses.get((a.clinic_id, a.date, a.portion.code), []):
            row.items += 1
            p.items += 1
            if resp.result != ResponseResult.BELUM:
                row.filled += 1
                p.filled += 1
                if resp.checked_by_id and resp.checked_by_id not in team:
                    row.taken_over += 1
                    p.taken_over += 1
                    row.taken_over_by.add(str(resp.checked_by))

    # Pembukaan tepat waktu dan centang massal: butir yang ia isi sendiri.
    checked = (
        ChecklistResponse.objects.filter(
            run__operational_day__clinic__in=clinics, run__operational_day__date__range=(first, upto),
            checked_by__isnull=False, checked_at__isnull=False,
        ).exclude(result=ResponseResult.BELUM)
        .select_related("run__operational_day__clinic", "checked_by")
    )
    if only_user is not None:
        checked = checked.filter(checked_by=only_user)
    per_user_clinic = defaultdict(list)
    tolerance = {c.pk: int(ClinicConfig.get(c, OPEN_TOLERANCE_KEY, 15)) for c in clinics}
    for resp in checked:
        p = person(resp.checked_by)
        if not p:
            continue
        day = resp.run.operational_day
        per_user_clinic[(p.user.pk, day.clinic)].append(resp.checked_at)
        if resp.run.session != ChecklistSession.OPENING:
            continue
        row = p.day(day.date, day.clinic)
        deadline = _aware(day.date, day.clinic.open_time) + dt.timedelta(minutes=tolerance[day.clinic_id])
        p.opening_own += 1
        row.opening_own += 1
        row.opening_deadline = deadline
        if resp.checked_at > deadline:
            p.opening_late += 1
            row.opening_late += 1
        if row.latest_opening is None or resp.checked_at > row.latest_opening:
            row.latest_opening = resp.checked_at
    for (uid, clinic), times in per_user_clinic.items():
        p = people[uid]
        for burst in find_bursts(times, int(ClinicConfig.get(clinic, BULK_ITEMS_KEY, 5)),
                                 int(ClinicConfig.get(clinic, BULK_SECONDS_KEY, 60))):
            p.bursts += 1
            p.day(timezone.localtime(burst["start"]).date(), clinic).bursts.append(burst)

    # Jejak
    stamps = PresenceStamp.objects.filter(clinic__in=clinics, created_at__gte=start_at, created_at__lt=end_at)
    if only_user is not None:
        stamps = stamps.filter(user=only_user)
    for s in stamps.select_related("user", "clinic"):
        p = person(s.user)
        if not p:
            continue
        p.stamps_total += 1
        if s.confidence in (Confidence.KUAT, Confidence.SEDANG):
            p.stamps_good += 1
        p.day(timezone.localtime(s.created_at).date(), s.clinic).stamps[s.confidence] += 1

    # Task: target pada bulan ini yang sudah lewat.
    task_qs = (
        TaskAssignment.objects.filter(
            action_item__clinic__in=clinics, action_item__due_at__gte=start_at,
            action_item__due_at__lt=min(end_at, now),
        )
        .exclude(status=TaskAssignmentStatus.CANCELLED)
        .exclude(action_item__status=ActionItemStatus.BATAL)
        .filter(Q(action_item__assignment_mode=TaskAssignmentMode.INDIVIDUAL) | Q(claimed_by=F("assignee")))
        .select_related("action_item", "assignee")
        .prefetch_related("action_item__waiting_decisions")
        .annotate(first_submit=Min("events__created_at", filter=Q(events__event_type=TaskEventType.SUBMITTED)))
    )
    if only_user is not None:
        task_qs = task_qs.filter(assignee=only_user)
    for a in task_qs:
        item = a.action_item
        if item.on_hold:
            continue
        p = person(a.assignee)
        if not p:
            continue
        submitted = a.first_submit or a.submitted_at
        if submitted and submitted <= item.due_at:
            state = "tepat"
            p.tasks_on_time += 1
        elif submitted:
            state = "terlambat"
            p.tasks_late += 1
        else:
            state = "belum"
            p.tasks_pending += 1
        p.tasks_due += 1
        p.tasks.append({"item": item, "assignment": a, "submitted": submitted, "state": state})
    revisions = TaskEvent.objects.filter(
        event_type=TaskEventType.REVISION_REQUESTED, created_at__gte=start_at, created_at__lt=end_at,
        assignment__isnull=False, action_item__clinic__in=clinics,
    ).select_related("assignment__assignee")
    if only_user is not None:
        revisions = revisions.filter(assignment__assignee=only_user)
    for ev in revisions:
        p = person(ev.assignment.assignee)
        if p:
            p.revisions += 1

    # Bintang: assignment yang dikonfirmasi bulan ini dan sudah bernilai (termasuk bintang otomatis).
    rated = TaskAssignment.objects.filter(
        action_item__clinic__in=clinics, status=TaskAssignmentStatus.CONFIRMED, rating__isnull=False,
        confirmed_at__gte=start_at, confirmed_at__lt=end_at,
    ).select_related("assignee")
    if only_user is not None:
        rated = rated.filter(assignee=only_user)
    from accounts.models import Role, UserRole

    not_rated = set(UserRole.objects.filter(role__in=(Role.AOM, Role.OWNER)).values_list("user_id", flat=True))
    for a in rated:
        if a.assignee_id in not_rated:
            continue  # Direktur Operasional dan Owner tidak dinilai
        p = person(a.assignee)
        if p:
            p.rating_sum += a.rating
            p.rating_count += 1

    for p in people.values():
        p.tasks.sort(key=lambda t: t["item"].due_at)
    return sorted(people.values(), key=lambda p: (str(p.user).lower(), p.user.pk))


CSV_HEADER = [
    "Bulan", "Username", "Nama", "Hari jaga", "Butir porsi", "Butir terisi", "Kelengkapan (%)",
    "Diambil alih orang lain", "Butir pembukaan diisi sendiri", "Pembukaan tepat waktu",
    "Pembukaan tepat waktu (%)", "Jejak", "Jejak Kuat + Sedang", "Jejak Kuat + Sedang (%)",
    "Task jatuh tempo", "Task tepat target", "Task terlambat", "Task belum diajukan",
    "Task tepat target (%)", "Diminta revisi", "Tanda centang massal", "Bintang rata-rata", "Task dinilai",
]


def csv_row(first: dt.date, p: StaffKpi) -> list:
    def n(v):
        return "" if v is None else v

    return [
        f"{first:%Y-%m}", p.user.username, str(p.user), p.duty_days, p.items, p.filled, n(p.filled_pct),
        p.taken_over, p.opening_own, p.opening_on_time, n(p.opening_pct), p.stamps_total, p.stamps_good,
        n(p.stamps_pct), p.tasks_due, p.tasks_on_time, p.tasks_late, p.tasks_pending, n(p.tasks_pct),
        p.revisions, p.bursts, n(p.rating_avg), p.rating_count,
    ]
