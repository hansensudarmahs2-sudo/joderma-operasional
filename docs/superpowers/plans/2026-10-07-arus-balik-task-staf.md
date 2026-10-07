# Arus balik staf ↔ Direktur pada task (tahap 3a) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lapor progres, balasan, dan kendala dari staf sampai ke pemberi tugas dan semua Direktur; komentar dan persetujuan target dari Direktur sampai ke staf; staf dapat menandai task terhambat dengan usulan target yang bisa disetujui satu tombol.

**Architecture:** Riwayat `core.TaskEvent` yang ada menjadi percakapan task (dua jenis baru: `KENDALA`, `TARGET_DIUBAH`). Empat kolom baru di `core.ActionItem` menyimpan tanda terhambat. Semua aturan dan notifikasi di `core/task_services.py`; staf memakai kartu "Tugas saya" (`templates/core/_my_tasks.html`) dan dua URL baru di app `core`; Direktur memakai halaman detail task, Daftar Task, Tim, dan Ringkasan yang ada.

**Tech Stack:** Django 5.1, Python 3.11 (`.venv`), pytest + pytest-django, template Django.

**Spec:** `docs/superpowers/specs/2026-10-07-arus-balik-task-staf-design.md`

## Global Constraints

- Kerja di worktree WSL `~/joderma-tahap3a` (branch `tahap3a`) dengan `.venv/bin/python` (Python 3.11). Jangan menyentuh `~/joderma-operasional`.
- **Jangan commit, `git add`, stash, atau mengubah index git.** Index dipakai controller sebagai titik periksa; tiap task ditinjau sebagai `git diff`.
- Otorisasi di service (server-side); menyembunyikan tombol bukan kontrol akses.
- Notifikasi dari staf (progres, balasan, kendala) → pemberi tugas (`created_by`, bila aktif) + semua pengguna aktif ber-`Role.AOM`, tanpa duplikat, tidak ke penulis.
- Notifikasi dari pemberi tugas/Direktur (komentar, setujui target) → penerima task yang assignment-nya bukan `CANCELLED`, aktif, tidak ke penulis.
- `type_code` persis: `TASK_PROGRESS`, `TASK_COMMENT`, `TASK_BLOCKED`, `TASK_DUE_CHANGED`.
- Tautan notifikasi: untuk pengamat (pemberi tugas/Direktur) `direktur:task_detail` args `[item.pk]`; untuk penerima `reverse("core:today") + "#task-<pk>"`.
- Usulan target staf dicatat pukul 21.00 waktu lokal pada tanggal yang dipilih; tidak boleh sebelum hari ini.
- Migrasi additive: `core 0009_task_kendala`.
- Teks antarmuka dan komentar berbahasa Indonesia, mengikuti gaya file sekitarnya.
- `pytest.ini` sudah menambah `-q`. Ringkasan: `| grep -E "passed|failed|^FAILED" | tail -3`. Test `stok/` kadang gagal acak (dikenal); ulangi sekali bila hanya itu yang gagal.

---

## File Structure

| File | Tanggung jawab |
|---|---|
| `core/models.py` | `TaskEventType.KENDALA`, `TARGET_DIUBAH`; kolom terhambat di `ActionItem`; properti `is_blocked` |
| `core/migrations/0009_task_kendala.py` | migrasi additive (makemigrations) |
| `core/task_services.py` | penerima notifikasi, `report_blocker`, `approve_proposed_due`, notifikasi di `report_progress`/`add_task_comment`, hapus tanda terhambat saat selesai/batal; `my_task_row` memuat percakapan |
| `core/views.py`, `core/urls.py` | `assignment_blocker`, `task_comment` |
| `templates/core/_my_tasks.html` | kartu staf: Percakapan, Ada kendala, label Terhambat |
| `direktur/views.py`, `templates/direktur/task_detail.html` | kotak Terhambat + Setujui target |
| `templates/direktur/task_list.html`, `templates/direktur/team.html` | label Terhambat |
| `direktur/dashboard.py`, `templates/direktur/_overview_body.html` | jumlah task terhambat di Ringkasan |
| `core/tests/test_arus_balik_task.py`, `direktur/tests/test_task_terhambat.py` | test |
| `docs/panduan-staf.md`, `docs/panduan-direktur.md`, `docs/peran-dan-akses.md`, `README.md` | dokumentasi |

---

### Task 1: Data, aturan, dan notifikasi task

**Files:**
- Modify: `core/models.py` (`class TaskEventType`, `class ActionItem`)
- Create: `core/migrations/0009_task_kendala.py` (makemigrations)
- Modify: `core/task_services.py`
- Create: `core/tests/test_arus_balik_task.py`

**Interfaces:**
- Produces: `TaskEventType.KENDALA`, `TaskEventType.TARGET_DIUBAH`; `ActionItem.blocked_at`, `blocked_by`, `blocked_reason`, `proposed_due_at`, `ActionItem.is_blocked -> bool`; `task_services.report_blocker(assignment, *, user, reason: str, proposed_due: dt.date | None = None) -> TaskEvent`; `task_services.approve_proposed_due(item, *, actor) -> ActionItem`; `task_services.THREAD_EVENTS: tuple[str, ...]`.

