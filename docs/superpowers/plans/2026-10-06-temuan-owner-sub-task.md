# Temuan Owner: task besar dan sub task — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Temuan Owner menjadi task besar dengan sub task, batas target 3/30 hari menurut tanda mendesak, sub task Direktur tanpa verifikasi, dan penutupan temuan oleh Direktur yang terlihat di dashboard Owner.

**Architecture:** Tidak ada tingkat baru di `core.ActionItem`. `owner.OwnerRequest` mendapat tiga kolom (`plan_title`, `completed_at`, `completed_by`); aturan target, status, dan penutupan ada di `owner/services.py`. Di `core`, satu properti `ActionItem.is_temuan_subtask` mengubah `effective_review_by` dan `submit_assignment` hanya untuk sub task temuan.

**Tech Stack:** Django 5.1, Python 3.11 (venv `.venv`), pytest + pytest-django, template Django tanpa JS framework.

**Spec:** `docs/superpowers/specs/2026-10-06-temuan-owner-sub-task-design.md`

## Global Constraints

- Kerja di WSL `~/joderma-operasional`. Semua perintah dijalankan dari direktori itu dengan `.venv/bin/python` (Python 3.11). Jangan memakai `python3` sistem.
- Database pengembangan saja (`data/db.sqlite3`); jangan menyentuh mini PC atau database produksi.
- **Jangan commit atau push sebelum product owner meninjau bukti pengujian** (AGENTS.md). Setiap task diakhiri dengan pemeriksaan `git diff`, bukan commit. Commit tunggal ada di Task 7 setelah persetujuan.
- Otorisasi di service (server-side); menyembunyikan tombol bukan kontrol akses.
- Hanya temuan (`RequestKind.TEMUAN`). Permintaan Owner dan task dari modul lain tidak berubah perilakunya.
- Batas: mendesak = tanggal catat + 3 hari; tidak mendesak = tanggal catat + 30 hari.
- Label status temuan persis: "Menunggu Direktur", "Berjalan", "Siap ditutup", "Selesai & terverifikasi".
- Label status sub task persis: "Berjalan", "Menunggu verifikasi", "Terverifikasi Direktur", "Selesai oleh Direktur".
- Teks antarmuka dan komentar berbahasa Indonesia, mengikuti gaya file sekitarnya.
- Jalankan `pytest` sebagai perintah tersendiri, tidak dirangkai `&&` sesudah `pip install`.

---

## File Structure

| File | Tanggung jawab |
|---|---|
| `owner/models.py` | Kolom baru `plan_title`, `completed_at`, `completed_by` |
| `owner/migrations/0003_rencana_temuan.py` | Migrasi additive (dibuat `makemigrations`) |
| `owner/services.py` | Batas target, target efektif, status temuan, `set_plan`, `complete_finding`, `subtask_rows`, urutan daftar |
| `owner/views.py` | Form temuan tanpa target; aksi `rencana` dan `selesai` di detail |
| `core/models.py` | `ActionItem.is_temuan_subtask`; `effective_review_by` |
| `core/task_services.py` | Konfirmasi otomatis sub task Direktur pada temuan; helper penyelesaian item dipakai bersama |
| `templates/owner/request_form.html` | Kolom target hanya untuk Permintaan |
| `templates/owner/request_detail.html` | Rencana, daftar sub task, tombol selesai |
| `templates/owner/dashboard.html`, `templates/owner/_request_state.html` | Baris temuan: target efektif, status baru, hasil |
| `owner/tests/test_temuan_rencana.py` | Test baru untuk seluruh fitur |
| `reports/tests/test_inbox_pilah.py` | Satu test lama disesuaikan (temuan mendesak kini bertarget) |
| `docs/panduan-owner.md`, `docs/panduan-direktur.md`, `docs/peran-dan-akses.md`, `current-progress.md` | Dokumentasi |

---

### Task 1: Kolom baru dan batas target saat temuan dibuat

**Files:**
- Modify: `owner/models.py` (class `OwnerRequest`)
- Create: `owner/migrations/0003_rencana_temuan.py` (via makemigrations)
- Modify: `owner/services.py` (konstanta, helper tanggal, `create_request`)
- Modify: `owner/views.py:68-98` (`request_new`)
- Modify: `templates/owner/request_form.html`
- Modify: `reports/tests/test_inbox_pilah.py:68-74`
- Create: `owner/tests/test_temuan_rencana.py`

**Interfaces:**
- Produces: `services.URGENT_DAYS = 3`, `services.NORMAL_DAYS = 30`, `services.recorded_on(req) -> dt.date`, `services.deadline_cap(req) -> dt.date | None` (None untuk Permintaan), `services.effective_target(req) -> dt.date | None`. Kolom `OwnerRequest.plan_title: str`, `completed_at: datetime | None`, `completed_by: User | None`.

- [ ] **Step 1: Tulis test yang gagal**

Buat `owner/tests/test_temuan_rencana.py`:

```python
"""Temuan Owner sebagai task besar: batas target, sub task, penutupan oleh Direktur (6 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import ActionItem, ActionItemStatus, Clinic, TaskAssignmentStatus, local_today
from notifications.models import Notification
from owner import services
from owner.models import OwnerRequest, RequestKind

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password=PASSWORD, **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani", open_time="14:00", close_time="22:00")


@pytest.fixture
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def desy(jemur):
    return _user(jemur, "desy", Role.PIC, Role.FRONT_DESK, display_name="Desy")


def _temuan(owner, urgent=False, title="Alur pasien baru belum seragam", **kw):
    return services.create_request(actor=owner, kind=RequestKind.TEMUAN, title=title, urgent=urgent, **kw)


def _age(req, days):
    """Mundurkan tanggal catat temuan `days` hari."""
    OwnerRequest.objects.filter(pk=req.pk).update(created_at=timezone.now() - dt.timedelta(days=days))
    req.refresh_from_db()
    return req


# --- Task 1: batas target saat dibuat ------------------------------------------


def test_urgent_finding_gets_three_day_target(yohanes):
    req = _temuan(yohanes, urgent=True)
    assert req.target_date == local_today() + dt.timedelta(days=3)
    assert services.deadline_cap(req) == local_today() + dt.timedelta(days=3)


def test_normal_finding_has_no_target_but_thirty_day_cap(yohanes):
    req = _temuan(yohanes)
    assert req.target_date is None
    assert services.deadline_cap(req) == local_today() + dt.timedelta(days=30)
    assert services.effective_target(req) == local_today() + dt.timedelta(days=30)


def test_cap_counts_from_recorded_date(yohanes):
    req = _age(_temuan(yohanes), 10)
    assert services.recorded_on(req) == local_today() - dt.timedelta(days=10)
    assert services.deadline_cap(req) == local_today() + dt.timedelta(days=20)


def test_finding_target_beyond_cap_is_rejected(yohanes):
    with pytest.raises(ValidationError, match="paling lambat"):
        _temuan(yohanes, target_date=local_today() + dt.timedelta(days=31))
    assert not OwnerRequest.objects.exists()


def test_request_has_no_cap(yohanes):
    req = services.create_request(actor=yohanes, title="Evaluasi paket", target_date=local_today() + dt.timedelta(days=90))
    assert services.deadline_cap(req) is None
    assert services.effective_target(req) == req.target_date


def test_finding_form_has_no_target_field(client, yohanes):
    client.force_login(yohanes)
    body = client.get(reverse("owner:request_new") + "?jenis=TEMUAN").content.decode()
    assert 'name="target"' not in body and "Mendesak" in body
    body = client.get(reverse("owner:request_new")).content.decode()
    assert 'name="target"' in body


def test_owner_posts_urgent_finding_without_target(client, yohanes, jemur):
    client.force_login(yohanes)
    client.post(reverse("owner:request_new"), {"jenis": "TEMUAN", "judul": "Wastafel bocor", "mendesak": "1",
                                               "target": "2099-01-01"})
    req = OwnerRequest.objects.get()
    assert req.urgent and req.target_date == local_today() + dt.timedelta(days=3)
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_temuan_rencana.py -q`
Expected: FAIL — `AttributeError: module 'owner.services' has no attribute 'deadline_cap'` dan sejenisnya.

