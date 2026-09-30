"""Definisi peran standar seluruh akun yang dikenal, dan reset ke definisi itu.

Dipakai tombol **Reset peran ke default** di halaman Admin dan perintah
`seed_staf_cabang`. Setelah kode disinkronkan ke mini PC, satu tombol
mengembalikan peran, cabang, dan fungsi PIC ke definisi di sini, tanpa terminal.

Yang dilakukan (lihat `docs/KEBUTUHAN_REDEFINISI_PERAN.md`):
- akun standar yang belum ada dibuat dengan password awal dan wajib ganti password;
- ejaan username lama diganti (`heny` → `heni`, `regita` → `regitta`, dst.);
- peran yang kurang ditambah, peran di luar definisi dicabut;
- fungsi PIC yang kurang ditambah, PIC aktif di luar definisi diakhiri (tidak dihapus).

Yang tidak dilakukan: mengubah password akun yang sudah ada, menyentuh data (task,
catatan, checklist, audit), atau menyentuh akun di luar daftar (mis. `AOM_HS`).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.db import transaction

from accounts.models import PicAssignment, Role, User, UserRole
from audit.models import AuditAction
from audit.services import log_event
from jadwal.staff import JMR, RENAMES, STAFF

DEFAULT_PASSWORD = "klinik123"

# username, nama tampilan, jabatan, {cabang: [peran]}, [(cabang, fungsi PIC, mulai)]
# Owner dan Direktur Utama: satu peran dan satu tampilan (OWNER); cabang hanya tempat
# peran disimpan, aksesnya lintas cabang.
MANAGEMENT = [
    ("yohanes", "dr. Yohanes Widjaja, Sp.DVE", "Owner", {JMR: [Role.OWNER]}, []),
    ("jean", "Jean", "Direktur Utama", {JMR: [Role.OWNER]}, []),
    ("hansen1", "dr. Hansen Sudarma", "Direktur Operasional", {JMR: [Role.AOM]}, []),
    ("superadmin", "superadmin", "Admin sistem", {JMR: [Role.ADMIN]}, []),
]


def standard_accounts() -> list[tuple]:
    """Seluruh akun standar: manajemen lalu staf. Flag terakhir: perbarui nama tampilan."""
    return [(*row, False) for row in MANAGEMENT] + [(*row, True) for row in STAFF]


@dataclass
class AccountPlan:
    username: str
    display: str
    create: bool = False
    rename_from: str = ""
    profile: list[str] = field(default_factory=list)
    add_roles: list[tuple] = field(default_factory=list)  # (clinic, role)
    remove_roles: list[UserRole] = field(default_factory=list)
    add_pics: list[tuple] = field(default_factory=list)  # (clinic, function, starts_on)
    end_pics: list[PicAssignment] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.create or self.rename_from or self.profile or self.add_roles or self.remove_roles
                    or self.add_pics or self.end_pics)


def _clinics() -> dict:
    from jadwal.services import resolve_clinic

    keys = sorted({code for row in standard_accounts() for code in row[3]})
    return {key: resolve_clinic(key) for key in keys}


def build_plan(*, remove_extras: bool = True) -> tuple[list[AccountPlan], dict]:
    """Rencana perubahan tanpa menulis apa pun."""
    clinics = _clinics()
    plans: list[AccountPlan] = []
    taken = set(User.objects.values_list("username", flat=True))
    for username, display, title, roles, pics, sync_profile in standard_accounts():
        plan = AccountPlan(username=username, display=display)
        user = User.objects.filter(username=username).first()
        if user is None:
            old = next((o for o, n in RENAMES.items() if n == username and o in taken), None)
            if old:
                user = User.objects.get(username=old)
                plan.rename_from = old
        if user is None:
            plan.create = True
            plan.add_roles = [(clinics[c], r) for c, rs in roles.items() for r in rs]
            plan.add_pics = [(clinics[c], f, s) for c, f, s in pics]
            plans.append(plan)
            continue
        if sync_profile:
            if user.display_name != display:
                plan.profile.append(f"nama tampilan: {user.display_name or '—'} → {display}")
            if user.job_title != title:
                plan.profile.append(f"jabatan: {user.job_title or '—'} → {title}")
        wanted = {(clinics[c].pk, r) for c, rs in roles.items() for r in rs}
        have = {(ur.clinic_id, ur.role): ur for ur in user.user_roles.select_related("clinic")}
        plan.add_roles = [(clinics[c], r) for c, rs in roles.items() for r in rs if (clinics[c].pk, r) not in have]
        if remove_extras:
            plan.remove_roles = [ur for key, ur in have.items() if key not in wanted]
        wanted_pics = {(clinics[c].pk, f) for c, f, _ in pics}
        active = list(user.pic_assignments.filter(active=True).select_related("clinic"))
        have_pics = {(p.clinic_id, p.function) for p in active}
        plan.add_pics = [(clinics[c], f, s) for c, f, s in pics if (clinics[c].pk, f) not in have_pics]
        if remove_extras:
            plan.end_pics = [p for p in active if (p.clinic_id, p.function) not in wanted_pics]
        plans.append(plan)
    return plans, clinics


def describe(plan: AccountPlan) -> list[str]:
    lines = []
    if plan.create:
        lines.append(f"akun baru, password awal {DEFAULT_PASSWORD}")
    if plan.rename_from:
        lines.append(f"username {plan.rename_from} → {plan.username}")
    lines += plan.profile
    lines += [f"+ peran {Role(r).label} @ {c.name}" for c, r in plan.add_roles]
    lines += [f"− peran {ur.get_role_display()} @ {ur.clinic.name}" for ur in plan.remove_roles]
    lines += [f"+ PIC {dict(PicAssignment._meta.get_field('function').choices)[f]} @ {c.name}"
              for c, f, _ in plan.add_pics]
    lines += [f"− PIC {p.get_function_display()} @ {p.clinic.name} (diakhiri)" for p in plan.end_pics]
    return lines


@transaction.atomic
def apply_plan(plans: list[AccountPlan], *, actor=None, password: str = DEFAULT_PASSWORD) -> int:
    """Terapkan rencana dari `build_plan`. Mengembalikan jumlah akun yang berubah."""
    standard = {row[0]: row for row in standard_accounts()}
    today = dt.date.today()
    changed = 0
    for plan in plans:
        if not plan.changed:
            continue
        changed += 1
        _, display, title, _, _, _ = standard[plan.username]
        if plan.create:
            user = User(username=plan.username, display_name=display, job_title=title, must_change_password=True)
            user.set_password(password)
            user.save()
            log_event(action=AuditAction.CREATE, entity_type="user", entity_id=user.pk, entity_label=user.username,
                      actor=actor, after={"display_name": display}, reason="Reset peran ke default")
        else:
            user = User.objects.get(username=plan.rename_from or plan.username)
            if plan.rename_from:
                user.username = plan.username
                user.save(update_fields=["username"])
                log_event(action=AuditAction.UPDATE, entity_type="user", entity_id=user.pk, entity_label=user.username,
                          actor=actor, before={"username": plan.rename_from}, after={"username": plan.username},
                          reason="Reset peran ke default")
            if plan.profile:
                user.display_name, user.job_title = display, title
                user.save(update_fields=["display_name", "job_title"])
        for clinic, role in plan.add_roles:
            UserRole.objects.get_or_create(user=user, clinic=clinic, role=role, defaults={"granted_by": actor})
            log_event(action=AuditAction.PERMISSION_CHANGED, entity_type="userrole", entity_id=user.pk,
                      entity_label=f"{user.username} +{role} {clinic.code}", actor=actor,
                      after={"role": role, "clinic": clinic.code}, reason="Reset peran ke default")
        for ur in plan.remove_roles:
            log_event(action=AuditAction.PERMISSION_CHANGED, entity_type="userrole", entity_id=user.pk,
                      entity_label=f"{user.username} -{ur.role} {ur.clinic.code}", actor=actor,
                      before={"role": ur.role, "clinic": ur.clinic.code}, reason="Reset peran ke default")
            ur.delete()
        for clinic, function, starts in plan.add_pics:
            pic, created = PicAssignment.objects.get_or_create(
                user=user, clinic=clinic, function=function, starts_on=starts,
                defaults={"granted_by": actor},
            )
            if not created and not pic.active:  # pernah diakhiri, diaktifkan lagi
                pic.active, pic.ends_on = True, None
                pic.save(update_fields=["active", "ends_on"])
            log_event(action=AuditAction.PERMISSION_CHANGED, entity_type="picassignment", entity_id=user.pk,
                      entity_label=f"{user.username} +{function} {clinic.code}", actor=actor,
                      after={"function": function, "clinic": clinic.code}, reason="Reset peran ke default")
        for pic in plan.end_pics:
            pic.active = False
            pic.ends_on = today
            pic.save(update_fields=["active", "ends_on"])
            log_event(action=AuditAction.PERMISSION_CHANGED, entity_type="picassignment", entity_id=user.pk,
                      entity_label=f"{user.username} -{pic.function} {pic.clinic.code}", actor=actor,
                      before={"function": pic.function, "clinic": pic.clinic.code}, reason="Reset peran ke default")
        if hasattr(user, "_role_cache"):
            del user._role_cache
    return changed