- [ ] **Step 1: Tulis test yang gagal**

Buat `core/tests/test_arus_balik_task.py`:

```python
"""Arus balik staf ↔ Direktur pada task (tahap 3a, 7 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import (
    ActionItem, ActionItemStatus, Clinic, TaskAssignmentStatus, TaskAudienceType, TaskEventType, local_today,
)
from core import task_services as ts
from notifications.models import Notification

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def rina(jemur):
    return _user(jemur, "rina", Role.AOM, display_name="Rina")


@pytest.fixture
def sinta(jemur):
    return _user(jemur, "sinta", Role.SUPERVISOR, Role.STAF, display_name="Sinta")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.STAF, display_name="Desy")


@pytest.fixture
def yani(jemur):
    return _user(jemur, "yani", Role.STAF, display_name="Yani")


def _task(actor, clinic, *people, title="Ganti filter AC"):
    ids = [p.pk for p in people]
    audience = TaskAudienceType.USER if len(ids) == 1 else TaskAudienceType.USERS
    return ts.create_task(clinic=clinic, actor=actor, title=title, audience_type=audience, user_ids=ids)


def _notes(type_code):
    return {n.user.username: n for n in Notification.objects.filter(type_code=type_code)}


# --- Task 1: aturan dan notifikasi --------------------------------------------------------


def test_progress_notifies_creator_and_all_directors(jemur, hansen, rina, sinta, desy):
    item = _task(sinta, jemur, desy)
    ts.report_progress(item.task_assignments.get(), user=desy, note="Vendor dihubungi")
    notes = _notes("TASK_PROGRESS")
    assert set(notes) == {"sinta", "hansen1", "rina"}
    assert notes["hansen1"].url == reverse("direktur:task_detail", args=[item.pk])
    assert "Ganti filter AC" in notes["sinta"].title


def test_progress_no_duplicate_when_creator_is_director(jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    ts.report_progress(item.task_assignments.get(), user=desy, note="Mulai")
    assert Notification.objects.filter(type_code="TASK_PROGRESS", user=hansen).count() == 1


def test_staff_reply_to_watchers_and_director_comment_to_active_recipients(jemur, hansen, sinta, desy, yani):
    item = _task(sinta, jemur, desy, yani)
    ts.cancel_assignment(item.task_assignments.get(assignee=yani), actor=sinta, reason="dipindah")
    ts.add_task_comment(item, actor=desy, note="Boleh pakai vendor lama?")
    assert set(_notes("TASK_COMMENT")) == {"sinta", "hansen1"}
    Notification.objects.all().delete()
    ts.add_task_comment(item, actor=hansen, note="Boleh, maksimal Rp200 ribu")
    notes = _notes("TASK_COMMENT")
    assert set(notes) == {"desy"}  # yani dibatalkan; sinta pemberi tugas, bukan penerima
    assert notes["desy"].url == reverse("core:today") + f"#task-{item.pk}"


def test_blocker_validation(jemur, hansen, desy, yani):
    a = _task(hansen, jemur, desy).task_assignments.get()
    with pytest.raises(ValidationError):
        ts.report_blocker(a, user=desy, reason="  ")
    with pytest.raises(ValidationError):
        ts.report_blocker(a, user=desy, reason="Vendor telat", proposed_due=local_today() - dt.timedelta(days=1))
    with pytest.raises(PermissionDenied):
        ts.report_blocker(a, user=yani, reason="Bukan tugas saya")
    item = ActionItem.objects.get(pk=a.action_item_id)
    assert not item.is_blocked and not item.task_events.filter(event_type=TaskEventType.KENDALA).exists()


def test_blocker_marks_task_and_notifies(jemur, hansen, sinta, desy):
    item = _task(sinta, jemur, desy)
    proposed = local_today() + dt.timedelta(days=3)
    ts.report_blocker(item.task_assignments.get(), user=desy, reason="Vendor baru bisa Jumat", proposed_due=proposed)
    item.refresh_from_db()
    assert item.is_blocked and item.blocked_by == desy and item.blocked_reason == "Vendor baru bisa Jumat"
    local_due = dt.datetime.combine(proposed, dt.time(21, 0))
    from django.utils import timezone
    assert timezone.localtime(item.proposed_due_at).replace(tzinfo=None) == local_due
    event = item.task_events.get(event_type=TaskEventType.KENDALA)
    assert event.note == f"Vendor baru bisa Jumat · usul target {proposed:%d/%m/%Y}"
    assert set(_notes("TASK_BLOCKED")) == {"sinta", "hansen1"}


def test_blocker_refused_after_submit(jemur, hansen, desy):
    a = _task(hansen, jemur, desy).task_assignments.get()
    ts.submit_assignment(a, user=desy, note="Selesai")
    a.refresh_from_db()
    with pytest.raises(ValidationError):
        ts.report_blocker(a, user=desy, reason="Telat")


def test_progress_clears_blocked(jemur, hansen, desy):
    a = _task(hansen, jemur, desy).task_assignments.get()
    ts.report_blocker(a, user=desy, reason="Menunggu sparepart")
    ts.report_progress(a, user=desy, note="Sparepart datang")
    item = ActionItem.objects.get(pk=a.action_item_id)
    assert not item.is_blocked and item.blocked_at is None and item.blocked_reason == ""


def test_approve_proposed_due(jemur, hansen, sinta, desy):
    item = _task(sinta, jemur, desy)
    proposed = local_today() + dt.timedelta(days=2)
    ts.report_blocker(item.task_assignments.get(), user=desy, reason="Vendor telat", proposed_due=proposed)
    Notification.objects.all().delete()
    item.refresh_from_db()
    with pytest.raises(PermissionDenied):
        ts.approve_proposed_due(item, actor=desy)
    expected = item.proposed_due_at
    ts.approve_proposed_due(item, actor=hansen)
    item.refresh_from_db()
    assert item.due_at == expected and not item.is_blocked and item.proposed_due_at is None
    assert item.task_events.filter(event_type=TaskEventType.TARGET_DIUBAH, actor=hansen).exists()
    note = Notification.objects.get(type_code="TASK_DUE_CHANGED")
    assert note.user == desy and note.url == reverse("core:today") + f"#task-{item.pk}"
    with pytest.raises(ValidationError):
        ts.approve_proposed_due(item, actor=hansen)


def test_finish_and_cancel_clear_blocked(jemur, hansen, desy):
    done = _task(hansen, jemur, desy, title="Selesai")
    a = done.task_assignments.get()
    ts.report_blocker(a, user=desy, reason="Telat")
    ts.submit_assignment(a, user=desy, note="Beres")
    ts.confirm_assignment(ActionItem.objects.get(pk=done.pk).task_assignments.get(), reviewer=hansen)
    done.refresh_from_db()
    assert done.status == ActionItemStatus.SELESAI and done.blocked_at is None
    cancelled = _task(hansen, jemur, desy, title="Batal")
    ts.report_blocker(cancelled.task_assignments.get(), user=desy, reason="Telat")
    ts.cancel_task(ActionItem.objects.get(pk=cancelled.pk), actor=hansen, reason="Tidak perlu")
    cancelled.refresh_from_db()
    assert cancelled.blocked_at is None


def test_old_tasks_not_blocked(jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    assert not item.is_blocked and item.blocked_reason == ""
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest core/tests/test_arus_balik_task.py`
Expected: FAIL — `AttributeError: module 'core.task_services' has no attribute 'report_blocker'` dan `AttributeError: 'ActionItem' object has no attribute 'is_blocked'`.