- [ ] **Step 3: Tambah kolom model**

Di `owner/models.py`, pada `OwnerRequest` sesudah `urgent`:

```python
    plan_title = models.CharField(
        "task besar", max_length=200, blank=True,
        help_text="Nama penanganan temuan dari Direktur, mis. 'Membuat alur untuk temuan X'.",
    )
    completed_at = models.DateTimeField("dinyatakan selesai", null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
```

Lalu buat migrasi:

Run: `.venv/bin/python manage.py makemigrations owner --name rencana_temuan`
Expected: `owner/migrations/0003_rencana_temuan.py` dengan tiga `AddField`.

- [ ] **Step 4: Helper tanggal dan batas di `create_request`**

Di `owner/services.py`, tambahkan import `from django.utils import timezone` dan sesudah `TITLE_MAX = 200`:

```python
URGENT_DAYS = 3
NORMAL_DAYS = 30
```

Tambahkan di bagian `# --- Permintaan ---` (sebelum `create_request`):

```python
def _cap_from(day: dt.date, urgent: bool) -> dt.date:
    return day + dt.timedelta(days=URGENT_DAYS if urgent else NORMAL_DAYS)


def recorded_on(req: OwnerRequest) -> dt.date:
    """Tanggal temuan dicatat, menurut zona waktu klinik."""
    return timezone.localtime(req.created_at).date() if req.created_at else local_today()


def deadline_cap(req: OwnerRequest) -> dt.date | None:
    """Batas target temuan: 3 hari bila mendesak, 30 hari bila tidak. Permintaan tidak berbatas."""
    if req.kind != RequestKind.TEMUAN:
        return None
    return _cap_from(recorded_on(req), req.urgent)


def effective_target(req: OwnerRequest) -> dt.date | None:
    """Target dari Direktur bila ada; untuk temuan tanpa target, batasnya."""
    return req.target_date or deadline_cap(req)
```

Di `create_request`, sisipkan tepat sebelum baris `if target_date is None and kind == RequestKind.PERMINTAAN:`:

```python
    if kind == RequestKind.TEMUAN:
        cap = _cap_from(local_today(), bool(urgent))
        if urgent and target_date is None:
            target_date = cap
        if target_date is not None and target_date > cap:
            raise ValidationError(f"Target temuan paling lambat {cap:%d/%m/%Y}.")
```

- [ ] **Step 5: Form temuan tanpa target**

Di `owner/views.py` `request_new`, ganti argumen

```python
                    target_date=services.parse_target(form["target"], required=not temuan),
```

dengan

```python
                    target_date=None if temuan else services.parse_target(form["target"]),
```

Di `templates/owner/request_form.html`, bungkus blok kolom target:

```html
    {% if not temuan %}<div><label for="target">Target selesai</label>
      <input id="target" type="date" name="target" required min="{{ today|date:'Y-m-d' }}" value="{{ form.target }}"></div>{% endif %}
```

dan ganti paragraf bantuan menjadi:

```html
  <p class="help">{% if temuan %}Mendesak: dibereskan paling lambat 3 hari. Tidak mendesak: Direktur Operasional menentukan target, paling lambat 1 bulan.{% else %}Bila target perlu diubah atau tidak terpenuhi, Direktur membicarakannya langsung dengan Anda atau menulis catatan.{% endif %}</p>
```

- [ ] **Step 6: Sesuaikan test Inbox lama**

Di `reports/tests/test_inbox_pilah.py` `test_owner_finding_without_target_reaches_inbox`, ganti

```python
    assert finding.target_date is None and progress(finding)["late"] is False
```

dengan

```python
    assert finding.target_date == local_today() + dt.timedelta(days=3) and progress(finding)["late"] is False
```

Pastikan `dt` dan `local_today` sudah diimpor di file itu; bila belum, tambahkan `import datetime as dt` dan `from core.models import local_today`.

- [ ] **Step 7: Jalankan test**

Run: `.venv/bin/python -m pytest owner/tests/test_temuan_rencana.py reports/tests/test_inbox_pilah.py owner/tests/test_owner.py -q`
Expected: semua PASS.

- [ ] **Step 8: Tinjau diff (tanpa commit)**

Run: `git diff --stat` dan `git status --short`
Expected: hanya file di daftar Task 1 ditambah migrasi baru.

---

### Task 2: Status temuan, rencana Direktur, dan penutupan

**Files:**
- Modify: `owner/services.py` (`progress`, `request_rows`, fungsi baru `set_plan`, `complete_finding`)
- Test: `owner/tests/test_temuan_rencana.py`

**Interfaces:**
- Consumes: `deadline_cap`, `effective_target`, `recorded_on` (Task 1).
- Produces: `services.set_plan(req, *, actor, plan_title: str, target_date: dt.date | None) -> OwnerRequest`; `services.complete_finding(req, *, actor) -> OwnerRequest`; `progress()` mengembalikan kunci tambahan `target` (date|None), `target_set` (bool), `finished_late_by` (int), dan `state` baru `"ready"`.

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan ke `owner/tests/test_temuan_rencana.py`:

```python
# --- Task 2: status, rencana, penutupan ------------------------------------------


def _sub(req, clinic, status=ActionItemStatus.BARU, title="Sub task"):
    return ActionItem.objects.create(clinic=clinic, title=title, source_type="permintaan_owner", source_id=req.pk,
                                     status=status)


def test_finding_states(jemur, yohanes, hansen):
    req = _temuan(yohanes)
    assert (services.progress(req)["state"], services.progress(req)["label"]) == ("waiting", "Menunggu Direktur")
    a = _sub(req, jemur)
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    assert services.progress(req)["label"] == "Berjalan"
    a.status = ActionItemStatus.SELESAI
    a.save()
    row = services.progress(req)
    assert (row["state"], row["label"]) == ("ready", "Siap ditutup")
    services.complete_finding(req, actor=hansen)
    row = services.progress(req)
    assert (row["state"], row["label"], row["finished_late_by"]) == ("done", "Selesai & terverifikasi", 0)


def test_request_still_done_automatically(jemur, yohanes):
    req = services.create_request(actor=yohanes, title="Evaluasi paket", target_date=local_today() + dt.timedelta(days=5))
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    assert services.progress(req)["label"] == "Selesai"


def test_late_uses_effective_target(yohanes):
    req = _age(_temuan(yohanes), 32)  # batas 30 hari lewat 2 hari
    row = services.progress(req)
    assert row["late"] and row["days_late"] == 2 and not row["target_set"]
    assert row["target"] == local_today() - dt.timedelta(days=2)


def test_complete_rejected_without_or_with_open_subtasks(jemur, yohanes, hansen):
    req = _temuan(yohanes)
    with pytest.raises(ValidationError, match="belum punya sub task"):
        services.complete_finding(req, actor=hansen)
    _sub(req, jemur)
    with pytest.raises(ValidationError, match="belum selesai"):
        services.complete_finding(req, actor=hansen)
    req.refresh_from_db()
    assert req.completed_at is None


def test_only_director_completes_and_owner_is_notified(jemur, yohanes, hansen, desy):
    req = _temuan(yohanes)
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    for user in (yohanes, desy):
        with pytest.raises(PermissionDenied):
            services.complete_finding(req, actor=user)
    services.complete_finding(req, actor=hansen)
    req.refresh_from_db()
    assert req.completed_by == hansen and req.completed_at is not None
    assert Notification.objects.filter(user=yohanes, title__startswith="Temuan selesai").exists()
    with pytest.raises(ValidationError, match="sudah dinyatakan selesai"):
        services.complete_finding(req, actor=hansen)


def test_completed_late_is_reported(jemur, yohanes, hansen):
    req = _age(_temuan(yohanes, urgent=True), 5)  # target = catat + 3 = 2 hari lalu
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    services.complete_finding(req, actor=hansen)
    assert services.progress(req)["finished_late_by"] == 2


def test_set_plan_limits(yohanes, hansen):
    req = _temuan(yohanes)
    services.set_plan(req, actor=hansen, plan_title="Membuat alur pasien baru",
                      target_date=local_today() + dt.timedelta(days=14))
    req.refresh_from_db()
    assert req.plan_title == "Membuat alur pasien baru" and req.target_date == local_today() + dt.timedelta(days=14)
    with pytest.raises(ValidationError, match="paling lambat"):
        services.set_plan(req, actor=hansen, plan_title="", target_date=local_today() + dt.timedelta(days=31))
    with pytest.raises(ValidationError, match="sebelum hari ini"):
        services.set_plan(req, actor=hansen, plan_title="", target_date=local_today() - dt.timedelta(days=1))
    with pytest.raises(PermissionDenied):
        services.set_plan(req, actor=yohanes, plan_title="X", target_date=None)


def test_urgent_plan_cannot_exceed_three_days_or_drop_target(yohanes, hansen):
    req = _temuan(yohanes, urgent=True)
    with pytest.raises(ValidationError, match="paling lambat"):
        services.set_plan(req, actor=hansen, plan_title="", target_date=local_today() + dt.timedelta(days=4))
    services.set_plan(req, actor=hansen, plan_title="Bereskan", target_date=None)
    req.refresh_from_db()
    assert req.target_date == local_today() + dt.timedelta(days=3)
    services.set_plan(req, actor=hansen, plan_title="", target_date=local_today() + dt.timedelta(days=1))
    req.refresh_from_db()
    assert req.target_date == local_today() + dt.timedelta(days=1)


def test_unchanged_past_target_does_not_block_plan_title(yohanes, hansen):
    req = _age(_temuan(yohanes, urgent=True), 5)
    services.set_plan(req, actor=hansen, plan_title="Alur baru", target_date=req.target_date)
    req.refresh_from_db()
    assert req.plan_title == "Alur baru"


def test_urgent_open_findings_listed_first(jemur, yohanes, hansen):
    late = services.create_request(actor=yohanes, title="Lewat", target_date=local_today() + dt.timedelta(days=1))
    OwnerRequest.objects.filter(pk=late.pk).update(target_date=local_today() - dt.timedelta(days=1))
    normal = _temuan(yohanes, title="Biasa")
    urgent = _temuan(yohanes, urgent=True, title="Mendesak")
    done_urgent = _temuan(yohanes, urgent=True, title="Mendesak selesai")
    _sub(done_urgent, jemur, status=ActionItemStatus.SELESAI)
    services.complete_finding(done_urgent, actor=hansen)
    order = [r["request"].pk for r in services.request_rows(yohanes)]
    assert order == [urgent.pk, late.pk, normal.pk, done_urgent.pk]
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_temuan_rencana.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'complete_finding'` dan `KeyError: 'target_set'`.

- [ ] **Step 3: Ganti `progress` dan `request_rows`**

Di `owner/services.py`, ganti seluruh fungsi `progress` dengan:

```python
def progress(req: OwnerRequest, today: dt.date | None = None) -> dict:
    """Status permintaan/temuan dari task turunannya.

    Permintaan selesai otomatis bila semua task selesai. Temuan baru selesai bila Direktur
    menyatakannya (`complete_finding`); sebelum itu, semua sub task selesai = "Siap ditutup".
    """
    today = today or local_today()
    tasks = list(req.tasks())
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == ActionItemStatus.SELESAI)
    temuan = req.kind == RequestKind.TEMUAN
    if temuan and req.completed_at:
        state, label = "done", "Selesai & terverifikasi"
    elif total == 0:
        state, label = "waiting", "Menunggu Direktur"
    elif done == total:
        state, label = ("ready", "Siap ditutup") if temuan else ("done", "Selesai")
    else:
        state, label = "running", "Berjalan"
    target = effective_target(req)
    late = state != "done" and target is not None and target < today
    finished_on = timezone.localtime(req.completed_at).date() if req.completed_at else None
    return {
        "request": req,
        "tasks": tasks,
        "total": total,
        "done": done,
        "percent": round(done * 100 / total) if total else 0,
        "state": state,
        "label": label,
        "late": late,
        "target": target,
        "target_set": req.target_date is not None,
        "days_left": (target - today).days if target else None,
        "days_late": max(0, (today - target).days) if target else 0,
        "finished_late_by": max(0, (finished_on - target).days) if finished_on and target else 0,
    }
```

