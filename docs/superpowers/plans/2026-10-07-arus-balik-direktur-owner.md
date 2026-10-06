# Arus balik Direktur → Owner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Owner bisa memutuskan permintaan keputusan Direktur (Setujui/Tolak/Bahas di rapat) dengan notifikasi dua arah, "Teruskan ke Owner" di Inbox menjadi permintaan keputusan, dan Summary Harian punya tanda baca serta tanggapan.

**Architecture:** Register `direktur.Decision` yang ada dipakai sebagai satu-satunya jalur; dua kolom baru (`verdict`, `decided_by`). Aturan Owner memutuskan dan Summary dua arah ada di `owner/services.py`; halaman Owner di app `owner`. Dua tabel baru untuk Summary (`DailySummaryRead`, `DailySummaryNote`) di app `direktur`, di samping `DailySummary`.

**Tech Stack:** Django 5.1, Python 3.11 (`.venv`), pytest + pytest-django, template Django.

**Spec:** `docs/superpowers/specs/2026-10-07-arus-balik-direktur-owner-design.md`

## Global Constraints

- Kerja di worktree WSL `~/joderma-arus-balik` (branch `arus-balik`). Semua perintah dari direktori itu dengan `.venv/bin/python` (Python 3.11). Jangan menyentuh `~/joderma-operasional`.
- **Jangan commit, `git add`, stash, atau mengubah index git.** Index dipakai controller sebagai titik periksa; pekerjaan tiap task ditinjau sebagai `git diff`. (AGENTS.md: tidak commit sebelum product owner meninjau bukti pengujian.)
- Otorisasi di service (server-side); menyembunyikan tombol bukan kontrol akses.
- Siapa saja yang berperan `Role.OWNER` boleh memutuskan perkara berpemutus `OWNER` atau `DIRUT`; keputusan pertama yang berlaku.
- Teks isi keputusan persis: `Disetujui <nama>` / `Disetujui <nama>: <catatan>`; `Ditolak <nama>: <catatan>`; nama = `str(user)`.
- Baris tambahan latar saat dibawa ke rapat persis: `Catatan Owner (<nama>, <dd/mm/YYYY>): <catatan>`.
- `type_code` notifikasi persis: `DECISION_REQUESTED`, `DECISION_DECIDED`, `SUMMARY_NOTE`.
- Migrasi hanya menambah kolom/tabel: `direktur 0006_keputusan_owner`, `direktur 0007_summary_dua_arah`.
- Teks antarmuka dan komentar berbahasa Indonesia, mengikuti gaya file sekitarnya.
- `pytest.ini` sudah menambah `-q`; jangan menambah lagi. Ringkasan: `| grep -E "passed|failed" | tail -1`.

---

## File Structure

| File | Tanggung jawab |
|---|---|
| `direktur/models.py` | `Verdict`; kolom `Decision.verdict`, `Decision.decided_by`; model `DailySummaryRead`, `DailySummaryNote` |
| `direktur/migrations/0006_keputusan_owner.py`, `0007_summary_dua_arah.py` | migrasi additive (dibuat `makemigrations`) |
| `direktur/services.py` | `OWNER_DECIDERS`, `is_owner_decision`, notifikasi ke Owner di `create_decision` |
| `owner/services.py` | `decide`, `decisions_awaiting`, `record_summary_read`, `summary_reads`, `summary_is_read`, `add_summary_note` |
| `owner/views.py`, `owner/urls.py` | halaman `owner:decision`; dashboard memuat kartu; `summary` menerima tanggapan dan mencatat baca |
| `templates/owner/decision.html` (baru), `dashboard.html`, `summary.html` | tampilan |
| `reports/triage.py` | `forward` ke `DIRUT` membuat perkara Keputusan |
| `owner/tests/test_keputusan_owner.py`, `reports/tests/test_teruskan_owner.py`, `owner/tests/test_summary_dua_arah.py` | test |
| `docs/panduan-owner.md`, `docs/panduan-direktur.md`, `docs/peran-dan-akses.md` | dokumentasi |

---

### Task 1: Owner memutuskan (data dan service)

**Files:**
- Modify: `direktur/models.py` (sesudah `class Decider`; kolom di `class Decision` sesudah `decided_on`)
- Create: `direktur/migrations/0006_keputusan_owner.py` (via makemigrations)
- Modify: `direktur/services.py` (konstanta + fungsi sesudah blok import)
- Modify: `owner/services.py` (fungsi baru di akhir bagian `# --- Permintaan ---`, sebelum `# --- Jadwal ringkas ---`)
- Create: `owner/tests/test_keputusan_owner.py`

**Interfaces:**
- Produces: `direktur.models.Verdict` (`SETUJU`, `TOLAK`); `Decision.verdict: str`, `Decision.decided_by: User | None`; `direktur.services.OWNER_DECIDERS: set[str]`, `direktur.services.is_owner_decision(decision) -> bool`; `owner.services.decide(decision, *, actor, verdict: str, note: str = "") -> Decision` (`verdict` ∈ `"setuju" | "tolak" | "rapat"`); `owner.services.decisions_awaiting(user) -> list[dict]` dengan kunci `decision`, `late`, `age_days`.

- [ ] **Step 1: Tulis test yang gagal**

Buat `owner/tests/test_keputusan_owner.py`:

```python
"""Owner memutuskan permintaan keputusan Direktur Operasional (7 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from accounts.models import Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import ActionItem, Clinic, local_today
from direktur import services as direktur
from direktur.models import Decider, Decision, DecisionStatus, Verdict
from notifications.models import Notification
from owner import services

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
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes")


@pytest.fixture
def jean(jemur):
    return _user(jemur, "jean", Role.OWNER, display_name="Jean")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def yani(jemur):
    return _user(jemur, "yani", Role.STAF, display_name="Yani")


def _perkara(hansen, jemur, title="Tambah anggaran tissue", decider=Decider.OWNER, **kw):
    return direktur.create_decision(actor=hansen, title=title, decider=decider, clinic=jemur,
                                    background="Tissue habis tiap Sabtu.", **kw)


# --- Task 1: service ---------------------------------------------------------------


def test_owner_approves_with_note(jemur, yohanes, hansen):
    d = services.decide(_perkara(hansen, jemur), actor=yohanes, verdict="setuju", note="boleh, maksimal Rp1,5 juta")
    d.refresh_from_db()
    assert (d.status, d.verdict, d.decided_by, d.decided_on) == (
        DecisionStatus.DITETAPKAN, Verdict.SETUJU, yohanes, local_today())
    assert d.decision_text == "Disetujui dr. Yohanes: boleh, maksimal Rp1,5 juta"
    note = Notification.objects.get(user=hansen, type_code="DECISION_DECIDED")
    assert note.title == "Keputusan Owner: Tambah anggaran tissue" and note.body == d.decision_text
    assert note.url == reverse("direktur:decision_detail", args=[d.pk])
    assert AuditEvent.objects.filter(entity_type="decision", entity_id=str(d.pk), action=AuditAction.APPROVE).exists()


def test_approve_without_note(jemur, yohanes, hansen):
    d = services.decide(_perkara(hansen, jemur), actor=yohanes, verdict="setuju")
    assert d.decision_text == "Disetujui dr. Yohanes"


def test_reject_requires_reason(jemur, jean, hansen):
    d = _perkara(hansen, jemur)
    with pytest.raises(ValidationError, match="alasan penolakan"):
        services.decide(d, actor=jean, verdict="tolak", note="  ")
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU
    services.decide(d, actor=jean, verdict="tolak", note="perlu angka pembanding dulu")
    d.refresh_from_db()
    assert (d.verdict, d.decision_text) == (Verdict.TOLAK, "Ditolak Jean: perlu angka pembanding dulu")


def test_move_to_meeting_keeps_waiting(jemur, yohanes, hansen):
    d = services.decide(_perkara(hansen, jemur), actor=yohanes, verdict="rapat", note="bahas bareng apoteker")
    d.refresh_from_db()
    assert (d.status, d.decider, d.verdict, d.decided_by) == (
        DecisionStatus.MENUNGGU, Decider.RAPAT_BERSAMA, "", None)
    assert d.background.endswith(f"Catatan Owner (dr. Yohanes, {local_today():%d/%m/%Y}): bahas bareng apoteker")
    note = Notification.objects.get(user=hansen, type_code="DECISION_DECIDED")
    assert note.body == "Dibawa ke rapat Kamis: bahas bareng apoteker"


def test_waiting_tasks_released_only_when_decided(jemur, yohanes, hansen):
    held = ActionItem.objects.create(clinic=jemur, title="Beli tissue", source_type="manual")
    d = _perkara(hansen, jemur)
    d.waiting_tasks.add(held)
    services.decide(d, actor=yohanes, verdict="rapat")
    assert ActionItem.objects.get(pk=held.pk).on_hold
    d2 = _perkara(hansen, jemur, title="Perkara kedua")
    held2 = ActionItem.objects.create(clinic=jemur, title="Pasang rak", source_type="manual")
    d2.waiting_tasks.add(held2)
    services.decide(d2, actor=yohanes, verdict="setuju")
    assert not ActionItem.objects.get(pk=held2.pk).on_hold


def test_dirut_decider_is_also_decided_by_owner(jemur, jean, hansen):
    d = services.decide(_perkara(hansen, jemur, decider=Decider.DIRUT), actor=jean, verdict="setuju")
    assert d.status == DecisionStatus.DITETAPKAN


@pytest.mark.parametrize("who", ["hansen", "yani"])
def test_only_owner_decides(jemur, hansen, yani, who):
    d = _perkara(hansen, jemur)
    with pytest.raises(PermissionDenied):
        services.decide(d, actor={"hansen": hansen, "yani": yani}[who], verdict="setuju")
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU


def test_owner_cannot_decide_other_or_closed_matters(jemur, yohanes, jean, hansen):
    meeting = _perkara(hansen, jemur, decider=Decider.RAPAT_BERSAMA)
    with pytest.raises(ValidationError):
        services.decide(meeting, actor=yohanes, verdict="setuju")
    first = _perkara(hansen, jemur, title="Sudah diputuskan")
    services.decide(first, actor=yohanes, verdict="setuju")
    with pytest.raises(ValidationError):
        services.decide(first, actor=jean, verdict="tolak", note="tidak")
    assert Decision.objects.get(pk=first.pk).decided_by == yohanes
    cancelled = _perkara(hansen, jemur, title="Dibatalkan")
    direktur.cancel_decision(cancelled, actor=hansen, reason="tidak relevan")
    with pytest.raises(ValidationError):
        services.decide(cancelled, actor=yohanes, verdict="setuju")
    moved = _perkara(hansen, jemur, title="Sudah ke rapat")
    services.decide(moved, actor=yohanes, verdict="rapat")
    with pytest.raises(ValidationError):
        services.decide(moved, actor=jean, verdict="setuju")
    with pytest.raises(ValidationError):
        services.decide(_perkara(hansen, jemur, title="Pilihan aneh"), actor=yohanes, verdict="nanti")


def test_decisions_awaiting_order_and_scope(jemur, yohanes, hansen):
    later = _perkara(hansen, jemur, title="Nanti", needed_by=local_today() + dt.timedelta(days=5))
    none = _perkara(hansen, jemur, title="Tanpa tenggat")
    late = _perkara(hansen, jemur, title="Terlambat")
    Decision.objects.filter(pk=late.pk).update(needed_by=local_today() - dt.timedelta(days=1))
    _perkara(hansen, jemur, title="Rapat", decider=Decider.RAPAT_BERSAMA)
    services.decide(_perkara(hansen, jemur, title="Sudah"), actor=yohanes, verdict="setuju")
    rows = services.decisions_awaiting(yohanes)
    assert [r["decision"].pk for r in rows] == [late.pk, later.pk, none.pk]
    assert rows[0]["late"] and not rows[1]["late"] and rows[0]["age_days"] == 0
    assert services.decisions_awaiting(hansen) == []
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_keputusan_owner.py`
Expected: FAIL — `ImportError: cannot import name 'Verdict' from 'direktur.models'`.

- [ ] **Step 3: Model dan migrasi**

Di `direktur/models.py`, sesudah `class Decider`:

```python
class Verdict(models.TextChoices):
    """Jawaban Owner atas permintaan keputusan Direktur Operasional (7 Okt 2026)."""

    SETUJU = "SETUJU", "Disetujui"
    TOLAK = "TOLAK", "Ditolak"
```

Di `class Decision`, sesudah `decided_on`:

```python
    verdict = models.CharField("jawaban Owner", max_length=10, choices=Verdict.choices, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Owner yang memutuskan lewat halaman Owner (7 Okt 2026).",
    )
```

Run: `.venv/bin/python manage.py makemigrations direktur --name keputusan_owner`
Expected: `direktur/migrations/0006_keputusan_owner.py` dengan dua `AddField`.

- [ ] **Step 4: Penentu perkara Owner di `direktur/services.py`**

Sesudah blok import (pastikan `Decider` sudah diimpor dari `.models`; bila belum, tambahkan ke daftar import `.models`):

```python
OWNER_DECIDERS = {Decider.OWNER, Decider.DIRUT}


def is_owner_decision(decision: Decision) -> bool:
    """Perkara yang diputuskan siapa saja yang berperan Owner / Direktur Utama (7 Okt 2026)."""
    return decision.decider in OWNER_DECIDERS
```

