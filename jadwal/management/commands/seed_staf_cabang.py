"""Buat atau lengkapi akun staf dua cabang beserta peran dan PIC-nya (idempoten).

    manage.py seed_staf_cabang --dry-run
    manage.py seed_staf_cabang --password 'SementaraRahasia!'

- Akun yang sudah ada tidak diubah password-nya.
- Akun baru wajib diberi `--password`; pemiliknya wajib mengganti saat login pertama.
- Peran yang kurang ditambahkan. Peran lain yang sudah dimiliki tidak dicabut,
  kecuali `--prune`: peran staf ini di cabang yang tidak lagi menjadi tempatnya
  (mis. Naya di Jemur) dicabut dan dicatat di audit.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import PicAssignment, User, UserRole
from audit.models import AuditAction
from audit.services import log_event
from core.models import Clinic
from jadwal.staff import RENAMES, STAFF


class Command(BaseCommand):
    help = "Akun staf Jemur dan Citraland, peran, dan PIC sesuai memo penunjukan."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="", help="Password awal untuk akun yang baru dibuat.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--prune", action="store_true", help="Cabut peran di cabang yang bukan tempatnya lagi.")

    def handle(self, *args, password="", dry_run=False, prune=False, **opts):
        clinics = {c.code: c for c in Clinic.objects.all()}
        needed = {code for _, _, _, roles, _ in STAFF for code in roles}
        missing = needed - set(clinics)
        if missing:
            raise CommandError(f"Cabang belum ada: {', '.join(sorted(missing))}")
        with transaction.atomic():
            for old, new in RENAMES.items():
                user = User.objects.filter(username=old).first()
                if user and not User.objects.filter(username=new).exists():
                    self.stdout.write(f"~ ganti username {old} -> {new}")
                    user.username = new
                    user.save(update_fields=["username"])
            for username, display, title, roles, pics in STAFF:
                user = User.objects.filter(username=username).first()
                if user is None:
                    if not password and not dry_run:
                        raise CommandError(f"Akun {username} belum ada: berikan --password untuk akun baru.")
                    self.stdout.write(f"+ akun {username} ({display})")
                    user = User(username=username, display_name=display, job_title=title, must_change_password=True)
                    user.set_password(password or "belum-diisi")
                    user.save()
                    log_event(action=AuditAction.CREATE, entity_type="user", entity_id=user.pk,
                              entity_label=username, actor=None, after={"display_name": display})
                else:
                    changed = []
                    if user.display_name != display:
                        user.display_name = display
                        changed.append("display_name")
                    if user.job_title != title:
                        user.job_title = title
                        changed.append("job_title")
                    if changed:
                        user.save(update_fields=changed)
                        self.stdout.write(f"~ {username}: {', '.join(changed)}")
                for code, wanted in roles.items():
                    for role in wanted:
                        _, created = UserRole.objects.get_or_create(user=user, clinic=clinics[code], role=role)
                        if created:
                            self.stdout.write(f"  + {username} {role} @ {code}")
                            log_event(action=AuditAction.PERMISSION_CHANGED, entity_type="userrole",
                                      entity_id=user.pk, entity_label=f"{username} {role} {code}", actor=None,
                                      after={"role": role, "clinic": code})
                if prune:
                    for ur in UserRole.objects.filter(user=user).exclude(clinic__code__in=list(roles)):
                        self.stdout.write(f"  - {username} {ur.role} @ {ur.clinic.code}")
                        log_event(action=AuditAction.PERMISSION_CHANGED, entity_type="userrole",
                                  entity_id=user.pk, entity_label=f"{username} {ur.role} {ur.clinic.code}",
                                  actor=None, before={"role": ur.role, "clinic": ur.clinic.code},
                                  reason="Bukan cabang tempatnya lagi")
                        ur.delete()
                for code, function, starts in pics:
                    if not PicAssignment.objects.filter(
                        user=user, clinic=clinics[code], function=function, active=True
                    ).exists():
                        PicAssignment.objects.create(user=user, clinic=clinics[code], function=function,
                                                     starts_on=starts)
                        self.stdout.write(f"  + PIC {username} {function} @ {code}")
                        log_event(action=AuditAction.PERMISSION_CHANGED, entity_type="picassignment",
                                  entity_id=user.pk, entity_label=f"{username} {function} {code}", actor=None,
                                  after={"function": function, "clinic": code, "starts_on": str(starts)})
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry-run: tidak ada yang disimpan."))
        self.stdout.write(self.style.SUCCESS("Selesai."))
