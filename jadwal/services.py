"""Jadwal jaga dan pembagian tugas harian."""
from __future__ import annotations

import calendar
import datetime as dt
from collections import Counter, defaultdict

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from accounts.models import PicAssignment, User
from audit.models import AuditAction
from audit.services import log_event

from .models import (
    WORKING_STATUSES,
    AssignmentSource,
    DutyAssignment,
    DutyPortion,
    DutyRoster,
    DutyStatus,
)

# ---------------------------------------------------------------------------
# Izin
# ---------------------------------------------------------------------------


def can_edit_roster(user) -> bool:
    """Jadwal jaga diubah Direktur Operasional atau Admin."""
    from core.permissions import is_admin, is_aom, is_bootstrap_superuser

    return is_aom(user) or is_admin(user) or is_bootstrap_superuser(user)


def can_edit_duty(user, home_clinic) -> bool:
    """Mengubah jadwal jaga satu orang (masuk, off, cuti, perbantuan).

    Direktur Operasional dan Admin: semua orang. Koordinator Shift: orang yang cabang asalnya
    cabang koordinasinya, termasuk mengirimnya perbantuan ke cabang lain (keputusan 3 Okt 2026).
    """
    from accounts.models import Role
    from core.permissions import can_access_clinic

    if can_edit_roster(user):
        return True
    return bool(home_clinic) and can_access_clinic(user, home_clinic) and user.user_roles.filter(
        clinic=home_clinic, role=Role.SUPERVISOR
    ).exists()


def home_clinic_for(user, day: dt.date, default=None):
    """Cabang asal seseorang pada tanggal itu: baris jadwal hari itu, baris terdekat sebelumnya,
    baris terdekat sesudahnya, atau `default`."""
    rows = DutyRoster.objects.filter(user=user).select_related("home_clinic")
    row = (
        rows.filter(date=day).first()
        or rows.filter(date__lt=day).order_by("-date").first()
        or rows.filter(date__gt=day).order_by("date").first()
    )
    return row.home_clinic if row else default


def can_plan_duties(user) -> bool:
    """Menyusun ulang pembagian tugas satu bulan."""
    return can_edit_roster(user)


def can_swap_duties(user, clinic) -> bool:
    """Menukar pelaksana porsi: Direktur/Admin, atau Koordinator Shift cabang itu."""
    from accounts.models import Role
    from core.permissions import can_access_clinic

    if can_edit_roster(user):
        return True
    return can_access_clinic(user, clinic) and user.user_roles.filter(
        clinic=clinic, role=Role.SUPERVISOR
    ).exists()


# Fase 8: PIC mengganti pelaksana hanya untuk porsi fungsinya di cabangnya (keputusan no. 3).
# Koordinator Shift (peran SUPERVISOR) tetap untuk semua porsi cabangnya; giliran perawat, jadwal
# istirahat, dan jadwal jaga tetap bagian Koordinator Shift.
PIC_PORTION_GROUPS = {
    "CASHIER": {"KAS"},
    "PHARMACY": {"APOTEK"},
    "CLEANLINESS": {"KEBERSIHAN", "LIMBAH"},
}


def pic_functions_of(user, clinic, day: dt.date | None = None) -> set[str]:
    """Fungsi PIC yang aktif untuk pengguna di cabang itu pada tanggal itu."""
    from core.models import local_today

    day = day or local_today()
    return set(
        PicAssignment.objects.filter(user=user, clinic=clinic, active=True, starts_on__lte=day)
        .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=day))
        .values_list("function", flat=True)
    )


def can_swap_portion(user, portion: DutyPortion, day: dt.date | None = None) -> bool:
    """Mengganti pelaksana satu porsi: Koordinator Shift/Direktur/Admin semua porsi; PIC lain hanya
    porsi fungsinya (kelompok porsi, atau porsi yang didahulukan untuk fungsinya) di cabangnya."""
    from core.permissions import can_access_clinic

    if can_swap_duties(user, portion.clinic):
        return True
    if not can_access_clinic(user, portion.clinic):
        return False
    functions = pic_functions_of(user, portion.clinic, day)
    groups = set().union(*(PIC_PORTION_GROUPS.get(f, set()) for f in functions)) if functions else set()
    return portion.group in groups or bool(portion.pic_function and portion.pic_function in functions)