Di `request_rows`, ganti dua baris pengurutan

```python
    order = {"waiting": 1, "running": 1, "done": 2}
    far = dt.date.max
    rows.sort(key=lambda r: (not r["late"], order[r["state"]], r["request"].target_date or far))
```

dengan

```python
    order = {"waiting": 1, "running": 1, "ready": 1, "done": 2}
    far = dt.date.max
    rows.sort(key=lambda r: (
        not (r["request"].urgent and r["state"] != "done"), not r["late"], order[r["state"]], r["target"] or far,
    ))
```

- [ ] **Step 4: Tambah `set_plan` dan `complete_finding`**

Di `owner/services.py`, ubah import audit menjadi
`from audit.services import log_create, log_event, log_update, snapshot`, lalu tambahkan sesudah `add_note`:

```python
@transaction.atomic
def set_plan(req: OwnerRequest, *, actor, plan_title: str, target_date: dt.date | None) -> OwnerRequest:
    """Direktur memberi nama task besar dan target, dalam batas 3/30 hari sejak temuan dicatat."""
    if not is_aom(actor):
        raise PermissionDenied("Hanya Direktur Operasional yang menyusun rencana penanganan.")
    if req.kind != RequestKind.TEMUAN:
        raise ValidationError("Rencana penanganan hanya untuk temuan.")
    if req.completed_at:
        raise ValidationError("Temuan ini sudah dinyatakan selesai.")
    plan_title = (plan_title or "").strip()
    if len(plan_title) > TITLE_MAX:
        raise ValidationError(f"Nama task besar terlalu panjang (maks. {TITLE_MAX} karakter).")
    cap = deadline_cap(req)
    if target_date is None and req.urgent:
        target_date = cap  # temuan mendesak selalu bertanggal
    if target_date is not None and target_date != req.target_date:
        if target_date < local_today():
            raise ValidationError("Tanggal target tidak boleh sebelum hari ini.")
        if target_date > cap:
            reason = "mendesak, 3 hari" if req.urgent else "1 bulan"
            raise ValidationError(f"Target paling lambat {cap:%d/%m/%Y} ({reason} sejak temuan dicatat).")
    before = snapshot(req)
    req.plan_title = plan_title
    req.target_date = target_date
    req.save(update_fields=["plan_title", "target_date", "updated_at"])
    log_update(req, before, actor=actor)
    return req


@transaction.atomic
def complete_finding(req: OwnerRequest, *, actor) -> OwnerRequest:
    """Direktur menyatakan temuan selesai & terverifikasi. Tidak pernah otomatis."""
    if not is_aom(actor):
        raise PermissionDenied("Hanya Direktur Operasional yang menyatakan temuan selesai.")
    if req.kind != RequestKind.TEMUAN:
        raise ValidationError("Hanya temuan yang dinyatakan selesai oleh Direktur.")
    if req.completed_at:
        raise ValidationError("Temuan ini sudah dinyatakan selesai.")
    tasks = list(req.tasks())
    if not tasks:
        raise ValidationError("Temuan belum punya sub task.")
    if any(t.status != ActionItemStatus.SELESAI for t in tasks):
        raise ValidationError("Masih ada sub task yang belum selesai.")
    req.completed_at = timezone.now()
    req.completed_by = actor
    req.save(update_fields=["completed_at", "completed_by", "updated_at"])
    log_event(action=AuditAction.UPDATE, entity_type="ownerrequest", entity_id=req.pk, entity_label=req.title,
              actor=actor, after={"completed_at": req.completed_at.isoformat(), "completed_by": actor.pk})
    _notify(_owners(), actor=actor, request=req, title=f"Temuan selesai & terverifikasi: {req.title}",
            body=f"oleh {actor}")
    return req
```

Periksa tanda tangan `log_update` di `audit/services.py:101`; bila urutan argumennya bukan `(instance, before, *, actor)`, sesuaikan pemanggilan di atas agar cocok.

- [ ] **Step 5: Jalankan test**

Run: `.venv/bin/python -m pytest owner reports direktur -q`
Expected: semua PASS (Inbox memakai `progress()`; "Siap ditutup" tetap dihitung terbuka karena `state != "done"`).

- [ ] **Step 6: Tinjau diff (tanpa commit)**

Run: `git diff owner/services.py`

---

### Task 3: Verifikasi sub task temuan di `core`

**Files:**
- Modify: `core/models.py` (class `ActionItem`: properti baru, `effective_review_by`)
- Modify: `core/task_services.py` (`submit_assignment`, `confirm_assignment`, helper baru)
- Test: `owner/tests/test_temuan_rencana.py`

**Interfaces:**
- Produces: `ActionItem.is_temuan_subtask -> bool` (cached per instance); `core.task_services._finish_item_if_all_confirmed(item: ActionItem) -> None`.
- Consumes: `direktur.services.create_task_from_source(*, actor, clinic, title, target, ..., source_type, source_id, source_label)` dengan `target="user:<id>"`.

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan ke `owner/tests/test_temuan_rencana.py`:

```python
# --- Task 3: verifikasi sub task ---------------------------------------------------


def _assigned(req, actor, clinic, person, title="Sub task", source_type="permintaan_owner"):
    from direktur.services import create_task_from_source

    return create_task_from_source(actor=actor, clinic=clinic, title=title, target=f"user:{person.pk}",
                                   source_type=source_type, source_id=req.pk)


def test_director_subtask_on_finding_completes_without_review(jemur, yohanes, hansen):
    from core.task_services import submit_assignment

    req = _temuan(yohanes)
    item = _assigned(req, hansen, jemur, hansen, title="Menulis alur tertulis")
    assert item.is_temuan_subtask and item.effective_review_by == "DIREKTUR"
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=hansen, note="Alur sudah ditulis")
    assignment.refresh_from_db()
    item.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.CONFIRMED and assignment.reviewer is None
    assert item.status == ActionItemStatus.SELESAI
    assert item.task_events.filter(note__contains="tanpa verifikasi").exists()
    assert not Notification.objects.filter(user=yohanes, title__startswith="Menunggu verifikasi").exists()


def test_staff_subtask_on_finding_is_reviewed_by_director_not_owner(jemur, yohanes, hansen, desy):
    from core.task_services import can_review_assignment, confirm_assignment, submit_assignment

    req = _temuan(yohanes)
    item = _assigned(req, hansen, jemur, desy, title="Sosialisasi alur ke rekan shift")
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=desy, note="Sudah disosialisasikan")
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED
    assert can_review_assignment(assignment, hansen) and not can_review_assignment(assignment, yohanes)
    assert services.verification_queue(yohanes) == []
    confirm_assignment(assignment, reviewer=hansen)
    item.refresh_from_db()
    assert item.status == ActionItemStatus.SELESAI


def test_mixed_subtask_on_finding_stays_with_director(jemur, yohanes, hansen, desy):
    from core.task_services import create_task

    req = _temuan(yohanes)
    item = create_task(clinic=jemur, actor=hansen, title="Evaluasi bersama", audience_type="USER",
                       user_ids=[hansen.pk, desy.pk], source_type="permintaan_owner", source_id=req.pk)
    assert item.effective_review_by == "DIREKTUR" and not item.reviewed_by_dirut


def test_director_task_outside_finding_still_reviewed_by_owner(jemur, yohanes, hansen):
    from core.task_services import submit_assignment

    req = services.create_request(actor=yohanes, title="Evaluasi paket", target_date=local_today() + dt.timedelta(days=5))
    item = _assigned(req, hansen, jemur, hansen, title="Hitung ulang harga")
    assert not item.is_temuan_subtask and item.reviewed_by_dirut
    assignment = item.task_assignments.get()
    submit_assignment(assignment, user=hansen)
    assignment.refresh_from_db()
    assert assignment.status == TaskAssignmentStatus.SUBMITTED
```

Sebelum menjalankan, periksa nilai `TaskAudienceType.USER` di `core/models.py` (`class TaskAudienceType`); bila nilainya bukan `"USER"`, ganti string `audience_type="USER"` di test dengan `TaskAudienceType.USER` (impor dari `core.models`).

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_temuan_rencana.py -q -k "subtask or finding"`
Expected: FAIL — `AttributeError: 'ActionItem' object has no attribute 'is_temuan_subtask'`.

- [ ] **Step 3: Properti dan pemeriksa di `core/models.py`**

Tambahkan `from functools import cached_property` di bagian import `core/models.py`. Di class `ActionItem`, tepat sebelum `effective_review_by`:

```python
    @cached_property
    def is_temuan_subtask(self) -> bool:
        """Sub task temuan Owner: task bersumber permintaan_owner yang jenisnya TEMUAN (6 Okt 2026)."""
        if self.source_type != "permintaan_owner" or not self.source_id:
            return False
        from owner.models import OwnerRequest, RequestKind

        return OwnerRequest.objects.filter(pk=self.source_id, kind=RequestKind.TEMUAN).exists()
```

Di `effective_review_by`, tambahkan sebagai baris pertama badan fungsi (sesudah docstring):

```python
        if self.is_temuan_subtask:
            # Sub task temuan selalu diverifikasi Direktur Operasional; sub task Direktur sendiri
            # selesai tanpa verifikasi (task_services.submit_assignment).
            return ReviewBy.DIREKTUR
```

- [ ] **Step 4: Helper penyelesaian dan konfirmasi otomatis di `core/task_services.py`**

Tambahkan sebelum `confirm_assignment`:

```python
def _finish_item_if_all_confirmed(item: ActionItem) -> None:
    """Task selesai bila semua penerimanya sudah dikonfirmasi."""
    if not item.task_assignments.exclude(status=TaskAssignmentStatus.CONFIRMED).exists():
        item.status = ActionItemStatus.SELESAI
        item.save(update_fields=["status", "updated_at"])
```

Di `confirm_assignment`, ganti blok penutup

```python
    if not assignment.action_item.task_assignments.exclude(
        status=TaskAssignmentStatus.CONFIRMED
    ).exists():
        item = assignment.action_item
        item.status = ActionItemStatus.SELESAI
        item.save(update_fields=["status", "updated_at"])
    return assignment
```

dengan

```python
    _finish_item_if_all_confirmed(assignment.action_item)
    return assignment
```

Di `submit_assignment`, ganti baris `_notify_reviewers(assignment, actor=user, note=note)` dengan:

```python
    item = assignment.action_item
    if item.is_temuan_subtask and is_aom(user):
        # Pekerjaan Direktur sendiri pada temuan: tanpa verifikasi, tanggung jawabnya ada
        # pada pernyataan "temuan selesai" (spec 2026-10-06).
        assignment.status = TaskAssignmentStatus.CONFIRMED
        assignment.confirmed_at = timezone.now()
        assignment.save(update_fields=["status", "confirmed_at", "updated_at"])
        TaskEvent.objects.create(
            action_item=item, assignment=assignment, event_type=TaskEventType.CONFIRMED, actor=user,
            note="Selesai tanpa verifikasi (task Direktur pada temuan).",
        )
        _finish_item_if_all_confirmed(item)
        return assignment
    _notify_reviewers(assignment, actor=user, note=note)
```

- [ ] **Step 5: Jalankan test**

Run: `.venv/bin/python -m pytest owner core direktur reports -q`
Expected: semua PASS.

- [ ] **Step 6: Tinjau diff (tanpa commit)**

Run: `git diff core/`

---

### Task 4: Baris sub task untuk Owner

**Files:**
- Modify: `owner/services.py` (fungsi baru `subtask_rows`)
- Test: `owner/tests/test_temuan_rencana.py`

**Interfaces:**
- Consumes: `OwnerRequest.tasks()`, `TaskAssignment` (`status`, `assignee`, `reviewer_id`, `assignee_id`, `confirmed_at`).
- Produces: `services.subtask_rows(req) -> list[dict]` dengan kunci `task`, `state` (`running|waiting|done`), `label`, `people` (str), `finished_at` (datetime|None).

- [ ] **Step 1: Tulis test yang gagal**

```python
# --- Task 4: baris sub task --------------------------------------------------------


