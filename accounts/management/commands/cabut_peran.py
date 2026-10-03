"""Cabut peran satu akun di satu cabang, tercatat di audit (PERMISSION_CHANGED).

    python manage.py cabut_peran regita jemur --semua --catatan "Hanya Citraland (Memo 002)"
    python manage.py cabut_peran elvira jemur SUPERVISOR --catatan "Apoteker dan PJ Kebersihan"
    python manage.py cabut_peran regita jemur --semua --dry-run

Cabang ditulis sebagai kunci (`jemur`, `citraland`) atau kode/nama cabang. Data lain (jadwal,
tally, task, fungsi PIC) tidak disentuh. Sama dengan menghapus centang peran di Admin ▸ Pengguna.
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Role, User, UserRole
from audit.models import AuditAction
from audit.services import log_event


class Command(BaseCommand):
    help = "Cabut peran satu akun di satu cabang."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("cabang")
        parser.add_argument("peran", nargs="*", help="Kode peran, mis. SUPERVISOR ONLINE")
        parser.add_argument("--semua", action="store_true", help="Cabut semua peran di cabang itu")
        parser.add_argument("--catatan", default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, username, cabang, peran, semua, catatan, dry_run, **opts):
        from core.models import Clinic
        from core.services import clinic_key

        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            raise CommandError(f"Akun {username} tidak ditemukan.")
        key = cabang.lower()
        clinics = [c for c in Clinic.objects.all()
                   if key in (c.code.lower(), clinic_key(c)) or clinic_key(c).startswith(key)
                   or key in c.name.lower()]
        if len(clinics) != 1:
            raise CommandError(f"Cabang '{cabang}' cocok dengan {len(clinics)} cabang.")
        clinic = clinics[0]
        unknown = set(peran) - set(Role.values)
        if unknown:
            raise CommandError(f"Peran tidak dikenal: {', '.join(sorted(unknown))}")
        if not semua and not peran:
            raise CommandError("Sebutkan peran yang dicabut, atau pakai --semua.")
        rows = UserRole.objects.filter(user=user, clinic=clinic)
        before = sorted(rows.values_list("role", flat=True))
        target = rows if semua else rows.filter(role__in=peran)
        removing = sorted(target.values_list("role", flat=True))
        after = sorted(set(before) - set(removing))
        prefix = "[dry-run] " if dry_run else ""
        if not removing:
            self.stdout.write(f"{prefix}{user.username} @ {clinic.name}: tidak ada yang dicabut ({', '.join(before) or '-'}).")
            return
        if not dry_run:
            target.delete()
            log_event(action=AuditAction.PERMISSION_CHANGED, entity_type="user", entity_id=user.pk,
                      entity_label=str(user), before={"clinic": clinic.code, "roles": before},
                      after={"clinic": clinic.code, "roles": after},
                      reason=catatan or "dicabut lewat cabut_peran")
        self.stdout.write(f"{prefix}{user.username} @ {clinic.name}: dicabut {', '.join(removing)}; "
                          f"tersisa {', '.join(after) or '-'}.")