def can_view_duties(user, clinic) -> bool:
    from core.permissions import can_access_clinic

    return can_access_clinic(user, clinic)


# ---------------------------------------------------------------------------
# Jadwal jaga
# ---------------------------------------------------------------------------


def resolve_clinic(key: str):
    """Cabang dari kunci pendek (`jemur-andayani`, `citraland`).

    Kode cabang di produksi tidak selalu sama dengan kunci di berkas data
    (mis. Citraland dibuat manual dengan kode lain), jadi dicocokkan berurutan:
    kode persis, lalu kode atau nama yang memuat kunci. Harus tepat satu cabang.
    """
    from core.models import Clinic

    exact = Clinic.objects.filter(code=key).first()
    if exact:
        return exact
    word = key.split("-")[0]
    found = list(Clinic.objects.filter(Q(code__icontains=word) | Q(name__icontains=word)))
    if len(found) == 1:
        return found[0]
    if not found:
        raise ValidationError(f"Cabang belum ada: {key}")
    raise ValidationError(f"Kunci cabang '{key}' cocok dengan lebih dari satu cabang: "
                          + ", ".join(c.code for c in found))


def duty_of(user, day: dt.date) -> DutyRoster | None:
    return DutyRoster.objects.filter(user=user, date=day).select_related("clinic").first()


def working_rows(clinic, day: dt.date):
    return (
        DutyRoster.objects.filter(clinic=clinic, date=day, status__in=WORKING_STATUSES)
        .select_related("user", "home_clinic")
        .order_by("user__display_name", "user__username")
    )


def staff_on_duty(clinic, day: dt.date) -> list[User]:
    return [row.user for row in working_rows(clinic, day) if row.user.is_active]


def has_roster(clinic, day: dt.date) -> bool:
    """Apakah jadwal jaga cabang ini sudah diisi untuk tanggal itu."""
    return DutyRoster.objects.filter(Q(clinic=clinic) | Q(home_clinic=clinic), date=day).exists()


def month_days(year: int, month: int) -> list[dt.date]:
    return [dt.date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)]


def roster_grid(clinic, year: int, month: int) -> dict:
    """Baris per orang yang pernah tercatat di cabang ini pada bulan itu."""
    days = month_days(year, month)
    rows = (
        DutyRoster.objects.filter(date__year=year, date__month=month)
        .filter(Q(home_clinic=clinic) | Q(clinic=clinic))
        .select_related("user", "clinic", "home_clinic")
    )
    people: dict[int, dict] = {}
    for r in rows:
        entry = people.setdefault(
            r.user_id, {"user": r.user, "home": r.home_clinic_id == clinic.pk, "cells": {}}
        )
        if r.home_clinic_id == clinic.pk:
            entry["home"] = True
        if r.status == DutyStatus.MASUK and r.clinic_id == clinic.pk:
            code, label = "M", "Masuk"
        elif r.status == DutyStatus.PERBANTUAN and r.clinic_id == clinic.pk:
            code, label = "B", f"Perbantuan dari {r.home_clinic.name}"
        elif r.status == DutyStatus.PERBANTUAN:
            code, label = "P", f"Ke {r.clinic.name}"
        elif r.status == DutyStatus.CUTI:
            code, label = "C", "Cuti"
        else:
            code, label = "O", "Off"
        entry["cells"][r.date] = {"code": code, "label": label}
    ordered = sorted(people.values(), key=lambda e: (not e["home"], str(e["user"]).lower()))
    for e in ordered:
        e["row"] = [{**e["cells"].get(d, {"code": "", "label": "Belum diisi"}), "date": d} for d in days]
        e["working"] = sum(1 for c in e["row"] if c["code"] in ("M", "B"))
    totals = [sum(1 for e in ordered if e["row"][i]["code"] in ("M", "B")) for i in range(len(days))]
    return {"days": days, "people": ordered, "totals": totals}