- [ ] **Step 3: Model dan migrasi**

Di `core/models.py`, `class TaskEventType`, tambahkan sesudah `PROGRESS`:

```python
    KENDALA = "KENDALA", "Kendala"
    TARGET_DIUBAH = "TARGET_DIUBAH", "Target diubah"
```

Di `class ActionItem`, sesudah field `review_by`:

```python
    # Tahap 3a arus balik (7 Okt 2026): staf menandai task terhambat, opsional dengan usulan target.
    blocked_at = models.DateTimeField("ditandai terhambat", null=True, blank=True)
    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    blocked_reason = models.TextField("alasan terhambat", blank=True)
    proposed_due_at = models.DateTimeField("usulan target baru", null=True, blank=True)
```

dan properti (di dekat `is_overdue`):

```python
    @property
    def is_blocked(self) -> bool:
        """Terhambat menurut penerima dan task masih terbuka (tahap 3a)."""
        return self.blocked_at is not None and self.status in (ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN)
```

Run: `.venv/bin/python manage.py makemigrations core --name task_kendala`
Expected: `core/migrations/0009_task_kendala.py` dengan empat `AddField` dan satu `AlterField` (choices `event_type`).

- [ ] **Step 4: Service di `core/task_services.py`**

Pastikan `local_today` diimpor dari `.models` (tambahkan ke daftar import `.models` bila belum ada) dan `import datetime as dt` di atas file. Tambahkan sesudah `_notify_reviewers`:

```python
# --- Arus balik staf ↔ Direktur (tahap 3a, 7 Okt 2026) ------------------------------------

BLOCKED_FIELDS = ["blocked_at", "blocked_by", "blocked_reason", "proposed_due_at"]
THREAD_EVENTS = (
    TaskEventType.PROGRESS,
    TaskEventType.COMMENT,
    TaskEventType.KENDALA,
    TaskEventType.TARGET_DIUBAH,
    TaskEventType.REVISION_REQUESTED,
)


def _clear_blocked(item: ActionItem) -> list[str]:
    """Kosongkan tanda terhambat; kembalikan nama field untuk `update_fields`."""
    item.blocked_at = None
    item.blocked_by = None
    item.blocked_reason = ""
    item.proposed_due_at = None
    return list(BLOCKED_FIELDS)


def _watchers(item: ActionItem) -> list[User]:
    """Pemberi tugas dan semua Direktur Operasional aktif (product owner memantau semua task)."""
    people = {u.pk: u for u in User.objects.filter(is_active=True, user_roles__role=Role.AOM).distinct()}
    if item.created_by_id and item.created_by.is_active:
        people.setdefault(item.created_by_id, item.created_by)
    return list(people.values())


def _active_recipients(item: ActionItem) -> list[User]:
    people = {}
    for a in item.task_assignments.exclude(status=TaskAssignmentStatus.CANCELLED).select_related("assignee"):
        if a.assignee.is_active:
            people.setdefault(a.assignee_id, a.assignee)
    return list(people.values())


def _notify_task(people, *, actor, item: ActionItem, type_code: str, title: str, body: str, to_staff: bool) -> None:
    """Satu notifikasi per orang, tidak ke penulis. Staf ditautkan ke Hari Ini, pengamat ke detail task."""
    from django.urls import reverse

    for person in {p.pk: p for p in people}.values():
        if person.pk == actor.pk:
            continue
        if to_staff:
            notif = notify_user(person, type_code=type_code, title=title, body=body[:300],
                                entity_ref=f"actionitem#{item.pk}")
            if notif is not None:
                notif.url = reverse("core:today") + f"#task-{item.pk}"
                notif.save(update_fields=["url"])
        else:
            notify_user(person, type_code=type_code, title=title, body=body[:300], entity_ref=f"actionitem#{item.pk}",
                        url_name="direktur:task_detail", url_args=[item.pk])


@transaction.atomic
def report_blocker(assignment: TaskAssignment, *, user, reason: str, proposed_due: dt.date | None = None) -> TaskEvent:
    """Penerima menandai task terhambat: alasan wajib, usulan target opsional (pukul 21.00 lokal)."""
    from audit.models import AuditAction
    from audit.services import log_event

    if assignment.assignee_id != user.pk and assignment.claimed_by_id != user.pk:
        raise PermissionDenied("Anda bukan penerima task ini.")
    item = assignment.action_item
    workable = (TaskAssignmentStatus.OPEN, TaskAssignmentStatus.IN_PROGRESS, TaskAssignmentStatus.REVISION_REQUIRED)
    if assignment.status not in workable or item.status not in (ActionItemStatus.BARU, ActionItemStatus.DIKERJAKAN):
        raise ValidationError("Task ini sudah diajukan selesai, dikonfirmasi, atau dibatalkan.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Tulis kendalanya.")
    due = None
    if proposed_due is not None:
        if proposed_due < local_today():
            raise ValidationError("Usulan target tidak boleh sebelum hari ini.")
        due = timezone.make_aware(dt.datetime.combine(proposed_due, dt.time(21, 0)))
    item.blocked_at = timezone.now()
    item.blocked_by = user
    item.blocked_reason = reason
    item.proposed_due_at = due
    item.save(update_fields=[*BLOCKED_FIELDS, "updated_at"])
    note = reason + (f" · usul target {proposed_due:%d/%m/%Y}" if proposed_due else "")
    event = TaskEvent.objects.create(action_item=item, assignment=assignment, event_type=TaskEventType.KENDALA,
                                     actor=user, note=note)
    log_event(action=AuditAction.UPDATE, entity_type="actionitem", entity_id=item.pk,
              entity_label=f"Kendala: {item.title}"[:200], actor=user, after={"kendala": note[:300]})
    _notify_task(_watchers(item), actor=user, item=item, type_code="TASK_BLOCKED",
                 title=f"Kendala: {item.title}", body=f"{user}: {note}", to_staff=False)
    return event


@transaction.atomic
def approve_proposed_due(item: ActionItem, *, actor) -> ActionItem:
    """Pemberi tugas/Direktur menyetujui usulan target baru dari penerima."""
    from audit.services import log_update, snapshot

    _assert_manage(item, actor)
    _assert_open(item)
    if not item.is_blocked or item.proposed_due_at is None:
        raise ValidationError("Tidak ada usulan target baru untuk disetujui.")
    before = snapshot(item)
    new_due = item.proposed_due_at
    item.due_at = new_due
    fields = _clear_blocked(item)
    item.save(update_fields=["due_at", *fields, "updated_at"])
    log_update(item, before, actor=actor)
    label = f"{timezone.localtime(new_due):%d/%m/%Y %H.%M}"
    TaskEvent.objects.create(action_item=item, event_type=TaskEventType.TARGET_DIUBAH, actor=actor,
                             note=f"Target diubah ke {label}")
    _notify_task(_active_recipients(item), actor=actor, item=item, type_code="TASK_DUE_CHANGED",
                 title=f"Target baru disetujui: {item.title}", body=f"Target diubah ke {label} oleh {actor}",
                 to_staff=True)
    return item
```

Di `report_progress`, ganti `return TaskEvent.objects.create(...)` di akhir dengan:

```python
    event = TaskEvent.objects.create(
        action_item=assignment.action_item, assignment=assignment, event_type=TaskEventType.PROGRESS,
        actor=user, note=note,
    )
    item = assignment.action_item
    if item.blocked_at is not None:
        item.save(update_fields=[*_clear_blocked(item), "updated_at"])
    _notify_task(_watchers(item), actor=user, item=item, type_code="TASK_PROGRESS",
                 title=f"Progres: {item.title}", body=f"{user}: {note}", to_staff=False)
    return event
```

Di `add_task_comment`, ganti `return TaskEvent.objects.create(...)` di akhir dengan:

```python
    event = TaskEvent.objects.create(action_item=item, event_type=TaskEventType.COMMENT, actor=actor, note=note)
    if is_recipient and not can_manage_task(item, actor):
        _notify_task(_watchers(item), actor=actor, item=item, type_code="TASK_COMMENT",
                     title=f"Balasan di task: {item.title}", body=f"{actor}: {note}", to_staff=False)
    else:
        _notify_task(_active_recipients(item), actor=actor, item=item, type_code="TASK_COMMENT",
                     title=f"Catatan di task: {item.title}", body=f"{actor}: {note}", to_staff=True)
    return event
```

Hapus tanda terhambat saat selesai dan batal:
- `_finish_item_if_all_confirmed`: `item.save(update_fields=["status", *_clear_blocked(item), "updated_at"])`.
- `close_task`: `item.save(update_fields=["status", "progress_note", *_clear_blocked(item), "updated_at"])` (sesudah `snapshot` diambil).
- `cancel_task`: `item.save(update_fields=["status", "progress_note", *_clear_blocked(item), "updated_at"])`.
- [ ] **Step 5: Jalankan test**

Run: `.venv/bin/python -m pytest core/tests/test_arus_balik_task.py core owner direktur`
Expected: semua PASS.

---

### Task 2: Kartu staf — Percakapan dan Ada kendala

**Files:**
- Modify: `core/urls.py`, `core/views.py`
- Modify: `core/task_services.py` (`my_task_row`)
- Modify: `templates/core/_my_tasks.html`
- Test: `core/tests/test_arus_balik_task.py` (tambahkan)

**Interfaces:**
- Consumes: `report_blocker`, `add_task_comment`, `THREAD_EVENTS`, `ActionItem.is_blocked` (Task 1).
- Produces: URL `core:assignment_blocker` (`hari-ini/assignment/<pk>/kendala/`, POST `alasan`, `target`), `core:task_comment` (`hari-ini/task/<pk>/komentar/`, POST `catatan`); `my_task_row` kunci `thread`, `thread_count`, `blocked`.

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan ke `core/tests/test_arus_balik_task.py`:

```python
# --- Task 2: kartu staf -----------------------------------------------------------------


def test_staff_card_has_thread_and_blocker(client, jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    ts.report_progress(item.task_assignments.get(), user=desy, note="Mulai dikerjakan")
    ts.add_task_comment(item, actor=hansen, note="Tolong foto hasilnya")
    client.force_login(desy)
    body = client.get(reverse("core:today")).content.decode()
    assert f'id="task-{item.pk}"' in body and "Percakapan (2)" in body and "Ada kendala" in body
    assert body.index("Mulai dikerjakan") < body.index("Tolong foto hasilnya")


def test_staff_posts_blocker_and_sees_label(client, jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    a = item.task_assignments.get()
    client.force_login(desy)
    target = (local_today() + dt.timedelta(days=2)).isoformat()
    client.post(reverse("core:assignment_blocker", args=[a.pk]), {"alasan": "Vendor telat", "target": target})
    item.refresh_from_db()
    assert item.is_blocked and item.proposed_due_at is not None
    assert "Terhambat" in client.get(reverse("core:today")).content.decode()


def test_blocker_bad_date_and_missing_reason_show_errors(client, jemur, hansen, desy):
    a = _task(hansen, jemur, desy).task_assignments.get()
    client.force_login(desy)
    body = client.post(reverse("core:assignment_blocker", args=[a.pk]), {"alasan": "x", "target": "31-12-2026"},
                       follow=True).content.decode()
    assert "Format tanggal target tidak valid." in body
    body = client.post(reverse("core:assignment_blocker", args=[a.pk]), {"alasan": ""}, follow=True).content.decode()
    assert "Tulis kendalanya." in body
    assert not ActionItem.objects.get(pk=a.action_item_id).is_blocked


def test_staff_reply_from_card(client, jemur, hansen, desy):
    item = _task(hansen, jemur, desy)
    client.force_login(desy)
    client.post(reverse("core:task_comment", args=[item.pk]), {"catatan": "Boleh pakai vendor lama?"})
    assert item.task_events.filter(event_type=TaskEventType.COMMENT, actor=desy).exists()
    assert Notification.objects.filter(user=hansen, type_code="TASK_COMMENT").exists()


def test_non_recipient_cannot_post_blocker_or_reply(client, jemur, hansen, desy, yani):
    item = _task(hansen, jemur, desy)
    client.force_login(yani)
    assert client.post(reverse("core:assignment_blocker", args=[item.task_assignments.get().pk]),
                       {"alasan": "x"}).status_code == 403
    assert client.post(reverse("core:task_comment", args=[item.pk]), {"catatan": "x"}).status_code == 403
    assert not item.task_events.filter(event_type__in=[TaskEventType.KENDALA, TaskEventType.COMMENT]).exists()
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest core/tests/test_arus_balik_task.py -k "card or posts_blocker or bad_date or reply_from or non_recipient"`
Expected: FAIL — `NoReverseMatch` untuk `assignment_blocker` / `task_comment`.

- [ ] **Step 3: URL dan view**

Di `core/urls.py`, sesudah baris `assignment_progress`:

```python
    path("assignment/<int:pk>/kendala/", views.assignment_blocker, name="assignment_blocker"),
    path("task/<int:pk>/komentar/", views.task_comment, name="task_comment"),
```

Di `core/views.py`, sesudah `assignment_progress`:

```python
@login_required
@require_POST
def assignment_blocker(request, pk: int):
    """Penerima menandai task terhambat: alasan wajib, usulan target opsional (tahap 3a)."""
    import datetime as dt

    from .task_services import report_blocker

    assignment = _assignment_or_404(pk)
    if not can_access_clinic(request.user, assignment.action_item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    raw = (request.POST.get("target") or "").strip()
    try:
        proposed = dt.date.fromisoformat(raw) if raw else None
    except ValueError:
        messages.error(request, "Format tanggal target tidak valid.")
        return _back(request, "core:action_items")
    try:
        report_blocker(assignment, user=request.user, reason=request.POST.get("alasan", ""), proposed_due=proposed)
        messages.success(request, "Kendala dikirim ke pemberi tugas dan Direktur Operasional.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back(request, "core:action_items")


@login_required
@require_POST
def task_comment(request, pk: int):
    """Balasan di percakapan task dari kartu "Tugas saya" (tahap 3a)."""
    from .task_services import add_task_comment

    item = get_object_or_404(ActionItem, pk=pk)
    if not can_access_clinic(request.user, item.clinic):
        raise PermissionDenied("Anda tidak memiliki akses ke task cabang ini.")
    try:
        add_task_comment(item, actor=request.user, note=request.POST.get("catatan", ""))
        messages.success(request, "Balasan terkirim.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _back(request, "core:today")
```

Pastikan `ActionItem` dan `get_object_or_404` diimpor di `core/views.py`; tambahkan bila belum.

- [ ] **Step 4: Data kartu**

Di `core/task_services.py` `my_task_row`, sebelum `return {`, tambahkan:

```python
    thread_qs = item.task_events.filter(event_type__in=THREAD_EVENTS)
    thread = list(thread_qs.select_related("actor").order_by("-created_at")[:10])[::-1]
```

dan tambahkan ke dict yang dikembalikan:

```python
        "thread": thread,
        "thread_count": thread_qs.count(),
        "blocked": item.is_blocked,
```

- [ ] **Step 5: Template kartu**

Di `templates/core/_my_tasks.html`:

(a) Ganti `<li class="request-row{% if t.waiting %} is-waiting{% endif %}">` dengan
`<li class="request-row{% if t.waiting %} is-waiting{% endif %}" id="task-{{ t.item.pk }}">`.

(b) Ganti blok `{% if t.can_submit %}<span class="task-actions-row"> … </span>{% endif %}` dengan:

```html
        <span class="task-actions-row">
        {% if t.can_submit %}
        <details class="task-submit">
          <summary class="btn small secondary">Lapor progres</summary>
          <form method="post" data-jejak action="{% url 'core:assignment_progress' t.assignment.pk %}" enctype="multipart/form-data" class="stack-form">
            {% csrf_token %}<input type="hidden" name="next" value="{{ request.get_full_path }}">
            <label for="progres-task-{{ t.assignment.pk }}">Kemajuan</label>
            <input id="progres-task-{{ t.assignment.pk }}" name="catatan" required placeholder="Mis. vendor dihubungi, datang Senin">
            {% foto_input "Foto (opsional)" "foto" %}
            <button class="btn small" type="submit">Simpan progres</button>
          </form>
        </details>
        <details class="task-submit">
          <summary class="btn small">Ajukan selesai</summary>
          <form method="post" data-jejak action="{% url 'core:assignment_submit' t.assignment.pk %}" enctype="multipart/form-data" class="stack-form">
            {% csrf_token %}<input type="hidden" name="next" value="{{ request.get_full_path }}">
            <label for="catatan-task-{{ t.assignment.pk }}">Catatan bukti</label>
            <input id="catatan-task-{{ t.assignment.pk }}" name="catatan" required placeholder="Mis. limbah sudah ditimbang 2,4 kg">
            {% foto_input "Foto bukti (opsional)" "foto" %}
            <button class="btn small" type="submit">Kirim</button>
          </form>
        </details>
        <details class="task-submit">
          <summary class="btn small secondary">Ada kendala</summary>
          <form method="post" action="{% url 'core:assignment_blocker' t.assignment.pk %}" class="stack-form">
            {% csrf_token %}<input type="hidden" name="next" value="{{ request.get_full_path }}">
            <label for="kendala-task-{{ t.assignment.pk }}">Kendala</label>
            <input id="kendala-task-{{ t.assignment.pk }}" name="alasan" required placeholder="Mis. vendor baru bisa datang Jumat">
            <label for="target-task-{{ t.assignment.pk }}">Usulan target baru <span class="meta">(opsional)</span></label>
            <input id="target-task-{{ t.assignment.pk }}" type="date" name="target" min="{% now 'Y-m-d' %}">
            <button class="btn small" type="submit">Kirim kendala</button>
          </form>
        </details>
        {% endif %}
        {% if t.assignment %}
        <details class="task-submit">
          <summary class="btn small secondary">Percakapan ({{ t.thread_count }})</summary>
          <div class="stack-form">
            {% if t.thread %}
            <ul class="timeline">
              {% for e in t.thread %}<li><strong>{{ e.actor|default:"Sistem" }}</strong> <span class="meta">{{ e.created_at|date:"d/m H.i" }} · {{ e.get_event_type_display }}</span><div style="white-space:pre-wrap">{{ e.note }}</div></li>{% endfor %}
            </ul>
            {% else %}<p class="meta">Belum ada percakapan.</p>{% endif %}
            <form method="post" action="{% url 'core:task_comment' t.item.pk %}" class="stack-form">
              {% csrf_token %}<input type="hidden" name="next" value="{{ request.get_full_path }}">
              <label for="balas-task-{{ t.item.pk }}">Balas</label>
              <input id="balas-task-{{ t.item.pk }}" name="catatan" required placeholder="Mis. vendor minta DP dulu, boleh?">
              <button class="btn small" type="submit">Kirim</button>
            </form>
          </div>
        </details>
        {% endif %}
        </span>
```

