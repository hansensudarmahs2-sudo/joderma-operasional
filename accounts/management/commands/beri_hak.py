"""Beri atau cabut hak khusus (kapabilitas) satu akun, tercatat di audit.

    python manage.py beri_hak regita tally.correct --catatan "Koordinator Shift Citraland"
    python manage.py beri_hak regita tally.correct --cabut

Sama dengan mencentang kapabilitas di Admin ▸ Pengguna ▸ ubah. Hak khusus tidak disentuh
oleh Reset peran ke default.
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Capability, User, UserCapability
from audit.models import AuditAction
from audit.services import log_event


class Command(BaseCommand):
    help = "Beri/cabut kapabilitas tambahan untuk satu akun."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("kapabilitas", choices=Capability.values)
        parser.add_argument("--catatan", default="")
        parser.add_argument("--cabut", action="store_true")

    def handle(self, username, kapabilitas, catatan, cabut, **opts):
        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            raise CommandError(f"Akun {username} tidak ditemukan.")
        label = Capability(kapabilitas).label
        if cabut:
            n, _ = UserCapability.objects.filter(user=user, capability=kapabilitas).delete()
            if n:
                log_event(action=AuditAction.UPDATE, entity_type="user", entity_id=user.pk,
                          entity_label=user.username, before={"capability": kapabilitas}, after={},
                          reason=catatan or "dicabut lewat beri_hak")
            self.stdout.write(f"{user.username}: {label} {'dicabut' if n else 'memang tidak ada'}.")
            return
        _, created = UserCapability.objects.get_or_create(user=user, capability=kapabilitas,
                                                          defaults={"note": catatan[:200]})
        if created:
            log_event(action=AuditAction.UPDATE, entity_type="user", entity_id=user.pk,
                      entity_label=user.username, before={}, after={"capability": kapabilitas},
                      reason=catatan or "diberikan lewat beri_hak")
        self.stdout.write(f"{user.username}: {label} {'diberikan' if created else 'sudah ada'}.")