@transaction.atomic
def set_duty(*, user, day: dt.date, status: str, home_clinic, clinic=None, actor, note: str = "") -> DutyRoster:
    """Ubah jadwal satu orang pada satu tanggal.

    Untuk hari ini dan sesudahnya, porsi tugas dan roster giliran perawat ikut menyesuaikan:
    porsi orang yang tidak lagi bertugas di sebuah cabang dilepas lalu diisi orang lain yang
    bertugas (porsi yang sudah dipegang orang lain tidak diacak ulang). Hasilnya ada di
    ``row.sync`` untuk pesan ke pengguna.
    """
    if not can_edit_duty(actor, home_clinic):
        raise PermissionDenied(
            "Jadwal jaga diubah Direktur Operasional, Admin, atau Koordinator Shift cabang asal orang itu."
        )
    if status not in DutyStatus.values:
        raise ValidationError("Status jadwal tidak dikenali.")
    if status == DutyStatus.MASUK:
        clinic = home_clinic
    elif status in (DutyStatus.OFF, DutyStatus.CUTI):
        clinic = None
    row = DutyRoster.objects.filter(user=user, date=day).first()
    before = None
    if row is None:
        row = DutyRoster(user=user, date=day)
    else:
        before = {"status": row.status, "clinic": row.clinic_id, "home_clinic": row.home_clinic_id}
    row.home_clinic = home_clinic
    row.clinic = clinic
    row.status = status
    row.note = (note or "").strip()
    row.updated_by = actor
    row.full_clean()
    row.save()
    log_event(
        action=AuditAction.UPDATE if before else AuditAction.CREATE,
        entity_type="dutyroster",
        entity_id=row.pk,
        entity_label=str(row),
        actor=actor,
        before=before,
        after={"status": row.status, "clinic": row.clinic_id, "home_clinic": row.home_clinic_id},
        reason=row.note,
    )
    row.sync = _after_duty_change(row, before["clinic"] if before else None, actor=actor)
    return row


def _after_duty_change(row: DutyRoster, before_clinic_id, *, actor) -> dict:
    """Porsi tugas dan roster giliran perawat mengikuti perubahan jadwal (hari ini ke depan)."""
    from core.models import Clinic, OperationalDay, local_today

    out = {"released": [], "filled": []}
    if row.date < local_today():
        return out
    now_at = row.clinic_id if row.status in WORKING_STATUSES else None
    affected = [c for c in {before_clinic_id, now_at} if c]
    for clinic in Clinic.objects.filter(pk__in=affected):
        if clinic.pk != now_at:
            mine = DutyAssignment.objects.filter(user=row.user, date=row.date, clinic=clinic).select_related("portion")
            out["released"] += [a.portion.name for a in mine]
            mine.delete()
        if DutyPortion.objects.filter(clinic=clinic, active=True).exists():
            created = _plan_day(clinic, row.date, _month_tally(clinic, row.date), actor=actor, fill_only=True)
            out["filled"] += [f"{a.portion.name}: {a.user}" for a in created]
        day = OperationalDay.objects.filter(clinic=clinic, date=row.date).first()
        if day is not None:
            from nurses.services import sync_roster_with_duty

            sync_roster_with_duty(day, actor=actor)
    if out["released"] or out["filled"]:
        log_event(
            action=AuditAction.UPDATE,
            entity_type="dutyassignment",
            entity_id=f"roster:{row.pk}",
            entity_label=f"Porsi menyesuaikan jadwal {row.user} {row.date:%d/%m}",
            actor=actor,
            after=out,
        )
    return out