(c) Di `<span class="request-state">`, sebelum `{% if t.overdue %}`, tambahkan:
`{% if t.blocked %}<span class="tag warn">Terhambat</span>{% endif %}`.

- [ ] **Step 6: Jalankan test**

Run: `.venv/bin/python -m pytest core`
Expected: semua PASS (termasuk `core/tests/test_tugas_saya.py`).

---

### Task 3: Tampilan Direktur — kotak Terhambat, label, Ringkasan

**Files:**
- Modify: `direktur/views.py` (`task_detail`)
- Modify: `templates/direktur/task_detail.html`, `templates/direktur/task_list.html`, `templates/direktur/team.html`, `templates/direktur/_overview_body.html`
- Modify: `direktur/dashboard.py` (`headline_counts`)
- Create: `direktur/tests/test_task_terhambat.py`

**Interfaces:**
- Consumes: `task_services.approve_proposed_due`, `report_blocker`, `ActionItem.is_blocked` (Task 1).
- Produces: POST `aksi=setujui_target` pada `direktur:task_detail`; `headline_counts()["blocked"]`.

- [ ] **Step 1: Tulis test yang gagal**

Buat `direktur/tests/test_task_terhambat.py`:

```python
"""Task terhambat di tampilan Direktur (tahap 3a, 7 Okt 2026)."""
import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core import task_services as ts
from core.models import ActionItem, Clinic, TaskAudienceType, local_today

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.STAF, display_name="Desy")


def _blocked(hansen, jemur, desy, days=3):
    item = ts.create_task(clinic=jemur, actor=hansen, title="Ganti filter AC", audience_type=TaskAudienceType.USER,
                          user_ids=[desy.pk])
    ts.report_blocker(item.task_assignments.get(), user=desy, reason="Vendor baru bisa Jumat",
                      proposed_due=local_today() + dt.timedelta(days=days))
    return ActionItem.objects.get(pk=item.pk)


def test_detail_shows_box_and_approves(client, jemur, hansen, desy):
    item = _blocked(hansen, jemur, desy)
    client.force_login(hansen)
    url = reverse("direktur:task_detail", args=[item.pk])
    body = client.get(url).content.decode()
    target = (local_today() + dt.timedelta(days=3)).strftime("%d/%m/%Y")
    assert "Terhambat" in body and "Vendor baru bisa Jumat" in body and f"Setujui target {target}" in body
    client.post(url, {"aksi": "setujui_target"})
    item.refresh_from_db()
    assert not item.is_blocked and item.due_at is not None
    assert "Setujui target" not in client.get(url).content.decode()


def test_staff_cannot_open_director_detail(client, jemur, hansen, desy):
    item = _blocked(hansen, jemur, desy)
    client.force_login(desy)
    assert client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "setujui_target"}).status_code == 403
    assert ActionItem.objects.get(pk=item.pk).is_blocked


def test_list_team_and_overview_show_blocked(client, jemur, hansen, desy):
    item = _blocked(hansen, jemur, desy)
    client.force_login(hansen)
    assert "Terhambat" in client.get(reverse("direktur:tasks")).content.decode()
    assert "Terhambat" in client.get(reverse("direktur:team")).content.decode()
    assert "1 task terhambat" in client.get(reverse("direktur:overview")).content.decode()
    ts.report_progress(item.task_assignments.get(), user=desy, note="Vendor datang")
    assert "task terhambat" not in client.get(reverse("direktur:overview")).content.decode()
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest direktur/tests/test_task_terhambat.py`
Expected: FAIL (teks "Setujui target", "task terhambat" tidak ada).

- [ ] **Step 3: View**

Di `direktur/views.py` `task_detail`, dalam rantai `elif` sesudah `elif not can_manage: raise PermissionDenied(...)`, tambahkan cabang:

```python
            elif aksi == "setujui_target":
                task_services.approve_proposed_due(item, actor=request.user)
                messages.success(request, "Target baru disetujui; penerima diberi tahu.")
```

Pastikan context `render` memuat `"can_manage": can_manage` (tambahkan bila belum ada).

- [ ] **Step 4: Template detail task**