def test_subtask_rows_labels(jemur, yohanes, hansen, desy):
    from core.task_services import confirm_assignment, submit_assignment

    req = _temuan(yohanes)
    own = _assigned(req, hansen, jemur, hansen, title="Menulis alur")
    staff = _assigned(req, hansen, jemur, desy, title="Sosialisasi")
    labels = {r["task"].title: r["label"] for r in services.subtask_rows(req)}
    assert labels == {"Menulis alur": "Berjalan", "Sosialisasi": "Berjalan"}
    submit_assignment(own.task_assignments.get(), user=hansen)
    a = staff.task_assignments.get()
    submit_assignment(a, user=desy)
    rows = {r["task"].title: r for r in services.subtask_rows(req)}
    assert rows["Menulis alur"]["label"] == "Selesai oleh Direktur"
    assert rows["Sosialisasi"]["label"] == "Menunggu verifikasi"
    confirm_assignment(a, reviewer=hansen)
    rows = {r["task"].title: r for r in services.subtask_rows(req)}
    assert rows["Sosialisasi"]["label"] == "Terverifikasi Direktur"
    assert rows["Sosialisasi"]["people"] == str(desy) and rows["Sosialisasi"]["finished_at"] is not None
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_temuan_rencana.py -q -k subtask_rows`
Expected: FAIL — `AttributeError: ... has no attribute 'subtask_rows'`.

- [ ] **Step 3: Implementasi**

Di `owner/services.py`, sesudah `progress`:

```python
def subtask_rows(req: OwnerRequest) -> list[dict]:
    """Sub task temuan untuk Owner: siapa yang mengerjakan dan status verifikasinya."""
    from core.models import TaskAssignmentStatus

    rows = []
    for task in req.tasks().prefetch_related("task_assignments__assignee"):
        active = [a for a in task.task_assignments.all() if a.status != TaskAssignmentStatus.CANCELLED]
        confirmed = [a for a in active if a.status == TaskAssignmentStatus.CONFIRMED]
        if task.status == ActionItemStatus.SELESAI:
            self_done = any(a.reviewer_id in (None, a.assignee_id) for a in confirmed)
            state, label = "done", "Selesai oleh Direktur" if self_done else "Terverifikasi Direktur"
        elif any(a.status == TaskAssignmentStatus.SUBMITTED for a in active):
            state, label = "waiting", "Menunggu verifikasi"
        else:
            state, label = "running", "Berjalan"
        rows.append({
            "task": task,
            "state": state,
            "label": label,
            "people": ", ".join(sorted({str(a.assignee) for a in (confirmed or active)})),
            "finished_at": max((a.confirmed_at for a in confirmed if a.confirmed_at), default=None),
        })
    return rows
```

- [ ] **Step 4: Jalankan test**

Run: `.venv/bin/python -m pytest owner/tests/test_temuan_rencana.py -q`
Expected: semua PASS.

---

### Task 5: Tampilan detail dan dashboard

**Files:**
- Modify: `owner/views.py` (`request_detail`, fungsi baru `_finding_action`)
- Modify: `templates/owner/request_detail.html`
- Modify: `templates/owner/dashboard.html:24`
- Modify: `templates/owner/_request_state.html`
- Test: `owner/tests/test_temuan_rencana.py`

**Interfaces:**
- Consumes: `services.set_plan`, `services.complete_finding`, `services.subtask_rows`, `services.parse_target(raw, required=False)`, kunci `progress()` dari Task 2.
- Produces: aksi POST `aksi=rencana` (field `rencana`, `target`) dan `aksi=selesai` pada `owner:request_detail`.

- [ ] **Step 1: Tulis test yang gagal**

```python
# --- Task 5: tampilan -------------------------------------------------------------


def test_detail_shows_subtasks_and_plan_for_owner(client, jemur, yohanes, hansen, desy):
    req = _temuan(yohanes, urgent=True)
    services.set_plan(req, actor=hansen, plan_title="Membuat alur pasien baru", target_date=None)
    _assigned(req, hansen, jemur, desy, title="Sosialisasi alur")
    client.force_login(yohanes)
    body = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert "Membuat alur pasien baru" in body and "Sosialisasi alur" in body and "Desy" in body
    assert "Berjalan" in body and "Mendesak" in body
    assert 'value="rencana"' not in body and 'value="selesai"' not in body


def test_director_sets_plan_and_completes_from_page(client, jemur, yohanes, hansen):
    req = _temuan(yohanes)
    client.force_login(hansen)
    target = (local_today() + dt.timedelta(days=10)).isoformat()
    client.post(reverse("owner:request_detail", args=[req.pk]),
                {"aksi": "rencana", "rencana": "Membuat alur", "target": target})
    req.refresh_from_db()
    assert req.plan_title == "Membuat alur" and req.target_date.isoformat() == target
    body = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert 'value="selesai"' not in body  # belum ada sub task
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    body = client.get(reverse("owner:request_detail", args=[req.pk])).content.decode()
    assert 'value="selesai"' in body and "Siap ditutup" in body
    client.post(reverse("owner:request_detail", args=[req.pk]), {"aksi": "selesai"})
    req.refresh_from_db()
    assert req.completed_by == hansen


def test_owner_cannot_post_director_actions(client, jemur, yohanes):
    req = _temuan(yohanes)
    _sub(req, jemur, status=ActionItemStatus.SELESAI)
    client.force_login(yohanes)
    url = reverse("owner:request_detail", args=[req.pk])
    assert client.post(url, {"aksi": "selesai"}).status_code == 403
    assert client.post(url, {"aksi": "rencana", "rencana": "X", "target": ""}).status_code == 403
    req.refresh_from_db()
    assert req.completed_at is None and req.plan_title == ""


def test_dashboard_shows_cap_and_completion(client, jemur, yohanes, hansen):
    open_one = _temuan(yohanes, title="Belum bertarget")
    done = _temuan(yohanes, title="Sudah beres")
    _sub(done, jemur, status=ActionItemStatus.SELESAI)
    services.complete_finding(done, actor=hansen)
    client.force_login(yohanes)
    body = client.get(reverse("owner:dashboard")).content.decode()
    cap = services.deadline_cap(open_one)
    assert f"Paling lambat {cap:%d/%m/%Y}" in body
    assert "Selesai &amp; terverifikasi" in body and "tepat waktu" in body and "dr. Hansen" in body
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_temuan_rencana.py -q -k "detail or director_sets or cannot_post or dashboard"`
Expected: FAIL (teks belum tampil, aksi belum dikenali).

- [ ] **Step 3: View**

Di `owner/views.py` `request_detail`, tambahkan sebagai pemeriksaan POST pertama (sebelum `if request.method == "POST" and request.POST.get("aksi") == "task":`):

```python
    if request.method == "POST" and request.POST.get("aksi") in ("rencana", "selesai"):
        return _finding_action(request, req)