@transaction.atomic
def import_month(data: dict, *, actor=None) -> dict:
    """Impor jadwal satu bulan dari berkas `jadwal/jadwal_bulanan/jadwal-YYYY-MM.json`.

    Tiap cabang berisi satu string per orang; satu karakter per tanggal:
    `.` bertugas di cabang tabel itu, `X` off, `P` perbantuan ke cabang lain,
    `C` cuti. Orang yang muncul di dua tabel memakai cabang asal dari `home`.
    """
    year, month = (int(p) for p in data["month"].split("-"))
    days = month_days(year, month)
    clinics = {key: resolve_clinic(key) for key in data["clinics"]}
    appearances: dict[str, list[str]] = defaultdict(list)
    for code, people in data["clinics"].items():
        for username in people:
            appearances[username].append(code)
    users = {u.username: u for u in User.objects.filter(username__in=list(appearances))}
    missing_users = sorted(set(appearances) - set(users))
    if missing_users:
        raise ValidationError(f"Akun belum ada: {', '.join(missing_users)}")

    warnings: list[str] = []
    written = 0
    for username, codes in appearances.items():
        home_code = data.get("home", {}).get(username) or codes[0]
        if len(codes) > 1 and username not in data.get("home", {}):
            raise ValidationError(f"{username} ada di dua cabang; tentukan cabang asalnya di 'home'.")
        home = clinics[home_code]
        others = [c for c in codes if c != home_code]
        home_row = data["clinics"][home_code][username]
        if len(home_row) != len(days):
            raise ValidationError(f"{username}: {len(home_row)} kolom, bulan ini {len(days)} hari.")
        for i, day in enumerate(days):
            ch = home_row[i].upper()
            clinic = None
            if ch == ".":
                status, clinic = DutyStatus.MASUK, home
            elif ch == "X":
                status = DutyStatus.OFF
            elif ch == "C":
                status = DutyStatus.CUTI
            elif ch == "P":
                if len(others) != 1:
                    raise ValidationError(f"{username} {day}: perbantuan tanpa cabang tujuan yang jelas.")
                status, clinic = DutyStatus.PERBANTUAN, clinics[others[0]]
            else:
                raise ValidationError(f"{username} {day}: kode '{ch}' tidak dikenali.")
            for other in others:
                och = data["clinics"][other][username][i].upper()
                expected = {"MASUK": "P", "PERBANTUAN": ".", "OFF": "X", "CUTI": "X"}[status]
                if och != expected and not (status == DutyStatus.CUTI and och == "C"):
                    warnings.append(f"{username} {day:%d/%m}: tabel {home_code} '{ch}', tabel {other} '{och}'")
            DutyRoster.objects.update_or_create(
                user=users[username],
                date=day,
                defaults={"home_clinic": home, "clinic": clinic, "status": status, "updated_by": actor},
            )
            written += 1
    log_event(
        action=AuditAction.MIGRATION_IMPORT,
        entity_type="dutyroster",
        entity_id=data["month"],
        entity_label=f"Jadwal jaga {data['month']}",
        actor=actor,
        after={"rows": written, "warnings": warnings},
    )
    return {"rows": written, "warnings": warnings, "people": len(appearances)}


# ---------------------------------------------------------------------------
# Pembagian tugas
# ---------------------------------------------------------------------------


# Porsi yang tidak boleh jatuh ke orang tanpa perannya.
STRICT_GROUPS = {"APOTEK", "KAS"}


def pic_holders(clinic, function: str, day: dt.date) -> set[int]:
    return set(
        PicAssignment.objects.filter(clinic=clinic, function=function, active=True, starts_on__lte=day)
        .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=day))
        .values_list("user_id", flat=True)
    )


def _name(u) -> str:
    return (u.display_name or u.username).lower()


class _Tally:
    """Hitungan beban sepanjang bulan, dipakai untuk menggilir porsi."""

    def __init__(self):
        self.total = Counter()
        self.group = Counter()
        self.portion = Counter()

    def add(self, user_id: int, portion: DutyPortion):
        self.total[user_id] += 1
        self.group[(user_id, portion.group)] += 1
        self.portion[(user_id, portion.code)] += 1


def _month_tally(clinic, day: dt.date) -> _Tally:
    """Beban dari tanggal 1 sampai sehari sebelum `day` (semua cabang)."""
    tally = _Tally()
    rows = DutyAssignment.objects.filter(
        date__year=day.year, date__month=day.month, date__lt=day
    ).select_related("portion")
    for a in rows:
        tally.add(a.user_id, a.portion)
    return tally


