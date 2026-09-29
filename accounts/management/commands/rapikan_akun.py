"""Rapikan akun sebelum jadwal Oktober 2026 (arahan product owner 29 September 2026).

    manage.py rapikan_akun --dry-run
    manage.py rapikan_akun --password klinik123

1. Username berakhiran `_pic` diganti tanpa akhiran (mis. `desy_pic` → `desy`).
   Akunnya tetap akun yang sama (id sama), jadi catatan, task, checklist, dan
   audit yang sudah ada tetap melekat. Bila nama tujuan sudah dipakai akun lain,
   akun itu dilewati dan dilaporkan — tidak ada yang digabung diam-diam.
2. Password seluruh akun aktif diganti ke password awal yang sama, dan setiap
   akun ditandai wajib ganti password saat login berikutnya.

Semua perubahan tercatat di audit log.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from audit.models import AuditAction
from audit.services import log_event


class Command(BaseCommand):
    help = "Hapus akhiran _pic dari username dan setel ulang password semua akun aktif."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="", help="Password awal untuk semua akun aktif.")
        parser.add_argument("--akhiran", default="_pic", help="Akhiran username yang dibuang (bawaan _pic).")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, password="", akhiran="_pic", dry_run=False, **opts):
        if not password and not dry_run:
            raise CommandError("Berikan --password (atau --dry-run untuk melihat rencananya).")
        renamed = skipped = reset = 0
        with transaction.atomic():
            for user in User.objects.filter(username__iendswith=akhiran).order_by("username"):
                new = user.username[: -len(akhiran)]
                if not new or User.objects.filter(username__iexact=new).exclude(pk=user.pk).exists():
                    self.stdout.write(self.style.WARNING(f"! {user.username}: '{new}' sudah dipakai akun lain, dilewati"))
                    skipped += 1
                    continue
                self.stdout.write(f"~ {user.username} -> {new}")
                old = user.username
                user.username = new
                user.save(update_fields=["username"])
                log_event(action=AuditAction.UPDATE, entity_type="user", entity_id=user.pk, entity_label=new,
                          before={"username": old}, after={"username": new}, reason="Hapus akhiran _pic")
                renamed += 1
            for user in User.objects.filter(is_active=True).order_by("username"):
                self.stdout.write(f"  password awal: {user.username} ({user})")
                user.set_password(password or "dry-run")
                user.must_change_password = True
                user.save(update_fields=["password", "must_change_password"])
                log_event(action=AuditAction.PASSWORD_CHANGED, entity_type="user", entity_id=user.pk,
                          entity_label=user.username, reason="Setel ulang ke password awal; wajib ganti saat login")
                reset += 1
            if dry_run:
                transaction.set_rollback(True)
        suffix = " (dry-run, tidak disimpan)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"Diganti namanya {renamed}, dilewati {skipped}, password disetel ulang {reset}{suffix}."
        ))