Di `templates/direktur/task_detail.html`:
- Di dalam paragraf tag status (baris `<p>` pertama sesudah `<h1>`), tambahkan sebelum `</p>`:
  `{% if item.is_blocked %}<span class="tag warn">Terhambat</span>{% endif %}`
- Sesudah paragraf tag itu (sebelum `{% if item.description %}`), tambahkan:

```html
{% if item.is_blocked %}
<div class="card" style="border-left:4px solid var(--warn)">
  <strong>Terhambat</strong> <span class="meta">· {{ item.blocked_by|default:"penerima" }} · {{ item.blocked_at|date:"d/m/Y H:i" }}</span>
  <div style="white-space:pre-wrap">{{ item.blocked_reason }}</div>
  {% if item.proposed_due_at %}
  <p class="meta" style="margin:.3rem 0">Usulan target baru: <strong>{{ item.proposed_due_at|date:"d/m/Y H:i" }}</strong></p>
  {% if can_manage %}<form method="post">{% csrf_token %}<input type="hidden" name="aksi" value="setujui_target">
    <button class="btn small" type="submit">Setujui target {{ item.proposed_due_at|date:"d/m/Y" }}</button></form>{% endif %}
  {% endif %}
  <p class="meta" style="margin:.3rem 0 0">Balas lewat "Simpan catatan" di bawah; penerima diberi tahu.</p>
</div>
{% endif %}
```

- [ ] **Step 5: Label di Daftar Task dan Tim**

- `templates/direktur/task_list.html` sel Status: sesudah `{% if r.on_hold %} <span class="tag info">Menunggu keputusan</span>{% endif %}` tambahkan `{% if r.item.is_blocked %} <span class="tag warn">Terhambat</span>{% endif %}`.
- `templates/direktur/team.html` baris task terbuka per orang (yang memuat `a.action_item.is_overdue`): sesudah `{% if a.action_item.is_overdue %} <span class="tag err">Lewat</span>{% endif %}` tambahkan `{% if a.action_item.is_blocked %} <span class="tag warn">Terhambat</span>{% endif %}`.

- [ ] **Step 6: Ringkasan**

Di `direktur/dashboard.py` `headline_counts`, tambahkan ke dict yang dikembalikan:

```python
        "blocked": sum(1 for i in open_items if i.blocked_at is not None),
```

Di `templates/direktur/_overview_body.html`, pada paragraf `<p class="meta">{{ counts.open }} task terbuka…`, sisipkan sesudah blok `counts.overdue`:

```html
{% if counts.blocked %} · <a class="tag warn" href="{% url 'direktur:tasks' %}">{{ counts.blocked }} task terhambat</a>{% endif %}
```

- [ ] **Step 7: Jalankan test**

Run: `.venv/bin/python -m pytest direktur owner core`
Expected: semua PASS.

---

### Task 4: Dokumentasi

**Files:**
- Modify: `docs/panduan-staf.md`, `docs/panduan-direktur.md`, `docs/peran-dan-akses.md`, `README.md` (bila hitungan test perlu)

- [ ] **Step 1:** `grep -n -i "lapor progres\|tugas saya\|catatan di riwayat\|simpan catatan" docs/panduan-staf.md docs/panduan-direktur.md docs/peran-dan-akses.md`
- [ ] **Step 2:** Perbarui:
  - `docs/panduan-staf.md` (bagian Tugas saya): Lapor progres kini sampai ke pemberi tugas dan Direktur; **Percakapan (n)** untuk membaca catatan Direktur dan membalas; **Ada kendala** dengan alasan wajib dan usulan target opsional, label Terhambat, hilang saat lapor progres atau target disetujui.
  - `docs/panduan-direktur.md`: notifikasi Progres/Balasan/Kendala untuk semua Direktur dan pemberi tugas; kotak Terhambat di detail task dengan tombol "Setujui target"; "Simpan catatan" kini memberi notifikasi ke penerima; label Terhambat di Daftar Task dan Tim; "n task terhambat" di Ringkasan.
  - `docs/peran-dan-akses.md`: baris "Lapor kendala (terhambat) dan membalas percakapan task | penerima task | —" dan "Menyetujui usulan target baru | pemberi tugas, AOM | —".
- [ ] **Step 3:** `.venv/bin/python -m pytest core/tests/test_documentation.py`; bila tes hitungan README gagal, perbarui angka `pytest  # NNN test dijalankan` di `README.md` ke jumlah hasil run penuh.

---

### Task 5: Verifikasi menyeluruh, uji UI, laporan (controller)

- [ ] Seluruh test lulus; `manage.py check` bersih; `makemigrations --check --dry-run` tidak ada perubahan.
- [ ] Salin `~/joderma-operasional/data/uitest.sqlite3` ke worktree `data/`, migrate (`core.0009` OK).
- [ ] Uji UI desktop dan HP 375 px: progres → Direktur diberi tahu; kendala + usulan target → label di Daftar Task, Tim, Ringkasan → Direktur setujui → staf diberi tahu, label hilang; Direktur menulis catatan → staf diberi tahu → Percakapan → balas → Direktur diberi tahu.
- [ ] Laporkan ke product owner dan **berhenti sampai disetujui**; lalu commit di `tahap3a`, merge ke `master`, push, deploy hanya atas izin.