def _plan_day(clinic, day: dt.date, tally: _Tally, *, actor=None, fill_only: bool = False) -> list[DutyAssignment]:
    """Susun porsi satu hari. ``fill_only``: pertahankan semua porsi yang sudah terisi dan hanya
    isi yang kosong (dipakai sesudah jadwal jaga satu orang berubah)."""
    staff = staff_on_duty(clinic, day)
    roles = {u.pk: u.role_codes() for u in staff}
    kept = DutyAssignment.objects.filter(clinic=clinic, date=day)
    if not fill_only:
        kept.filter(source=AssignmentSource.OTOMATIS).delete()
        kept = kept.filter(source=AssignmentSource.MANUAL)
    manual = list(kept.select_related("portion"))
    today = Counter()
    for a in manual:
        today[a.user_id] += 1
        tally.add(a.user_id, a.portion)
    created: list[DutyAssignment] = []
    # Bila pemegang PIC libur, semua porsi fungsi itu hari itu jatuh ke satu
    # delegasi yang sama (mis. opening dan closing Koordinator Shift).
    delegates: dict[str, list[User]] = {}
    for portion in DutyPortion.objects.filter(clinic=clinic, active=True).order_by("sort_order", "code"):
        if not portion.runs_on(day):
            continue
        taken = {a.user_id for a in manual if a.portion_id == portion.pk}
        need = portion.people - len(taken)
        if need <= 0:
            continue
        chosen: list[User] = []
        holders_on_duty: list[User] = []
        if portion.pic_function:
            holders = pic_holders(clinic, portion.pic_function, day)
            holders_on_duty = sorted([u for u in staff if u.pk in holders and u.pk not in taken], key=_name)
            chosen = holders_on_duty[:need]
            if not chosen:
                wanted_roles = set(portion.eligible_roles or [])
                chosen = [
                    u for u in delegates.get(portion.pic_function, [])
                    if u.pk not in taken and (not wanted_roles or roles[u.pk] & wanted_roles)
                ][:need]
        if len(chosen) < need:
            wanted = set(portion.eligible_roles or [])
            used = taken | {u.pk for u in chosen}
            candidates = [
                u for u in staff if u.pk not in used and (not wanted or roles[u.pk] & wanted)
            ]
            if not candidates and portion.group not in STRICT_GROUPS:
                # Tidak ada pemegang peran yang bertugas: tetap ada yang memegang,
                # kecuali porsi apotek dan kas yang memang dibatasi perannya.
                candidates = [u for u in staff if u.pk not in used]
            candidates.sort(
                key=lambda u: (
                    today[u.pk],
                    tally.portion[(u.pk, portion.code)],
                    tally.group[(u.pk, portion.group)],
                    tally.total[u.pk],
                    _name(u),
                )
            )
            chosen += candidates[: need - len(chosen)]
            if portion.pic_function and not holders_on_duty:
                delegates.setdefault(portion.pic_function, list(chosen))
        for u in chosen:
            created.append(
                DutyAssignment.objects.create(
                    portion=portion, clinic=clinic, date=day, user=u,
                    source=AssignmentSource.OTOMATIS, updated_by=actor,
                )
            )
            today[u.pk] += 1
            tally.add(u.pk, portion)
    return created


@transaction.atomic
def plan_range(clinic, start: dt.date, end: dt.date, *, actor=None) -> int:
    """Susun ulang porsi otomatis dari `start` sampai `end`; porsi manual dipertahankan."""
    if actor is not None and not can_plan_duties(actor):
        raise PermissionDenied("Penyusunan pembagian tugas hanya oleh Direktur Operasional atau Admin.")
    count = 0
    day = start
    tally = _month_tally(clinic, day)
    while day <= end:
        if day.day == 1 and day != start:
            tally = _Tally()
        count += len(_plan_day(clinic, day, tally, actor=actor))
        day += dt.timedelta(days=1)
    log_event(
        action=AuditAction.UPDATE,
        entity_type="dutyassignment",
        entity_id=f"{clinic.code}:{start}:{end}",
        entity_label=f"Susun pembagian tugas {clinic.name} {start}–{end}",
        actor=actor,
        after={"created": count},
    )
    return count


def plan_month(clinic, year: int, month: int, *, actor=None) -> int:
    days = month_days(year, month)
    return plan_range(clinic, days[0], days[-1], actor=actor)


@transaction.atomic
def set_portion_people(portion: DutyPortion, day: dt.date, users: list[User], *, actor, note: str = ""):
    """Ganti pelaksana satu porsi pada satu tanggal (menjadi manual)."""
    if not can_swap_portion(actor, portion, day):
        raise PermissionDenied("Hanya Koordinator Shift cabang ini, PIC fungsi porsi ini, Direktur Operasional, "
                               "atau Admin.")
    on_duty = {u.pk for u in staff_on_duty(portion.clinic, day)}
    for u in users:
        if u.pk not in on_duty:
            raise ValidationError(f"{u} tidak bertugas di {portion.clinic.name} pada {day:%d/%m}.")
    wanted = set(portion.eligible_roles or [])
    if wanted:
        for u in users:
            if not (u.role_codes() & wanted) and u.pk not in pic_holders(portion.clinic, portion.pic_function, day):
                raise ValidationError(f"{u} tidak memegang peran yang dibutuhkan porsi {portion.name}.")
    before = list(
        DutyAssignment.objects.filter(portion=portion, date=day).values_list("user__username", flat=True)
    )
    DutyAssignment.objects.filter(portion=portion, date=day).delete()
    for u in users:
        DutyAssignment.objects.create(
            portion=portion, clinic=portion.clinic, date=day, user=u,
            source=AssignmentSource.MANUAL, updated_by=actor, note=(note or "").strip(),
        )
    log_event(
        action=AuditAction.UPDATE,
        entity_type="dutyassignment",
        entity_id=f"{portion.pk}:{day}",
        entity_label=f"{portion.name} {day:%d/%m}",
        actor=actor,
        before={"users": before},
        after={"users": [u.username for u in users]},
        reason=note,
    )


