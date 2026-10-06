"""Pilah item Inbox oleh Direktur Operasional (GTD, tahap 2 paket B).

Empat hasil, mengikuti matriks wewenang yang diusulkan (Okt 2026):

- TUGASKAN  : bidang Direktur Operasional sendiri (operasional harian, SDM ringan, kas
              <= Rp1 juta) -> buat task dengan PIC, prioritas, target.
- TERUSKAN  : di luar bidangnya (apotek/stok/harga obat, Omnicare, keuangan di atas batas,
              medis, strategis) -> catat diteruskan ke siapa; item tetap dipantau di Inbox.
- RAPAT     : perlu diputuskan bersama -> perkara baru di Keputusan (pemutus Rapat bersama).
- KEBIJAKAN : cukup ditetapkan sebagai aturan yang berlaku, tanpa penugasan -> Keputusan berstatus
              ditetapkan + kebijakan, diumumkan ke semua orang di cabangnya, tanpa nama pelapor
              (5 Okt 2026).
- TIDAK     : tidak ditindaklanjuti, alasan wajib.

Matriks tidak dipaksakan sistem (PP belum disahkan); halaman pilah hanya menampilkannya
sebagai panduan. Semua pilah tercatat di audit log; pada komplain/masukan/kerusakan juga
ditulis di riwayat catatan supaya cabang tahu.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from audit.models import AuditAction
from audit.services import log_event

from . import inbox
from .models import ForwardTo, InboxTriage, TriageAction


def _assert(user) -> None:
    if not inbox.can_triage(user):
        raise PermissionDenied("Pilah Inbox hanya untuk Direktur Operasional.")


def _issue_followup(row, *, actor, action: str, text: str) -> None:
    """Tulis hasil pilah di riwayat komplain/masukan/kerusakan dan majukan statusnya bila boleh."""
    if row["source_type"] != inbox.SOURCE_ISSUE:
        return
    from issues.models import Issue, IssueStatus
    from issues.services import WORKFLOWS, add_update, change_status

    issue = Issue.objects.get(pk=row["source_id"])
    # Dipilah = sudah ditinjau: Baru -> Ditinjau / Dipertimbangkan / Ditriase. Bila ditugaskan dan alurnya
    # mengizinkan, maju sekali lagi ke Ditugaskan. Selain itu cukup catatan di riwayat.
    review = {IssueStatus.DITINJAU, IssueStatus.DIPERTIMBANGKAN, IssueStatus.DITRIASE}
    path = []
    if action != TriageAction.TIDAK and issue.status == IssueStatus.BARU:
        step = next(iter(WORKFLOWS.get(issue.issue_type, {}).get(issue.status, set()) & review), None)
        if step:
            path.append(step)
    if action == TriageAction.TUGASKAN:
        path.append(IssueStatus.DITUGASKAN)
    for status in path:
        if status in WORKFLOWS.get(issue.issue_type, {}).get(issue.status, set()):
            issue = change_status(issue, user=actor, to_status=status, note="Dipilah Direktur Operasional.")
    add_update(issue, user=actor, note=text)


def _existing_triage(row):
    return (InboxTriage.objects.select_related("decision")
            .filter(source_type=row["source_type"], source_id=row["source_id"]).first())


def _waiting_owner_decision(triage):
    """Perkara Owner dari pilahan sebelumnya yang masih menunggu, atau None."""
    from direktur.models import DecisionStatus
    from direktur.services import is_owner_decision

    old = triage.decision if triage else None
    if old and old.status == DecisionStatus.MENUNGGU and is_owner_decision(old):
        return old
    return None


def _cancel_replaced_owner_decision(row, *, actor, new_decision) -> None:
    """Pilah ulang: perkara Owner lama yang masih menunggu dibatalkan, bukan dibiarkan menggantung."""
    from direktur.services import cancel_decision

    old = _waiting_owner_decision(_existing_triage(row))
    if old and (new_decision is None or new_decision.pk != old.pk):
        cancel_decision(old, actor=actor, reason="Pilahan Inbox diubah oleh Direktur Operasional.")


def _save(row, *, actor, action, note="", forwarded_to="", task=None, decision=None) -> InboxTriage:
    _cancel_replaced_owner_decision(row, actor=actor, new_decision=decision)
    triage, created = InboxTriage.objects.update_or_create(
        source_type=row["source_type"], source_id=row["source_id"],
        defaults={"action": action, "note": note.strip(), "forwarded_to": forwarded_to, "task": task,
                  "decision": decision, "triaged_by": actor},
    )
    log_event(
        action=AuditAction.CREATE if created else AuditAction.UPDATE,
        entity_type="inboxtriage", entity_id=triage.pk,
        entity_label=f"Pilah {row['kind_label']} {row['ref']}: {triage.get_action_display()}",
        actor=actor,
        after={"source": f"{row['source_type']}#{row['source_id']}", "action": action,
               "forwarded_to": forwarded_to, "task": task.pk if task else None,
               "decision": decision.pk if decision else None, "note": note.strip()[:300]},
    )
    return triage


@transaction.atomic
def assign(row, *, actor, title, clinic=None, target="", targets=None, description="", priority="SEDANG",
           due_at=None) -> InboxTriage:
    """Jadikan task. `targets` = [(cabang, penerima), ...] untuk hal yang berlaku di beberapa cabang:
    satu task per cabang, semuanya bersumber item yang sama."""
    from direktur import services as direktur

    _assert(actor)
    pairs = list(targets) if targets else [(clinic, target)]
    if not pairs or any(c is None for c, _ in pairs):
        raise ValidationError("Pilih cabang.")
    if any(not (t or "").strip() for _, t in pairs):
        raise ValidationError("Pilih PIC untuk setiap cabang.")
    tasks = []
    for n, (branch, who) in enumerate(pairs):
        if row["source_type"] == inbox.SOURCE_NOTE and n == 0:
            from direktur.models import DirectorNote

            note = DirectorNote.objects.get(pk=row["source_id"])
            task = direktur.convert_note(note, user=actor, clinic=branch, title=title, target=who,
                                         priority=priority, due_at=due_at)
        else:
            task = direktur.create_task_from_source(
                actor=actor, clinic=branch, title=title, target=who,
                description=description or row["description"], priority=priority, due_at=due_at,
                source_type=row["source_type"], source_id=row["source_id"],
                source_label=f"{row['kind_label']} {row['ref']}",
            )
        tasks.append(task)
    multi = len(tasks) > 1
    note_text = f"Berlaku untuk {len(tasks)} cabang: " + ", ".join(t.clinic.name for t in tasks) if multi else ""
    triage = _save(row, actor=actor, action=TriageAction.TUGASKAN, task=tasks[0], note=note_text)
    parts = []
    for task in tasks:
        names = ", ".join(str(a.assignee) for a in task.task_assignments.all()) or "belum ada penerima"
        parts.append(f"{names} ({task.clinic.name})" if multi else names)
    _issue_followup(row, actor=actor, action=TriageAction.TUGASKAN,
                    text=f"Dipilah Direktur Operasional: dijadikan task \"{tasks[0].title}\" untuk {'; '.join(parts)}.")
    return triage


def _owner_decision(row, *, actor, note: str):
    """Teruskan ke Owner = perkara Keputusan berpemutus Owner, supaya Owner diberi tahu dan memutuskan."""
    from direktur.models import Decider
    from direktur.services import create_decision

    lines = [
        (row.get("description") or "").strip(),
        f"Rujukan: {row['ref']} ({row['kind_label']}, dari {row.get('reporter') or '-'})",
    ]
    if note.strip():
        lines.append(f"Catatan Direktur: {note.strip()}")
    return create_decision(actor=actor, title=row["title"][:200], decider=Decider.OWNER, clinic=row.get("clinic"),
                           background="\n\n".join(line for line in lines if line))


@transaction.atomic
def forward(row, *, actor, to: str, note: str = "") -> InboxTriage:
    _assert(actor)
    if to not in dict(ForwardTo.choices):
        raise ValidationError("Pilih diteruskan ke siapa.")
    if to == ForwardTo.LAINNYA and not note.strip():
        raise ValidationError("Tulis diteruskan ke siapa.")
    decision = None
    if to == ForwardTo.DIRUT:
        decision = _waiting_owner_decision(_existing_triage(row)) or _owner_decision(row, actor=actor, note=note)
    triage = _save(row, actor=actor, action=TriageAction.TERUSKAN, forwarded_to=to, note=note, decision=decision)
    label = ForwardTo(to).label.split(" (")[0]
    _issue_followup(row, actor=actor, action=TriageAction.TERUSKAN,
                    text=f"Dipilah Direktur Operasional: diteruskan ke {label}." + (f" {note.strip()}" if note.strip() else ""))
    return triage


@transaction.atomic
def to_meeting(row, *, actor, title: str = "", background: str = "", needed_by=None,
               clinic="asal") -> InboxTriage:
    """Bawa ke rapat. `clinic`: "asal" = cabang item; None = lintas cabang; atau cabang tertentu."""
    from direktur import services as direktur
    from direktur.models import Decider

    _assert(actor)
    decision = direktur.create_decision(
        actor=actor, title=(title or row["title"])[:200], decider=Decider.RAPAT_BERSAMA,
        clinic=row["clinic"] if clinic == "asal" else clinic,
        reference=row["ref"][:30], background=background or row["description"], needed_by=needed_by,
    )
    triage = _save(row, actor=actor, action=TriageAction.RAPAT, decision=decision)
    _issue_followup(row, actor=actor, action=TriageAction.RAPAT,
                    text="Dipilah Direktur Operasional: dibawa ke rapat bersama (Kamis) untuk diputuskan.")
    return triage


@transaction.atomic
def to_policy(row, *, actor, title: str, text: str, clinic="semua", effective_on=None) -> InboxTriage:
    """Jadikan kebijakan berlaku dan umumkan. `clinic`: "asal" = cabang item; "semua"/None = semua
    cabang; atau cabang tertentu. Pengumuman hanya memuat judul dan isi yang ditulis Direktur:
    nama pelapor dan uraian aslinya tidak ikut."""
    from direktur import services as direktur
    from direktur.models import Decider

    _assert(actor)
    if not (title or "").strip():
        raise ValidationError("Judul kebijakan wajib diisi.")
    if not (text or "").strip():
        raise ValidationError("Isi kebijakan wajib diisi.")
    target = row["clinic"] if clinic == "asal" else (None if clinic in ("semua", None) else clinic)
    decision = direktur.create_decision(
        actor=actor, title=title.strip()[:200], decider=Decider.DIREKTUR_OPERASIONAL, clinic=target,
        reference=row["ref"][:30], background=f"Berasal dari {row['kind_label'].lower()} di Inbox.",
    )
    direktur.settle_decision(decision, actor=actor, decision_text=text, is_policy=True, decided_on=effective_on)
    triage = _save(row, actor=actor, action=TriageAction.KEBIJAKAN, decision=decision,
                   note=f"Kebijakan \"{decision.title}\" untuk {target.name if target else 'semua cabang'}.")
    _issue_followup(row, actor=actor, action=TriageAction.KEBIJAKAN,
                    text=f"Dipilah Direktur Operasional: dijadikan kebijakan \"{decision.title}\" dan diumumkan.")
    return triage


@transaction.atomic
def dismiss(row, *, actor, reason: str) -> InboxTriage:
    _assert(actor)
    if not (reason or "").strip():
        raise ValidationError("Alasan wajib diisi.")
    triage = _save(row, actor=actor, action=TriageAction.TIDAK, note=reason)
    _issue_followup(row, actor=actor, action=TriageAction.TIDAK,
                    text=f"Dipilah Direktur Operasional: tidak ditindaklanjuti. Alasan: {reason.strip()}")
    return triage
