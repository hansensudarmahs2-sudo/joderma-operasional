"""Data sekali jalan: temuan dan sub task Direktur dari sebelum fitur sub task (6 Okt 2026).

1. Assignment sub task temuan milik Direktur Operasional yang masih SUBMITTED (dulu menunggu
   Owner) dikonfirmasi tanpa verifikasi, sesuai aturan baru; task-nya SELESAI bila semua
   assignment sudah dikonfirmasi.
2. Temuan yang semua task aktifnya SELESAI dinyatakan selesai: waktu task terakhir selesai,
   oleh Direktur yang membuat task itu (kosong bila pembuatnya bukan Direktur).

Tanpa notifikasi; tiap perubahan tercatat di riwayat task atau audit. Pembalik tidak mengubah
apa pun, supaya rollback tidak menghapus penutupan yang mungkin sudah benar.
"""
from django.db import migrations
from django.utils import timezone

NOTE = "Selesai tanpa verifikasi (task Direktur pada temuan, migrasi 0004)."
REASON = "Ditutup otomatis oleh migrasi 0004 (temuan sebelum fitur sub task)."


def tutup_data_lama(apps, schema_editor):
    OwnerRequest = apps.get_model("owner", "OwnerRequest")
    ActionItem = apps.get_model("core", "ActionItem")
    TaskAssignment = apps.get_model("core", "TaskAssignment")
    TaskEvent = apps.get_model("core", "TaskEvent")
    UserRole = apps.get_model("accounts", "UserRole")
    AuditEvent = apps.get_model("audit", "AuditEvent")

    temuan_ids = list(OwnerRequest.objects.filter(kind="TEMUAN").values_list("pk", flat=True))
    if not temuan_ids:
        return
    directors = set(UserRole.objects.filter(role="AOM").values_list("user_id", flat=True))
    now = timezone.now()
    subtasks = ActionItem.objects.filter(source_type="permintaan_owner", source_id__in=temuan_ids)

    # 1. Pengajuan Direktur yang tertahan di antrean Owner.
    stuck = TaskAssignment.objects.filter(action_item__in=subtasks, status="SUBMITTED").select_related("action_item")
    touched, auto_confirmed = set(), set()
    for a in stuck:
        if a.assignee_id not in directors and a.claimed_by_id not in directors:
            continue
        a.status = "CONFIRMED"
        a.confirmed_at = now
        a.save(update_fields=["status", "confirmed_at", "updated_at"])
        TaskEvent.objects.create(action_item=a.action_item, assignment=a, event_type="CONFIRMED",
                                 actor_id=a.claimed_by_id or a.assignee_id, note=NOTE)
        touched.add(a.action_item_id)
        auto_confirmed.add(a.pk)
    for item in ActionItem.objects.filter(pk__in=touched):
        if not TaskAssignment.objects.filter(action_item=item).exclude(status="CONFIRMED").exists():
            item.status = "SELESAI"
            item.save(update_fields=["status", "updated_at"])

    def finished_at(item):
        """Kapan task benar-benar selesai: konfirmasi terakhir, atau saat diajukan untuk yang
        baru dikonfirmasi migrasi ini; tanpa assignment, perubahan terakhir task."""
        times = [
            (a.submitted_at or a.confirmed_at) if a.pk in auto_confirmed else a.confirmed_at
            for a in TaskAssignment.objects.filter(action_item=item, status="CONFIRMED")
        ]
        times = [t for t in times if t]
        return max(times) if times else item.updated_at

    # 2. Temuan yang semua task aktifnya sudah selesai.
    for req in OwnerRequest.objects.filter(pk__in=temuan_ids, completed_at__isnull=True):
        tasks = list(subtasks.filter(source_id=req.pk).exclude(status="BATAL"))
        if not tasks or any(t.status != "SELESAI" for t in tasks):
            continue
        finish = {t.pk: finished_at(t) for t in tasks}
        last = max(tasks, key=lambda t: (finish[t.pk], t.pk))
        req.completed_at = finish[last.pk]
        req.completed_by_id = last.created_by_id if last.created_by_id in directors else None
        req.save(update_fields=["completed_at", "completed_by", "updated_at"])
        AuditEvent.objects.create(
            action="CLOSE", entity_type="ownerrequest", entity_id=str(req.pk), entity_label=req.title[:200],
            after_json={"completed_at": req.completed_at.isoformat(), "completed_by": req.completed_by_id},
            reason=REASON,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("owner", "0003_rencana_temuan"),
        ("core", "0008_koordinat_cabang"),
        ("accounts", "0009_tally_correct_capability"),
        ("audit", "0004_alter_auditevent_action"),
    ]

    operations = [migrations.RunPython(tutup_data_lama, migrations.RunPython.noop)]