- [ ] **Step 5: Service Owner di `owner/services.py`**

Tambahkan sebelum `# --- Jadwal ringkas ---`:

```python
# --- Keputusan Owner (7 Okt 2026) ------------------------------------------------------

DECIDE_ACTIONS = ("setuju", "tolak", "rapat")


def _notify_decision_outcome(decision, *, actor, text: str) -> None:
    """Hasil keputusan Owner ke semua Direktur Operasional aktif dan pengaju perkara."""
    from notifications.services import notify_user

    people = {u.pk: u for u in _directors()}
    if decision.created_by_id and decision.created_by.is_active:
        people.setdefault(decision.created_by_id, decision.created_by)
    for person in people.values():
        if person.pk == actor.pk:
            continue
        notify_user(
            person, type_code="DECISION_DECIDED", title=f"Keputusan Owner: {decision.title}", body=text,
            entity_ref=f"decision#{decision.pk}", url_name="direktur:decision_detail", url_args=[decision.pk],
        )


@transaction.atomic
def decide(decision, *, actor, verdict: str, note: str = ""):
    """Owner menjawab permintaan keputusan Direktur: Setujui, Tolak (alasan wajib), atau Bahas di rapat."""
    from direktur.models import Decider, Decision, DecisionStatus, Verdict
    from direktur.services import _release_waiting, is_owner_decision

    if not is_owner(actor):
        raise PermissionDenied("Hanya Owner / Direktur Utama yang memutuskan perkara ini.")
    if verdict not in DECIDE_ACTIONS:
        raise ValidationError("Pilihan keputusan tidak dikenal.")
    decision = Decision.objects.select_for_update().get(pk=decision.pk)
    if decision.status != DecisionStatus.MENUNGGU or not is_owner_decision(decision):
        raise ValidationError("Perkara ini sudah diputuskan, dibatalkan, atau dipindah ke rapat.")
    note = (note or "").strip()
    if verdict == "tolak" and not note:
        raise ValidationError("Tulis alasan penolakan.")
    before = snapshot(decision)
    name = str(actor)
    if verdict == "rapat":
        decision.decider = Decider.RAPAT_BERSAMA
        if note:
            line = f"Catatan Owner ({name}, {local_today():%d/%m/%Y}): {note}"
            decision.background = f"{decision.background}\n\n{line}".strip()
        decision.save()
        log_update(decision, before, actor=actor)
        text = "Dibawa ke rapat Kamis" + (f": {note}" if note else "")
    else:
        decision.status = DecisionStatus.DITETAPKAN
        decision.verdict = Verdict.SETUJU if verdict == "setuju" else Verdict.TOLAK
        decision.decided_by = actor
        decision.decided_on = local_today()
        label = "Disetujui" if verdict == "setuju" else "Ditolak"
        decision.decision_text = f"{label} {name}" + (f": {note}" if note else "")
        decision.save()
        log_update(decision, before, actor=actor, action=AuditAction.APPROVE)
        _release_waiting(decision, actor=actor, verb="ditetapkan")
        text = decision.decision_text
    _notify_decision_outcome(decision, actor=actor, text=text)
    return decision


def decisions_awaiting(user) -> list[dict]:
    """Kartu "Menunggu keputusan Anda": perkara Owner/Dirut yang masih menunggu, terlambat dulu."""
    from direktur.dashboard import decisions_for
    from direktur.models import DecisionStatus
    from direktur.services import OWNER_DECIDERS

    if not is_owner(user):
        return []
    today = local_today()
    qs = decisions_for(user).filter(status=DecisionStatus.MENUNGGU, decider__in=OWNER_DECIDERS)
    rows = [
        {"decision": d, "late": d.is_overdue(today), "age_days": (today - timezone.localtime(d.created_at).date()).days}
        for d in qs.select_related("created_by", "clinic")
    ]
    rows.sort(key=lambda r: (not r["late"], r["decision"].needed_by or dt.date.max, r["decision"].created_at))
    return rows
```

Periksa import di bagian atas `owner/services.py`: harus ada `from django.utils import timezone`, `from audit.models import AuditAction`, `from audit.services import ... log_update, snapshot`, `from core.models import ... local_today`, `from core.permissions import is_aom, is_owner`, `from django.db import transaction`, `from django.core.exceptions import PermissionDenied, ValidationError`. Tambahkan yang belum ada.

- [ ] **Step 6: Jalankan test**

Run: `.venv/bin/python -m pytest owner/tests/test_keputusan_owner.py direktur`
Expected: semua PASS.

- [ ] **Step 7: Tinjau diff (tanpa commit)**

Run: `git status --short` dan `git diff --stat`

---

### Task 2: Halaman keputusan Owner dan kartu dashboard

**Files:**
- Modify: `owner/urls.py`, `owner/views.py`
- Create: `templates/owner/decision.html`
- Modify: `templates/owner/dashboard.html` (sisipkan sebelum `<section class="card owner-requests"`)
- Test: `owner/tests/test_keputusan_owner.py` (tambahkan)

**Interfaces:**
- Consumes: `services.decide`, `services.decisions_awaiting`, `direktur.services.is_owner_decision`, `direktur.dashboard.decisions_for(user)`.
- Produces: URL `owner:decision` (`/owner/keputusan/<int:pk>/`); POST `aksi=setuju|tolak|rapat`, `catatan`.

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan ke `owner/tests/test_keputusan_owner.py`:

```python
# --- Task 2: halaman dan dashboard ----------------------------------------------------


def test_owner_page_decides(client, jemur, yohanes, hansen):
    d = _perkara(hansen, jemur)
    url = reverse("owner:decision", args=[d.pk])
    client.force_login(yohanes)
    body = client.get(url).content.decode()
    for text in ("Tambah anggaran tissue", "Tissue habis tiap Sabtu.", 'value="setuju"', 'value="tolak"',
                 'value="rapat"', "Bahas di rapat Kamis"):
        assert text in body
    response = client.post(url, {"aksi": "setuju", "catatan": "oke"})
    assert response["Location"] == url
    d.refresh_from_db()
    assert d.decision_text == "Disetujui dr. Yohanes: oke"
    body = client.get(url).content.decode()
    assert "Disetujui dr. Yohanes: oke" in body and 'value="setuju"' not in body


def test_reject_without_reason_shows_error(client, jemur, yohanes, hansen):
    d = _perkara(hansen, jemur)
    client.force_login(yohanes)
    body = client.post(reverse("owner:decision", args=[d.pk]), {"aksi": "tolak", "catatan": ""}, follow=True)
    assert "Tulis alasan penolakan." in body.content.decode()
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU


def test_director_reads_but_cannot_post_and_staff_blocked(client, jemur, hansen, yani):
    d = _perkara(hansen, jemur)
    url = reverse("owner:decision", args=[d.pk])
    client.force_login(hansen)
    body = client.get(url).content.decode()
    assert "Tambah anggaran tissue" in body and 'value="setuju"' not in body
    assert client.post(url, {"aksi": "setuju"}).status_code == 403
    d.refresh_from_db()
    assert d.status == DecisionStatus.MENUNGGU
    client.force_login(yani)
    assert client.get(url).status_code == 403


def test_dashboard_card(client, jemur, yohanes, hansen):
    client.force_login(yohanes)
    assert "Menunggu keputusan Anda" not in client.get(reverse("owner:dashboard")).content.decode()
    d = _perkara(hansen, jemur)
    Decision.objects.filter(pk=d.pk).update(needed_by=local_today() - dt.timedelta(days=1))
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert "Menunggu keputusan Anda" in body and "Tambah anggaran tissue" in body and "Lewat tenggat" in body
    assert reverse("owner:decision", args=[d.pk]) in body
    services.decide(d, actor=yohanes, verdict="setuju")
    assert "Menunggu keputusan Anda" not in client.get(reverse("owner:dashboard")).content.decode()
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_keputusan_owner.py -k "page or reject_without or director_reads or dashboard_card"`
Expected: FAIL — `NoReverseMatch: Reverse for 'decision' not found`.

- [ ] **Step 3: URL dan view**

Di `owner/urls.py`, tambahkan sesudah baris `request_detail`:

```python
    path("keputusan/<int:pk>/", views.decision_page, name="decision"),
```

Di `owner/views.py`, ubah import `from core.permissions import is_aom, require, user_clinic_queryset` menjadi `from core.permissions import is_aom, is_owner, require, user_clinic_queryset`, lalu tambahkan sesudah `_request_task`:

```python
@login_required
@require(services.can_view_requests)
def decision_page(request, pk: int):
    """Permintaan keputusan Direktur untuk Owner (7 Okt 2026). Direktur boleh membaca; hanya Owner memutuskan."""
    from direktur.dashboard import decisions_for
    from direktur.models import DecisionStatus
    from direktur.services import is_owner_decision

    decision = get_object_or_404(decisions_for(request.user).select_related("created_by", "decided_by"), pk=pk)
    if request.method == "POST":
        try:
            services.decide(decision, actor=request.user, verdict=request.POST.get("aksi", ""),
                            note=request.POST.get("catatan", ""))
            messages.success(request, "Keputusan dikirim ke Direktur Operasional.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("owner:decision", pk=pk)
    return render(request, "owner/decision.html", {
        "decision": decision,
        "tasks": list(decision.waiting_tasks.select_related("clinic")),
        "can_decide": is_owner(request.user) and decision.status == DecisionStatus.MENUNGGU
        and is_owner_decision(decision),
    })
```

Di `dashboard_page`, tambahkan ke context: `"awaiting": services.decisions_awaiting(user),`.

- [ ] **Step 4: Template halaman**

Buat `templates/owner/decision.html`:

```html
{% extends "base.html" %}
{% block title %}{{ decision.title }}{% endblock %}
{% block content %}
<p><a href="{% url 'home' %}">← Kembali</a></p>
<h1>{{ decision.title }}</h1>
<p class="sub">Diajukan {{ decision.created_by|default:"Direktur Operasional" }} · {{ decision.created_at|date:"d/m/Y" }} · {{ decision.clinic.name|default:"lintas cabang" }} · {% if decision.needed_by %}perlu diputuskan sebelum <strong>{{ decision.needed_by|date:"d/m/Y" }}</strong>{% else %}tanpa tenggat{% endif %}</p>
<p><span class="tag {% if decision.status == 'DITETAPKAN' %}ok{% elif decision.status == 'DIBATALKAN' %}muted{% else %}warn{% endif %}">{{ decision.get_status_display }}</span> <span class="meta">Pemutus: {{ decision.get_decider_display }}</span></p>
{% if decision.background %}<div class="card" style="white-space:pre-wrap">{{ decision.background }}</div>{% endif %}
{% if tasks %}
<h2>Task yang menunggu keputusan ini</h2>
<ul class="request-list card">
  {% for t in tasks %}<li class="request-row"><span class="request-main"><strong>{{ t.title }}</strong><span class="meta">{{ t.clinic.name }}</span></span></li>{% endfor %}
</ul>
{% endif %}
{% if decision.status == 'DITETAPKAN' %}
<div class="card"><strong>Keputusan</strong><div style="white-space:pre-wrap">{{ decision.decision_text }}</div>
  <p class="meta" style="margin:.3rem 0 0">{% if decision.decided_by %}oleh {{ decision.decided_by }} · {% endif %}{{ decision.decided_on|date:"d/m/Y" }}</p></div>
{% elif can_decide %}
<form method="post" class="card">{% csrf_token %}
  <label for="catatan">Catatan <span class="meta">(wajib bila menolak)</span></label>
  <textarea id="catatan" name="catatan" rows="3" placeholder="Mis. boleh, maksimal Rp1,5 juta"></textarea>
  <p class="inline-actions">
    <button class="btn" type="submit" name="aksi" value="setuju">Setujui</button>
    <button class="btn secondary" type="submit" name="aksi" value="tolak">Tolak</button>
    <button class="btn secondary" type="submit" name="aksi" value="rapat">Bahas di rapat Kamis</button>
  </p>
</form>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Kartu dashboard**

Di `templates/owner/dashboard.html`, sisipkan tepat sebelum `<section class="card owner-requests" aria-labelledby="judul-permintaan">`:

```html
{% if awaiting %}
<section class="card owner-requests" aria-labelledby="judul-keputusan">
  <h2 id="judul-keputusan" style="margin:0">Menunggu keputusan Anda</h2>
  <ul class="request-list">
    {% for a in awaiting %}
    <li><a class="request-row" href="{% url 'owner:decision' a.decision.pk %}">
      <span class="request-main"><strong>{{ a.decision.title }}</strong>
        <span class="meta">{{ a.decision.clinic.name|default:"Lintas cabang" }} · dari {{ a.decision.created_by|default:"Direktur Operasional" }} · {% if a.age_days %}{{ a.age_days }} hari lalu{% else %}hari ini{% endif %}{% if a.decision.needed_by %} · sebelum {{ a.decision.needed_by|date:"d/m/Y" }}{% endif %}</span></span>
      <span class="request-state">{% if a.late %}<span class="tag err">Lewat tenggat</span>{% else %}<span class="tag warn">Putuskan</span>{% endif %}</span>
    </a></li>
    {% endfor %}
  </ul>