def assignments_by_portion(clinic, day: dt.date) -> dict[str, list[DutyAssignment]]:
    out: dict[str, list[DutyAssignment]] = defaultdict(list)
    for a in DutyAssignment.objects.filter(clinic=clinic, date=day).select_related("user", "portion"):
        out[a.portion.code].append(a)
    return dict(out)


def my_assignments(user, day: dt.date):
    return (
        DutyAssignment.objects.filter(user=user, date=day, portion__active=True)
        .select_related("portion", "clinic")
        .order_by("portion__sort_order")
    )


def is_assigned(user, clinic, day: dt.date, portion_code: str) -> bool:
    if not portion_code:
        return False
    return DutyAssignment.objects.filter(
        user=user, clinic=clinic, date=day, portion__code=portion_code
    ).exists()


def month_plan(clinic, year: int, month: int) -> dict:
    """Tabel pratinjau: baris tanggal, kolom kelompok; ringkasan per orang."""
    from .models import DutyGroup

    days = month_days(year, month)
    portions = list(DutyPortion.objects.filter(clinic=clinic, active=True).order_by("sort_order"))
    rows = DutyAssignment.objects.filter(clinic=clinic, date__year=year, date__month=month).select_related(
        "user", "portion"
    )
    cell: dict[tuple, list] = defaultdict(list)
    per_person: dict[int, dict] = {}
    for a in rows:
        cell[(a.date, a.portion.group)].append(a)
        p = per_person.setdefault(a.user_id, {"user": a.user, "total": 0, "groups": Counter()})
        p["total"] += 1
        p["groups"][a.portion.group] += 1
    groups = [g for g in DutyGroup if any(p.group == g for p in portions)]
    table = []
    for d in days:
        table.append(
            {
                "date": d,
                "staff": len(staff_on_duty(clinic, d)),
                "cells": [
                    sorted(cell.get((d, g), []), key=lambda a: (a.portion.sort_order, _name(a.user)))
                    for g in groups
                ],
            }
        )
    people = sorted(per_person.values(), key=lambda p: (-p["total"], _name(p["user"])))
    for p in people:
        p["by_group"] = [p["groups"].get(g, 0) for g in groups]
        working = DutyRoster.objects.filter(
            user=p["user"], clinic=clinic, date__year=year, date__month=month, status__in=WORKING_STATUSES
        ).count()
        p["days"] = working
        p["per_day"] = round(p["total"] / working, 1) if working else 0
    return {"days": days, "groups": [(g.value, g.label) for g in groups], "table": table, "people": people}


def cashier_assignments(user, day: dt.date | None = None):
    """Porsi kelompok Kas (mis. "Kasir hari ini") yang ditugaskan kepada pengguna pada tanggal itu.

    Tanpa tanggal: tanggal hari operasional yang berjalan di cabang porsi itu, sehingga kasir yang
    menutup kas lewat tengah malam (hari kemarin belum ditutup) tetap dianggap kasir.
    """
    from core.models import local_today, operational_date

    qs = DutyAssignment.objects.filter(user=user, portion__group="KAS", portion__active=True).select_related(
        "portion", "clinic")
    if day is not None:
        return qs.filter(date=day)
    today = local_today()
    rows = list(qs.filter(date__in=[today, today - dt.timedelta(days=1)]))
    keep = [a.pk for a in rows if a.date == operational_date(a.clinic)]
    return qs.filter(pk__in=keep)


def is_cashier_today(user, day: dt.date | None = None) -> bool:
    """Staf hanya membuka Kas pada hari ia ditugaskan sebagai kasir (keputusan no. 5, fase 7)."""
    if not getattr(user, "is_authenticated", False):
        return False
    return cashier_assignments(user, day).exists()