```

Tambahkan `"subtasks": services.subtask_rows(req) if req.kind == "TEMUAN" else [],` ke context `render(...)`.

Tambahkan fungsi baru sesudah `_request_task`:

```python
def _finding_action(request, req):
    """Direktur: simpan rencana penanganan temuan, atau nyatakan temuan selesai & terverifikasi."""
    try:
        with transaction.atomic():
            if request.POST.get("aksi") == "rencana":
                services.set_plan(
                    req, actor=request.user, plan_title=request.POST.get("rencana", ""),
                    target_date=services.parse_target(request.POST.get("target", ""), required=False),
                )
                messages.success(request, "Rencana penanganan disimpan.")
            else:
                services.complete_finding(req, actor=request.user)
                messages.success(request, "Temuan dinyatakan selesai & terverifikasi.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("owner:request_detail", pk=req.pk)
```

`PermissionDenied` dari service tidak ditangkap, sehingga Owner mendapat 403.

- [ ] **Step 4: Status tag**

Ganti baris pertama `templates/owner/_request_state.html` dengan:

```html
<span class="tag {% if r.state == 'done' %}ok{% elif r.state == 'ready' %}warn{% elif r.state == 'running' %}info{% else %}muted{% endif %}">{{ r.label }}</span>
```

Ganti `aria-label` dan teks meter `task` menjadi `sub task` hanya bila jenisnya temuan:

```html
<span class="request-meter"><span class="meter" role="img" aria-label="{{ r.done }} dari {{ r.total }} {% if r.request.kind == 'TEMUAN' %}sub {% endif %}task selesai"><span style="width:{{ r.percent }}%"></span></span><span class="meta">{{ r.done }}/{{ r.total }} {% if r.request.kind == 'TEMUAN' %}sub {% endif %}task</span></span>
```

- [ ] **Step 5: Baris dashboard**

Di `templates/owner/dashboard.html`, ganti baris `<strong>…{{ r.request.title }}</strong>` (baris 23) agar memuat nama task besar:

```html
          <strong>{% if r.request.kind == 'TEMUAN' %}<span class="tag info">Temuan</span> {% endif %}{% if r.request.urgent %}<span class="tag err">Mendesak</span> {% endif %}{{ r.request.title }}</strong>{% if r.request.plan_title %}<span class="meta">Task besar: {{ r.request.plan_title }}</span>{% endif %}
```

Ganti baris `<span class="meta">…</span>` (baris 24) dengan:

```html
          <span class="meta">{% if r.target %}{% if r.target_set %}Target{% else %}Paling lambat{% endif %} {{ r.target|date:"d/m/Y" }}{% if r.state == 'done' %}{% if r.request.completed_at %} · selesai {{ r.request.completed_at|date:"d/m/Y" }} oleh {{ r.request.completed_by }}, {% if r.finished_late_by %}terlambat {{ r.finished_late_by }} hari{% else %}tepat waktu{% endif %}{% endif %}{% else %} · {% if r.days_left > 0 %}{{ r.days_left }} hari lagi{% elif r.days_left == 0 %}hari ini{% else %}lewat {{ r.days_late }} hari{% endif %}{% endif %}{% else %}Tanpa target{% endif %} · {{ r.request.clinic.name|default:"Lintas cabang" }} · {{ r.request.created_by }}</span>
```

- [ ] **Step 6: Halaman detail**

Di `templates/owner/request_detail.html`:

(a) Ganti potongan target pada `<p class="sub">` —
`{% if row.request.target_date %}target <strong>{{ row.request.target_date|date:"d/m/Y" }}</strong>{% else %}tanpa target{% endif %}` — dengan:

```html
{% if row.target %}{% if row.target_set %}target{% else %}paling lambat{% endif %} <strong>{{ row.target|date:"d/m/Y" }}</strong>{% else %}tanpa target{% endif %}
```

(b) Sesudah baris `<p>{% with r=row %}…{% endwith %}</p>`, tambahkan:

```html
{% if row.request.kind == 'TEMUAN' %}
<p><strong>Task besar:</strong> {{ row.request.plan_title|default:"belum diberi nama oleh Direktur" }}</p>
{% if row.request.completed_at %}<p class="meta">Dinyatakan selesai &amp; terverifikasi oleh <strong>{{ row.request.completed_by }}</strong>, {{ row.request.completed_at|date:"d/m/Y H:i" }} · {% if row.finished_late_by %}terlambat {{ row.finished_late_by }} hari{% else %}tepat waktu{% endif %}</p>{% endif %}
{% endif %}
```

(c) Ganti judul dan daftar `<h2>Task dari Direktur</h2>` … `{% endif %}` (sampai sebelum `{% if triage %}`) dengan:

```html
{% if row.request.kind == 'TEMUAN' %}
<h2>Sub task</h2>
{% if subtasks %}
<ul class="request-list card">
  {% for s in subtasks %}
  <li class="request-row">
    <span class="request-main"><strong>{{ s.task.title }}</strong>
      <span class="meta">Dikerjakan oleh {{ s.people|default:"belum ada penerima" }}{% if s.finished_at %} · selesai {{ s.finished_at|date:"d/m/Y" }}{% elif s.task.due_at %} · target {{ s.task.due_at|date:"d/m/Y" }}{% endif %}</span></span>
    <span class="request-state"><span class="tag {% if s.state == 'done' %}ok{% elif s.state == 'waiting' %}warn{% else %}info{% endif %}">{{ s.label }}</span></span>
  </li>
  {% endfor %}
</ul>
{% else %}
<p class="meta">Belum dipecah menjadi sub task oleh Direktur Operasional.</p>
{% endif %}
{% else %}
<h2>Task dari Direktur</h2>
{% if row.tasks %}
<ul class="request-list card">
  {% for t in row.tasks %}
  <li class="request-row">
    <span class="request-main"><strong>{{ t.title }}</strong>
      <span class="meta">{{ t.clinic.name }}{% if t.owner %} · {{ t.owner }}{% endif %}{% if t.due_at %} · target {{ t.due_at|date:"d/m/Y" }}{% endif %}</span></span>
    <span class="request-state"><span class="tag {% if t.status == 'SELESAI' %}ok{% elif t.is_overdue %}err{% else %}info{% endif %}">{% if t.is_overdue %}Lewat target{% else %}{{ t.get_status_display }}{% endif %}</span></span>
  </li>
  {% endfor %}
</ul>
{% else %}
<p class="meta">Belum dipecah menjadi task oleh Direktur Operasional.</p>
{% endif %}
{% endif %}
```

(d) Di dalam `{% if is_director %}`, sebelum `<details class="card"…>` untuk tambah task, tambahkan:

```html
{% if row.request.kind == 'TEMUAN' and not row.request.completed_at %}
<form method="post" class="card">{% csrf_token %}<input type="hidden" name="aksi" value="rencana">
  <label for="rencana">Task besar <span class="meta">(nama penanganan)</span></label>
  <input id="rencana" name="rencana" maxlength="200" value="{{ row.request.plan_title }}" placeholder="Mis. Membuat alur untuk temuan ini">
  <label for="target-rencana">Target selesai <span class="meta">(paling lambat {{ cap|date:"d/m/Y" }})</span></label>
  <input id="target-rencana" type="date" name="target" min="{{ today|date:'Y-m-d' }}" max="{{ cap|date:'Y-m-d' }}" value="{{ row.request.target_date|date:'Y-m-d' }}">
  <p><button class="btn small secondary" type="submit">Simpan rencana</button></p>
</form>
{% if row.state == 'ready' %}
<form method="post" class="card" onsubmit="return confirm('Nyatakan temuan ini selesai & terverifikasi? Owner akan diberi tahu.')">{% csrf_token %}
  <input type="hidden" name="aksi" value="selesai">
  <p>Semua sub task sudah selesai.</p>
  <p><button class="btn small" type="submit">Nyatakan selesai &amp; terverifikasi</button></p>
</form>
{% endif %}
{% endif %}
```

dan ganti teks ringkasan `<summary>` menjadi
`{% if row.tasks %}Tambah {% if row.request.kind == 'TEMUAN' %}sub {% endif %}task{% else %}Pecah menjadi {% if row.request.kind == 'TEMUAN' %}sub {% endif %}task{% endif %}`.

Tambahkan `"cap": services.deadline_cap(req), "today": local_today(),` ke context `request_detail`.

Ganti nilai bawaan kolom batas sub task agar mengikuti target efektif:
`value="{{ row.target|date:'Y-m-d' }}"` pada `<input id="batas" …>`.

- [ ] **Step 7: Jalankan test**

Run: `.venv/bin/python -m pytest owner -q`
Expected: semua PASS. Test lama `test_late_request_is_flagged_and_listed_first` tetap lulus karena teks "lewat 3 hari" dipertahankan.

- [ ] **Step 8: Tinjau diff (tanpa commit)**

Run: `git diff owner/views.py templates/owner/`

---

### Task 6: Dokumentasi

**Files:**
- Modify: `docs/panduan-owner.md`, `docs/panduan-direktur.md`, `docs/peran-dan-akses.md`, `current-progress.md`

- [ ] **Step 1: Cari bagian yang membahas temuan dan aturan pemeriksa**

Run: `grep -n -i "temuan\|diperiksa Direktur Utama\|diverifikasi Direktur Utama\|pekerjaan Direktur" docs/panduan-owner.md docs/panduan-direktur.md docs/peran-dan-akses.md`

- [ ] **Step 2: Perbarui panduan**

- `docs/panduan-owner.md`, di bagian temuan: centang Mendesak = dibereskan paling lambat 3 hari; tanpa centang = Direktur menentukan target, paling lambat 1 bulan; kolom target tidak ada di form temuan; dashboard menunjukkan sub task, siapa yang mengerjakan, status verifikasi, dan "Selesai & terverifikasi oleh … tepat waktu/terlambat n hari".
- `docs/panduan-direktur.md`, di bagian temuan: isi Task besar dan target (batas 3/30 hari); tambah sub task, boleh untuk diri sendiri; sub task sendiri selesai tanpa verifikasi; sub task staf Anda verifikasi; tombol "Nyatakan selesai & terverifikasi" muncul saat semua sub task selesai, dan pernyataan itu menjadi tanggung jawab Direktur di hadapan Owner.
- `docs/peran-dan-akses.md`, pada aturan "pekerjaan Direktur diperiksa Direktur Utama": tambahkan pengecualian sub task temuan Owner (tanpa verifikasi; sub task staf diverifikasi Direktur).
- `current-progress.md`, baris "Belum dideploy": tambahkan "Temuan Owner sebagai task besar dan sub task (migrasi `owner 0003`)"; perbarui jumlah test dengan hasil Task 7.

---

### Task 7: Verifikasi menyeluruh, uji UI, lalu commit setelah persetujuan

- [ ] **Step 1: Migrasi pada database pengembangan (cadangan dulu)**

Run: `cp data/db.sqlite3 "data/db.sqlite3.bak-$(date +%F-%H%M)"`
Run: `.venv/bin/python manage.py migrate`
Expected: `Applying owner.0003_rencana_temuan... OK`

- [ ] **Step 2: Seluruh test**

Run: `.venv/bin/python -m pytest 2>&1 | grep -E "passed|failed" | tail -1`
Expected: `NNN passed` tanpa `failed` (baseline sebelum pekerjaan: 899 passed).

- [ ] **Step 3: `check` dan migrasi tidak tertinggal**

Run: `.venv/bin/python manage.py check`
Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: "System check identified no issues" dan "No changes detected".

- [ ] **Step 4: Uji UI di browser (database pengembangan)**

Jalankan server: `.venv/bin/python manage.py runserver 0.0.0.0:8000`, buka `http://localhost:8000` dari browser Windows. Dengan akun Owner dan Direktur pengembangan, periksa di lebar desktop dan HP (375 px):
1. Owner: form "Catat temuan" tanpa kolom target, centang Mendesak, kirim.
2. Direktur: detail temuan, isi Task besar dan target melewati batas (ditolak), lalu dalam batas (tersimpan).
3. Direktur: tambah sub task untuk diri sendiri dan untuk staf; ajukan selesai sub task sendiri (langsung "Selesai oleh Direktur").
4. Staf: ajukan selesai; Direktur konfirmasi ("Terverifikasi Direktur").
5. Direktur: tombol "Nyatakan selesai & terverifikasi" muncul, konfirmasi, tekan.
6. Owner: dashboard menunjukkan status, oleh siapa, dan tepat waktu/terlambat; notifikasi diterima.

- [ ] **Step 5: Laporkan dan minta persetujuan**

Laporkan ke product owner: file yang berubah (`git status --short`), hasil test, temuan uji UI, risiko tersisa, approval yang masih diperlukan (commit/push, deployment). **Berhenti di sini sampai disetujui.**

- [ ] **Step 6: Commit setelah persetujuan**

```bash
git add owner/ core/models.py core/task_services.py templates/owner/ reports/tests/test_inbox_pilah.py docs/panduan-owner.md docs/panduan-direktur.md docs/peran-dan-akses.md current-progress.md docs/superpowers/plans/2026-10-06-temuan-owner-sub-task.md
git commit -m "Temuan Owner: task besar dengan sub task, batas 3/30 hari, penutupan oleh Direktur"
```

Push hanya bila product owner memintanya.