</section>
{% endif %}
```

- [ ] **Step 6: Jalankan test**

Run: `.venv/bin/python -m pytest owner`
Expected: semua PASS.

---

### Task 3: Notifikasi perkara baru dan Teruskan ke Owner

**Files:**
- Modify: `direktur/services.py` (`create_decision`, helper baru)
- Modify: `reports/triage.py` (`forward`, helper baru)
- Create: `reports/tests/test_teruskan_owner.py`

**Interfaces:**
- Consumes: `direktur.services.is_owner_decision`, URL `owner:decision` (Task 2), `reports.inbox.find_row(user, source_type, source_id)`, baris Inbox dengan kunci `title`, `description`, `ref`, `kind_label`, `reporter`, `clinic`, `source_type`, `source_id`.
- Produces: `create_decision` memberi notifikasi `DECISION_REQUESTED` ke semua Owner aktif bila `is_owner_decision`; `triage.forward(row, actor=..., to=ForwardTo.DIRUT, note=...)` membuat `Decision` (pemutus `OWNER`) dan menyimpannya di `InboxTriage.decision`.

- [ ] **Step 1: Tulis test yang gagal**

Buat `reports/tests/test_teruskan_owner.py`:

```python
"""Teruskan ke Owner menjadi permintaan keputusan; Owner diberi tahu (7 Okt 2026)."""
import datetime as dt

import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from core.models import Clinic, local_today
from direktur import services as direktur
from direktur.models import Decider, Decision
from notifications.models import Notification
from reports import inbox, triage
from reports.models import ForwardTo, InboxTriage
from reports.services import create_laporan

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def people(jemur):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen"),
        "yohanes": _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes"),
        "jean": _user(jemur, "jean", Role.OWNER, display_name="Jean"),
        "yani": _user(jemur, "yani", Role.STAF, display_name="Yani"),
    }


def test_owner_decision_notifies_all_owners(jemur, people):
    h = people["hansen"]
    d = direktur.create_decision(actor=h, title="Tambah anggaran tissue", decider=Decider.OWNER, clinic=jemur,
                                 needed_by=local_today() + dt.timedelta(days=3))
    for owner in (people["yohanes"], people["jean"]):
        n = Notification.objects.get(user=owner, type_code="DECISION_REQUESTED")
        assert n.title == "Direktur Operasional meminta keputusan: Tambah anggaran tissue"
        assert n.body == f"Jemur Andayani · perlu diputuskan sebelum {d.needed_by:%d/%m/%Y}"
        assert n.url == reverse("owner:decision", args=[d.pk])
    assert not Notification.objects.filter(user=h, type_code="DECISION_REQUESTED").exists()


def test_dirut_decider_notifies_and_other_deciders_do_not(jemur, people):
    h = people["hansen"]
    direktur.create_decision(actor=h, title="Strategis", decider=Decider.DIRUT)
    n = Notification.objects.get(user=people["yohanes"], type_code="DECISION_REQUESTED")
    assert n.body == "lintas cabang · tanpa tenggat"
    for decider in (Decider.RAPAT_BERSAMA, Decider.PJ_PELAYANAN, Decider.DIREKTUR_OPERASIONAL):
        direktur.create_decision(actor=h, title=f"Bukan Owner {decider}", decider=decider, clinic=jemur)
    assert Notification.objects.filter(type_code="DECISION_REQUESTED").count() == 2


def test_forward_to_owner_creates_decision(jemur, people):
    h = people["hansen"]
    laporan = create_laporan(clinic=jemur, user=people["yani"], title="Tissue habis tiap Sabtu",
                             description="Sudah 3 minggu berturut-turut.")
    row = inbox.find_row(h, inbox.SOURCE_LAPORAN, laporan.pk)
    t = triage.forward(row, actor=h, to=ForwardTo.DIRUT, note="perlu tambahan anggaran")
    d = Decision.objects.get()
    assert (d.decider, d.title, d.clinic, d.created_by) == (Decider.OWNER, "Tissue habis tiap Sabtu", jemur, h)
    assert "Sudah 3 minggu berturut-turut." in d.background
    assert f"Rujukan: L-{laporan.pk} ({row['kind_label']}, dari {row['reporter']})" in d.background
    assert "Catatan Direktur: perlu tambahan anggaran" in d.background
    assert InboxTriage.objects.get(pk=t.pk).decision == d
    assert Notification.objects.filter(user=people["yohanes"], type_code="DECISION_REQUESTED").exists()


def test_forward_elsewhere_creates_no_decision(jemur, people):
    h = people["hansen"]
    laporan = create_laporan(clinic=jemur, user=people["yani"], title="Harga obat naik")
    t = triage.forward(inbox.find_row(h, inbox.SOURCE_LAPORAN, laporan.pk), actor=h, to=ForwardTo.APOTEKER)
    assert t.decision is None and not Decision.objects.exists()
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest reports/tests/test_teruskan_owner.py`
Expected: FAIL — `Notification.DoesNotExist` dan `Decision.DoesNotExist`.

- [ ] **Step 3: Notifikasi di `direktur/services.py`**

Pastikan `Role` diimpor: ubah `from accounts.models import PicAssignment, PicFunction, User` menjadi `from accounts.models import PicAssignment, PicFunction, Role, User`. Tambahkan sesudah `is_owner_decision`:

```python
def _notify_owners_of_request(decision: Decision, *, actor) -> None:
    """Perkara berpemutus Owner/Direktur Utama: semua Owner aktif diberi tahu (7 Okt 2026)."""
    from notifications.services import notify_user

    where = decision.clinic.name if decision.clinic_id else "lintas cabang"
    due = f"perlu diputuskan sebelum {decision.needed_by:%d/%m/%Y}" if decision.needed_by else "tanpa tenggat"
    owners = User.objects.filter(is_active=True, user_roles__role=Role.OWNER).distinct()
    for person in owners.exclude(pk=getattr(actor, "pk", None)):
        notify_user(
            person, type_code="DECISION_REQUESTED",
            title=f"Direktur Operasional meminta keputusan: {decision.title}", body=f"{where} · {due}",
            entity_ref=f"decision#{decision.pk}", url_name="owner:decision", url_args=[decision.pk],
        )
```

Di `create_decision`, sesudah `log_create(decision, actor=actor)` dan sebelum `return decision`:

```python
    if is_owner_decision(decision):
        _notify_owners_of_request(decision, actor=actor)
```

- [ ] **Step 4: Teruskan ke Owner di `reports/triage.py`**

Tambahkan sebelum `def forward`:

```python
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
```

Di `forward`, ganti baris

```python
    triage = _save(row, actor=actor, action=TriageAction.TERUSKAN, forwarded_to=to, note=note)
```

dengan

```python
    decision = _owner_decision(row, actor=actor, note=note) if to == ForwardTo.DIRUT else None
    triage = _save(row, actor=actor, action=TriageAction.TERUSKAN, forwarded_to=to, note=note, decision=decision)
```

- [ ] **Step 5: Jalankan test**

Run: `.venv/bin/python -m pytest reports owner direktur`
Expected: semua PASS. Bila test lama di `reports/tests/test_inbox_pilah.py` meneruskan ke `ForwardTo.DIRUT` dan memeriksa bahwa tidak ada Keputusan, laporkan sebagai DONE_WITH_CONCERNS dan jelaskan, jangan ubah diam-diam.

---

### Task 4: Summary Harian dua arah (data dan service)

**Files:**
- Modify: `direktur/models.py` (dua model baru sesudah `class DailySummary`)
- Create: `direktur/migrations/0007_summary_dua_arah.py` (via makemigrations)
- Modify: `owner/services.py` (bagian baru sesudah `decisions_awaiting`)
- Create: `owner/tests/test_summary_dua_arah.py`

**Interfaces:**
- Produces: `direktur.models.DailySummaryRead` (`summary`, `user`, `read_at`; related_name `reads`), `direktur.models.DailySummaryNote` (`summary`, `author`, `body`, `created_at`; related_name `notes`); `owner.services.record_summary_read(summary, user) -> None`, `summary_reads(summary) -> list[dict]` (kunci `user`, `read_at`, `state` ∈ `"baca" | "lama" | "belum"`), `summary_is_read(summary) -> bool`, `add_summary_note(summary, *, actor, body: str) -> DailySummaryNote`.

- [ ] **Step 1: Tulis test yang gagal**

Buat `owner/tests/test_summary_dua_arah.py`:

```python
"""Summary Harian dua arah: tanda baca Owner dan tanggapan Owner ↔ Direktur (7 Okt 2026)."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from core.models import Clinic, local_today
from direktur.models import DailySummary, DailySummaryNote, DailySummaryRead
from notifications.models import Notification
from owner import services

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles, **extra):
    u = User.objects.create_user(username=name, password="TestPassword123!", **extra)
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def yohanes(jemur):
    return _user(jemur, "yohanes", Role.OWNER, display_name="dr. Yohanes")


@pytest.fixture
def jean(jemur):
    return _user(jemur, "jean", Role.OWNER, display_name="Jean")


@pytest.fixture
def hansen(jemur):
    return _user(jemur, "hansen1", Role.AOM, display_name="dr. Hansen")


@pytest.fixture
def yani(jemur):
    return _user(jemur, "yani", Role.STAF, display_name="Yani")


def _summary(hansen, day=None):
    return DailySummary.objects.create(date=day or local_today(), sent_by=hansen, sent_at=timezone.now(),
                                       content={"sections": []}, note="Hari ini tenang.")


# --- Task 4: service ----------------------------------------------------------------


def test_read_recorded_for_owner_only(jemur, yohanes, hansen):
    s = _summary(hansen)
    services.record_summary_read(s, hansen)
    assert not DailySummaryRead.objects.exists()
    services.record_summary_read(None, yohanes)
    services.record_summary_read(s, yohanes)
    services.record_summary_read(s, yohanes)
    assert DailySummaryRead.objects.filter(summary=s, user=yohanes).count() == 1


def test_read_states_and_resend(jemur, yohanes, jean, hansen):
    s = _summary(hansen)
    assert not services.summary_is_read(s)
    services.record_summary_read(s, yohanes)
    states = {r["user"]: r["state"] for r in services.summary_reads(s)}
    assert states == {yohanes: "baca", jean: "belum"} and services.summary_is_read(s)
    DailySummary.objects.filter(pk=s.pk).update(sent_at=timezone.now() + dt.timedelta(minutes=5))
    s.refresh_from_db()
    states = {r["user"]: r["state"] for r in services.summary_reads(s)}
    assert states[yohanes] == "lama" and not services.summary_is_read(s)


def test_owner_note_notifies_directors(jemur, yohanes, jean, hansen):
    s = _summary(hansen)
    note = services.add_summary_note(s, actor=yohanes, body="Kenapa kas Citraland selisih lagi?")
    assert DailySummaryNote.objects.get() == note
    n = Notification.objects.get(user=hansen, type_code="SUMMARY_NOTE")
    assert n.title == f"Tanggapan Summary {s.date:%d/%m}: Kenapa kas Citraland selisih lagi?"
    assert n.url == reverse("owner:summary") + f"?tanggal={s.date:%Y-%m-%d}"
    assert not Notification.objects.filter(user__in=[yohanes, jean], type_code="SUMMARY_NOTE").exists()


def test_director_note_notifies_owners(jemur, yohanes, jean, hansen):
    s = _summary(hansen)
    services.add_summary_note(s, actor=hansen, body="Sudah dicek, salah input.")
    assert set(Notification.objects.filter(type_code="SUMMARY_NOTE").values_list("user__username", flat=True)) == {
        "yohanes", "jean"}


def test_note_validation_and_permission(jemur, yohanes, hansen, yani):
    s = _summary(hansen)
    with pytest.raises(ValidationError):
        services.add_summary_note(s, actor=yohanes, body="   ")
    with pytest.raises(PermissionDenied):
        services.add_summary_note(s, actor=yani, body="Halo")
    assert not DailySummaryNote.objects.exists()
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_summary_dua_arah.py`
Expected: FAIL — `ImportError: cannot import name 'DailySummaryNote'`.

- [ ] **Step 3: Model dan migrasi**

Di `direktur/models.py`, sesudah `class DailySummary` (setelah properti `sections` dan apa pun yang mengikutinya di kelas itu):

```python
class DailySummaryRead(models.Model):
    """Kapan seorang Owner terakhir membuka summary satu tanggal (7 Okt 2026)."""

    summary = models.ForeignKey(DailySummary, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField("terakhir dibuka")

    class Meta:
        verbose_name = "tanda baca summary"
        verbose_name_plural = "tanda baca summary"
        constraints = [models.UniqueConstraint(fields=["summary", "user"], name="uniq_summary_read")]


class DailySummaryNote(models.Model):
    """Tanggapan Owner ↔ Direktur pada summary satu tanggal. Tidak diubah atau dihapus (7 Okt 2026)."""

    summary = models.ForeignKey(DailySummary, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField("tanggapan")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "tanggapan summary"
        verbose_name_plural = "tanggapan summary"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.body[:80]
```

Run: `.venv/bin/python manage.py makemigrations direktur --name summary_dua_arah`
Expected: `direktur/migrations/0007_summary_dua_arah.py` dengan dua `CreateModel`.

- [ ] **Step 4: Service di `owner/services.py`**

Tambahkan sesudah `decisions_awaiting`:

```python
# --- Summary Harian dua arah (7 Okt 2026) -------------------------------------------------


def record_summary_read(summary, user) -> None:
    """Owner membuka summary satu tanggal: catat waktunya. Direktur sendiri tidak dicatat."""
    from direktur.models import DailySummaryRead

    if summary is None or not is_owner(user) or is_aom(user):
        return
    DailySummaryRead.objects.update_or_create(summary=summary, user=user, defaults={"read_at": timezone.now()})


def summary_reads(summary) -> list[dict]:
    """Status baca tiap Owner aktif: baca, lama (sebelum dikirim ulang), atau belum."""
    reads = {r.user_id: r.read_at for r in summary.reads.all()}
    rows = []
    for owner in _owners().order_by("display_name", "username"):
        at = reads.get(owner.pk)
        state = "belum" if at is None else ("lama" if at < summary.sent_at else "baca")
        rows.append({"user": owner, "read_at": at, "state": state})
    return rows


def summary_is_read(summary) -> bool:
    return summary.reads.filter(read_at__gte=summary.sent_at).exists()


@transaction.atomic
def add_summary_note(summary, *, actor, body: str):
    """Tanggapan pada summary: Owner → semua Direktur aktif, Direktur → semua Owner aktif."""
    from django.urls import reverse

    from direktur.models import DailySummaryNote
    from notifications.services import notify_user

    if not (is_owner(actor) or is_aom(actor)):
        raise PermissionDenied("Tanggapan summary hanya dari Owner atau Direktur Operasional.")
    body = (body or "").strip()
    if not body:
        raise ValidationError("Tanggapan kosong.")
    note = DailySummaryNote.objects.create(summary=summary, author=actor, body=body)
    log_event(action=AuditAction.CREATE, entity_type="dailysummarynote", entity_id=note.pk,
              entity_label=f"Tanggapan Summary {summary.date:%d/%m/%Y}", actor=actor,
              after={"summary": summary.pk, "body": body[:300]})
    recipients = _directors() if is_owner(actor) and not is_aom(actor) else _owners()
    url = reverse("owner:summary") + f"?tanggal={summary.date:%Y-%m-%d}"
    for person in recipients.exclude(pk=actor.pk):
        notif = notify_user(person, type_code="SUMMARY_NOTE",
                            title=f"Tanggapan Summary {summary.date:%d/%m}: {body[:60]}", body=body[:200],
                            entity_ref=f"dailysummary:{summary.pk}")
        if notif is not None:
            notif.url = url
            notif.save(update_fields=["url"])
    return note
```

Pastikan `log_event` sudah diimpor dari `audit.services` di bagian atas file.

- [ ] **Step 5: Jalankan test**

Run: `.venv/bin/python -m pytest owner/tests/test_summary_dua_arah.py direktur`
Expected: semua PASS.

---

### Task 5: Summary Harian dua arah (tampilan)

**Files:**
- Modify: `owner/views.py` (`summary`)
- Modify: `templates/owner/summary.html`
- Test: `owner/tests/test_summary_dua_arah.py` (tambahkan)

**Interfaces:**
- Consumes: `services.record_summary_read`, `services.summary_reads`, `services.summary_is_read`, `services.add_summary_note` (Task 4).
- Produces: `owner:summary` menerima POST `isi`, `tanggal`.

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan ke `owner/tests/test_summary_dua_arah.py`:

```python
# --- Task 5: halaman ----------------------------------------------------------------


def test_page_records_read_and_shows_status(client, jemur, yohanes, jean, hansen):
    s = _summary(hansen)
    client.force_login(hansen)
    client.get(reverse("owner:summary"))
    assert not DailySummaryRead.objects.exists()
    client.force_login(yohanes)
    client.get(reverse("owner:summary"))
    assert DailySummaryRead.objects.filter(summary=s, user=yohanes).exists()
    client.force_login(hansen)
    body = client.get(reverse("owner:summary")).content.decode()
    assert "Dibaca dr. Yohanes" in body and "Jean belum membaca" in body


def test_post_note_and_thread(client, jemur, yohanes, hansen):
    s = _summary(hansen)
    client.force_login(yohanes)
    response = client.post(reverse("owner:summary"), {"tanggal": s.date.isoformat(), "isi": "Kenapa selisih?"})
    assert response["Location"] == reverse("owner:summary") + f"?tanggal={s.date:%Y-%m-%d}"
    client.force_login(hansen)
    client.post(reverse("owner:summary"), {"tanggal": s.date.isoformat(), "isi": "Salah input, sudah dikoreksi."})
    body = client.get(reverse("owner:summary")).content.decode()
    assert body.index("Kenapa selisih?") < body.index("Salah input, sudah dikoreksi.")
    assert "Kirim tanggapan" in body


def test_note_for_day_without_summary_is_refused(client, jemur, yohanes, hansen):
    _summary(hansen)
    client.force_login(yohanes)
    yesterday = local_today() - dt.timedelta(days=1)
    client.post(reverse("owner:summary"), {"tanggal": yesterday.isoformat(), "isi": "Halo"})
    assert not DailySummaryNote.objects.exists()


def test_staff_cannot_post_note(client, jemur, hansen, yani):
    _summary(hansen)
    client.force_login(yani)
    assert client.post(reverse("owner:summary"), {"tanggal": local_today().isoformat(), "isi": "x"}).status_code == 403
    assert not DailySummaryNote.objects.exists()


def test_recent_list_marks(client, jemur, yohanes, hansen):
    s = _summary(hansen)
    services.add_summary_note(s, actor=hansen, body="Satu")
    services.add_summary_note(s, actor=hansen, body="Dua")
    client.force_login(hansen)
    body = client.get(reverse("owner:summary")).content.decode()
    assert "belum dibaca" in body and "2 tanggapan" in body
    services.record_summary_read(s, yohanes)
    assert "belum dibaca" not in client.get(reverse("owner:summary")).content.decode()
```

- [ ] **Step 2: Jalankan dan pastikan gagal**

Run: `.venv/bin/python -m pytest owner/tests/test_summary_dua_arah.py -k "page or post_note or without_summary or staff_cannot or recent_list"`
Expected: FAIL (tanda baca tidak tercatat, POST tidak dikenali).

- [ ] **Step 3: View**

Di `owner/views.py`, tambahkan import `from django.db.models import Count` dan `from django.urls import reverse` di bagian atas. Ganti seluruh fungsi `summary` dengan:

```python
@login_required
@require(services.can_view_summary)
def summary(request):
    today = local_today()
    day = _date(request.GET.get("tanggal") or request.POST.get("tanggal"), today)
    item = DailySummary.objects.filter(date=day).select_related("sent_by").first()
    if request.method == "POST":
        if item is None:
            messages.error(request, "Belum ada summary untuk tanggal ini.")
        else:
            try:
                services.add_summary_note(item, actor=request.user, body=request.POST.get("isi", ""))
                messages.success(request, "Tanggapan dikirim.")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        return redirect(reverse("owner:summary") + f"?tanggal={day:%Y-%m-%d}")
    services.record_summary_read(item, request.user)
    recent = list(DailySummary.objects.select_related("sent_by").annotate(n_notes=Count("notes")).order_by("-date")[:14])
    for r in recent:
        r.is_read = services.summary_is_read(r)
    return render(
        request,
        "owner/summary.html",
        {
            "day": day,
            "day_label": _day_label(day),
            "summary": item,
            "reads": services.summary_reads(item) if item else [],
            "notes": list(item.notes.select_related("author")) if item else [],
            "prev": day - dt.timedelta(days=1),
            "next": day + dt.timedelta(days=1) if day < today else None,
            "today": today,
            "recent": recent,
        },
    )
```

- [ ] **Step 4: Template**

Di `templates/owner/summary.html`, sisipkan tepat sebelum `{% else %}` yang diikuti `<div class="card"><strong>Belum ada summary untuk tanggal ini.</strong>` (artinya: masih di dalam cabang `{% if summary %}`, sesudah loop `{% for s in summary.sections %}...{% endfor %}`):

```html
<h2>Dibaca</h2>
<ul class="plain-list">
  {% for r in reads %}<li>{% if r.state == 'baca' %}Dibaca {{ r.user }} {{ r.read_at|date:"d/m H.i" }}{% elif r.state == 'lama' %}{{ r.user }} membaca versi sebelumnya (sebelum {{ summary.sent_at|date:"d/m H.i" }}){% else %}{{ r.user }} belum membaca{% endif %}</li>{% endfor %}
</ul>
<h2>Tanggapan</h2>
{% if notes %}
<ul class="timeline">
  {% for n in notes %}<li><strong>{{ n.author }}</strong> <span class="meta">{{ n.created_at|date:"d/m/Y H:i" }}</span><div style="white-space:pre-wrap">{{ n.body }}</div></li>{% endfor %}
</ul>
{% else %}
<p class="meta">Belum ada tanggapan.</p>
{% endif %}
<form method="post" class="card" style="margin-top:.6rem">{% csrf_token %}
  <input type="hidden" name="tanggal" value="{{ day|date:'Y-m-d' }}">
  <label for="isi">Tulis tanggapan</label>
  <textarea id="isi" name="isi" rows="3" required placeholder="Mis. Kenapa kas Citraland selisih lagi?"></textarea>
  <p><button class="btn small" type="submit">Kirim tanggapan</button></p>
</form>
```

Ganti isi loop chip "Summary terakhir":

```html
  {% for r in recent %}<a class="chip{% if r.date == day %} chip-on{% endif %}" href="?tanggal={{ r.date|date:'Y-m-d' }}">{{ r.date|date:"d/m" }}{% if not r.is_read %} · belum dibaca{% endif %}{% if r.n_notes %} · {{ r.n_notes }} tanggapan{% endif %}</a>{% endfor %}
```

- [ ] **Step 5: Jalankan test**

Run: `.venv/bin/python -m pytest owner`
Expected: semua PASS, termasuk `owner/tests/test_owner.py::test_summary_empty_then_filled` dan `test_summary_access`.

---

### Task 6: Dokumentasi

**Files:**
- Modify: `docs/panduan-owner.md`, `docs/panduan-direktur.md`, `docs/peran-dan-akses.md`

- [ ] **Step 1: Cari bagian terkait**

Run: `grep -n -i "keputusan\|summary harian\|teruskan\|diteruskan" docs/panduan-owner.md docs/panduan-direktur.md docs/peran-dan-akses.md`

- [ ] **Step 2: Perbarui**

- `docs/panduan-owner.md`: kartu "Menunggu keputusan Anda" di Dashboard; halaman keputusan dengan Setujui (catatan opsional), Tolak (alasan wajib), Bahas di rapat Kamis; siapa saja yang berperan Owner boleh memutuskan dan keputusan pertama yang berlaku; Summary Harian: waktu buka tercatat sebagai tanda baca untuk Direktur, dan Owner dapat menulis tanggapan yang diteruskan ke Direktur.
- `docs/panduan-direktur.md`: "Teruskan → Direktur Utama / Owner" di Inbox membuat perkara Keputusan berpemutus Owner dan memberi tahu Owner; perkara berpemutus Owner/Direktur Utama dari halaman Keputusan juga memberi tahu Owner; Direktur diberi tahu hasil keputusan Owner lalu dapat membuat task tindak lanjut; Summary Harian menampilkan siapa sudah membaca (dan "versi sebelumnya" bila dikirim ulang) serta utas tanggapan.
- `docs/peran-dan-akses.md`: tambahkan baris tabel "Memutuskan permintaan keputusan berpemutus Owner/Direktur Utama | owner (siapa saja), keputusan pertama berlaku | —" dan "Menulis tanggapan Summary Harian | owner, AOM | —"; pada baris Inbox owner tetap "baca saja".

- [ ] **Step 3: Test dokumentasi**

Run: `.venv/bin/python -m pytest core/tests/test_documentation.py`
Expected: PASS.

---

### Task 7: Verifikasi menyeluruh, uji UI, laporan (controller)

- [ ] **Step 1:** Seluruh test: `.venv/bin/python -m pytest 2>&1 | grep -E "passed|failed" | tail -1` (baseline sesudah tahap 1: 956 passed). Abaikan satu-satunya kegagalan dikenal `stok/tests/test_tanpa_harga.py::test_order_page_shows_action_without_price_or_supplier` hanya bila lulus saat diulang.
- [ ] **Step 2:** `.venv/bin/python manage.py makemigrations --check --dry-run` → "No changes detected"; `manage.py check` bersih.
- [ ] **Step 3:** Migrasi salinan database uji worktree: `DJANGO_DB_PATH=data/uitest.sqlite3 .venv/bin/python manage.py migrate` → `direktur.0006`, `direktur.0007` OK.
- [ ] **Step 4:** Uji UI (desktop dan HP 375 px) dengan akun uji: staf kirim laporan → Direktur teruskan ke Owner → Owner diberi tahu, kartu dashboard, Setujui dengan catatan → Direktur diberi tahu, buat task tindak lanjut; ulangi Tolak dan Bahas di rapat (muncul di agenda rapat); Direktur kirim Summary Harian → Owner buka dan menanggapi → Direktur lihat "Dibaca" dan membalas → Owner diberi tahu.
- [ ] **Step 5:** Laporkan ke product owner (file berubah, test, temuan UI, risiko, approval yang diperlukan). **Berhenti sampai disetujui**, lalu commit di branch `arus-balik`, merge ke `master`, push, deploy hanya atas izin.
