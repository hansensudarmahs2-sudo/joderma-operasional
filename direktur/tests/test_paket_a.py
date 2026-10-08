"""Paket A permintaan Owner (Oktober 2026): pelapor di task, Daftar Task, keputusan bersama (K-015)."""
from __future__ import annotations

import datetime as dt
import re

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User, UserRole
from audit.models import AuditAction, AuditEvent
from core.models import ActionItem, ActionItemStatus, Clinic, Priority, TaskAudienceType, TaskEvent
from core.task_services import create_task, submit_assignment
from direktur import dashboard, services, task_list
from direktur.models import Decider, DecisionStatus
from notifications.models import Notification

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


@pytest.fixture
def jemur(db):
    return Clinic.objects.create(code="jemur-andayani", name="Jemur Andayani")


@pytest.fixture
def citraland(db):
    return Clinic.objects.create(code="JC", name="Joderma Citraland")


@pytest.fixture
def people(jemur, citraland):
    return {
        "hansen": _user(jemur, "hansen1", Role.AOM),
        "yohanes": _user(jemur, "yohanes", Role.OWNER),
        "heni": _user(jemur, "heni", Role.SUPERVISOR, Role.PERAWAT, Role.STAF),
        "yani": _user(jemur, "yani", Role.PERAWAT, Role.STAF),
        "regita": _user(citraland, "regita", Role.SUPERVISOR, Role.STAF),
    }


def _task(clinic, actor, title, to, **kw):
    return create_task(clinic=clinic, actor=actor, title=title, audience_type=TaskAudienceType.USER,
                       user_ids=[to.pk], **kw)


# --- Butir 4: pelapor ----------------------------------------------------------

def test_reporter_comes_from_source(jemur, people):
    from owner.services import create_request

    hansen = people["hansen"]
    note = services.create_note(author=hansen, body="Wastafel lantai 2 mampet", clinic=jemur)
    from_note = services.convert_note(note, user=hansen, clinic=jemur, title="Perbaiki wastafel",
                                      target=f"user:{people['yani'].pk}")
    req = create_request(actor=people["yohanes"], title="Rapikan ruang tunggu",
                         target_date=dt.date.today() + dt.timedelta(days=7))
    from_owner = ActionItem.objects.create(clinic=jemur, title="Rapikan kursi", source_type="permintaan_owner",
                                           source_id=req.pk, created_by=hansen)
    manual = _task(jemur, hansen, "Cek APAR", people["heni"])
    who = dashboard.reporters([from_note, from_owner, manual])
    assert who[from_note.pk] == hansen and who[from_owner.pk] == people["yohanes"] and who[manual.pk] == hansen


def test_reporter_shown_on_card_detail_and_list(client, jemur, people):
    from owner.services import create_request

    req = create_request(actor=people["yohanes"], title="Rapikan ruang tunggu",
                         target_date=dt.date.today() + dt.timedelta(days=7))
    item = _task(jemur, people["hansen"], "Rapikan kursi tunggu", people["yani"], source_type="permintaan_owner",
                 source_id=req.pk)
    client.force_login(people["hansen"])
    kanban = client.get(reverse("direktur:kanban")).content.decode()
    assert "Pelapor: Yohanes" in kanban and "PIC: Yani" in kanban
    detail = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "pelapor <strong>Yohanes</strong>" in detail
    listing = client.get(reverse("direktur:tasks")).content.decode()
    assert "Rapikan kursi tunggu" in listing and "Yohanes" in listing and "Permintaan Owner" in listing


# --- Butir 5: Daftar Task -------------------------------------------------------

@pytest.fixture
def many(jemur, citraland, people):
    h = people["hansen"]
    now = timezone.now()
    a = _task(jemur, h, "Ganti lampu lobi", people["heni"], priority=Priority.TINGGI,
              due_at=now - dt.timedelta(days=1))
    b = _task(jemur, h, "Isi ulang APAR", people["yani"], priority=Priority.RENDAH,
              due_at=now + dt.timedelta(days=3))
    c = _task(citraland, h, "Rapikan rak obat", people["regita"], priority=Priority.KRITIS)
    d = _task(jemur, h, "Laporan limbah", people["yani"])
    d.status = ActionItemStatus.SELESAI
    d.save()
    submit_assignment(b.task_assignments.get(), user=people["yani"], note="sudah")
    return {"a": a, "b": b, "c": c, "d": d}


def _titles(user, **params):
    return [r["item"].title for r in task_list.rows(user, task_list.parse_filters(params))]


def test_list_filters(people, many, citraland):
    h = people["hansen"]
    assert set(_titles(h)) == {"Ganti lampu lobi", "Isi ulang APAR", "Rapikan rak obat"}  # default: terbuka
    assert _titles(h, status="selesai") == ["Laporan limbah"]
    assert len(_titles(h, status="semua")) == 4
    assert _titles(h, status="lewat") == ["Ganti lampu lobi"]
    assert _titles(h, status="menunggu") == ["Isi ulang APAR"]
    assert _titles(h, cabang=str(citraland.pk)) == ["Rapikan rak obat"]
    assert _titles(h, pic=str(people["yani"].pk)) == ["Isi ulang APAR"]
    assert _titles(h, prioritas="KRITIS") == ["Rapikan rak obat"]
    assert _titles(h, q="apar") == ["Isi ulang APAR"]
    assert _titles(h, q="regita") == ["Rapikan rak obat"]  # cari nama PIC
    # Nilai liar diabaikan, bukan galat.
    assert len(_titles(h, status="xx", cabang="abc", prioritas="zz", urut="hapus")) == 3


def test_list_sorting(people, many):
    h = people["hansen"]
    assert _titles(h, urut="prioritas") == ["Rapikan rak obat", "Ganti lampu lobi", "Isi ulang APAR"]
    assert _titles(h, urut="-prioritas")[0] == "Isi ulang APAR"
    assert _titles(h, urut="target")[:2] == ["Ganti lampu lobi", "Isi ulang APAR"]  # tanpa target di akhir
    assert _titles(h, urut="judul") == sorted(_titles(h, urut="judul"))


def test_list_page_and_csv(client, people, many):
    client.force_login(people["hansen"])
    body = client.get(reverse("direktur:tasks"), {"urut": "prioritas"}).content.decode()
    assert "3 task" in body and "Prioritas ↑" in body and "urut=-prioritas" in body
    res = client.get(reverse("direktur:tasks"), {"unduh": "csv", "status": "semua"})
    text = b"".join(res.streaming_content).decode("utf-8")
    assert res["Content-Type"].startswith("text/csv") and text.startswith("﻿")
    assert "Laporan limbah" in text and "Pelapor" in text and text.count("\n") == 5
    assert AuditEvent.objects.filter(action=AuditAction.EXPORT, entity_type="actionitem").exists()


def test_list_access(client, people, many):
    client.force_login(people["yohanes"])
    body = client.get(reverse("direktur:tasks")).content.decode()
    assert "Ganti lampu lobi" in body and "Tampilan baca saja" in body and "+ Task baru" not in body
    assert 'href="/direktur/daftar/" class="active" aria-current="page">Daftar Task</a>' in body
    for who in ("heni", "yani", "regita"):
        client.force_login(people[who])
        assert client.get(reverse("direktur:tasks")).status_code in (302, 403)
    with pytest.raises(PermissionDenied):
        task_list.rows(people["yani"], task_list.parse_filters({}))


def test_list_search_in_popup_and_start_column(client, people, many, citraland):
    """8 Okt 2026: cari dan saringan di pop up (tombol Cari di sebelah judul); kolom Mulai di sebelah Target."""
    client.force_login(people["hansen"])
    body = client.get(reverse("direktur:tasks")).content.decode()
    head = body.split('<dialog id="cari-task"', 1)[0]
    assert 'id="buka-cari"' in head and 'name="q"' not in head  # kotak cari tidak lagi di halaman
    dialog = body.split('<dialog id="cari-task"', 1)[1].split("</dialog>", 1)[0]
    assert 'name="q"' in dialog and 'name="status"' in dialog and 'name="dari"' in dialog and "Terapkan" in dialog
    assert "Saringan:" not in body  # tanpa saringan aktif tidak ada ringkasan
    heads = re.findall(r'class="sort[^"]*">([A-Za-z]+)', body)
    assert heads[heads.index("Target") - 1] == "Mulai"
    created = timezone.localtime(many["a"].created_at).strftime("%d/%m/%Y")
    assert f'<td data-label="Mulai">{created}</td>' in body
    assert _titles(people["hansen"], urut="dibuat")  # urut menurut tanggal mulai tetap berjalan

    body = client.get(reverse("direktur:tasks"), {"q": "apar", "cabang": citraland.pk, "prioritas": "KRITIS"}).content.decode()
    summary = body.split('class="filter-summary"', 1)[1].split("</p>", 1)[0]
    assert "Cari: “apar”" in summary and citraland.name in summary and "Prioritas Kritis" in summary
    assert "Hapus saringan" in summary and "Cari (3)" in body


# --- Butir 6: keputusan bersama (K-015) ---------------------------------------------

def test_next_meeting_is_thursday():
    assert dashboard.next_meeting(dt.date(2026, 10, 3)) == dt.date(2026, 10, 8)  # Sabtu -> Kamis
    assert dashboard.next_meeting(dt.date(2026, 10, 8)) == dt.date(2026, 10, 8)  # Kamis itu sendiri
    assert dashboard.next_meeting(dt.date(2026, 10, 9)) == dt.date(2026, 10, 15)


def test_hold_freezes_deadline_and_settle_notifies(jemur, people):
    h = people["hansen"]
    item = _task(jemur, h, "Pindah lokasi limbah", people["yani"], due_at=timezone.now() - dt.timedelta(days=2))
    assert item.is_overdue
    decision = services.bring_to_meeting(item, actor=h, title="Lokasi penampungan limbah baru")
    item.refresh_from_db()
    assert decision.decider == Decider.RAPAT_BERSAMA and item.on_hold and not item.is_overdue
    assert dashboard.headline_counts(h)["overdue"] == 0
    assert TaskEvent.objects.filter(action_item=item, note__startswith="Ditahan").exists()
    agenda = dashboard.meeting_agenda(h)
    assert [r["decision"] for r in agenda["rapat"]] == [decision] and agenda["rapat"][0]["tasks"] == [item]

    services.settle_decision(decision, actor=h, decision_text="Pindah ke gudang belakang")
    item.refresh_from_db()
    assert not item.on_hold and item.is_overdue  # tenggat berjalan lagi
    note = Notification.objects.get(user=people["yani"], type_code="TASK_DECISION")
    assert "Pindah lokasi limbah" in note.title and "gudang belakang" in note.body
    # Memperbarui isi keputusan tidak mengirim pemberitahuan ganda.
    services.settle_decision(decision, actor=h, decision_text="Pindah ke gudang belakang, rak 2")
    assert TaskEvent.objects.filter(action_item=item, metadata__released="ditetapkan").count() == 1
    assert dashboard.meeting_agenda(h)["rapat"] == []


def test_hold_rules(jemur, citraland, people):
    h = people["hansen"]
    item = _task(jemur, h, "Atur ulang jadwal piket", people["yani"])
    other = services.create_decision(actor=h, title="Perkara Citraland", decider=Decider.OWNER, clinic=citraland)
    with pytest.raises(ValidationError):
        services.hold_task(item, other, actor=h)
    shared = services.create_decision(actor=h, title="Aturan seragam", decider=Decider.RAPAT_BERSAMA)
    with pytest.raises(PermissionDenied):
        services.hold_task(item, shared, actor=people["heni"])
    services.hold_task(item, shared, actor=h)
    services.hold_task(item, shared, actor=h)  # dua kali tidak menggandakan
    assert shared.waiting_tasks.count() == 1
    services.release_task(item, shared, actor=h)
    assert not ActionItem.objects.get(pk=item.pk).on_hold
    services.cancel_decision(shared, actor=h, reason="tidak relevan")
    with pytest.raises(ValidationError):
        services.hold_task(item, shared, actor=h)


def test_task_detail_hold_flow(client, jemur, people):
    h = people["hansen"]
    item = _task(jemur, h, "Pasang rak sepatu", people["yani"])
    client.force_login(h)
    page = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "Bawa ke rapat dan tahan task" in page
    client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "rapat", "perkara": "Anggaran rak"})
    decision = item.waiting_decisions.get()
    assert decision.title == "Anggaran rak" and decision.clinic == jemur
    page = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "Menunggu keputusan" in page and "tenggat task dibekukan" in page
    client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "lepas", "keputusan": decision.pk})
    assert not item.waiting_decisions.exists()
    client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "tahan", "keputusan": decision.pk})
    assert item.waiting_decisions.exists()
    # Owner membaca, tidak dapat menahan.
    client.force_login(people["yohanes"])
    page = client.get(reverse("direktur:task_detail", args=[item.pk])).content.decode()
    assert "Bawa ke rapat" not in page and "Anggaran rak" in page
    client.post(reverse("direktur:task_detail", args=[item.pk]), {"aksi": "lepas", "keputusan": decision.pk})
    assert item.waiting_decisions.exists()


def test_home_pages_show_agenda(client, jemur, people):
    h = people["hansen"]
    item = _task(jemur, h, "Perbaiki AC", people["yani"])
    services.bring_to_meeting(item, actor=h, title="Ganti vendor AC")
    services.create_decision(actor=h, title="Harga paket baru", decider=Decider.DIRUT)
    for who, url in (("hansen", "direktur:overview"), ("yohanes", "owner:dashboard")):
        client.force_login(people[who])
        body = client.get(reverse(url)).content.decode()
        assert 'id="agenda-rapat"' in body and "Agenda rapat Kamis" in body, who
        assert "Ganti vendor AC" in body and "Task tertahan" in body and "Perbaiki AC" in body
        assert "1 perkara lain menunggu pemutus lain" in body and "Harga paket baru" in body


def test_follow_up_task_from_decision(client, jemur, people):
    h = people["hansen"]
    decision = services.create_decision(actor=h, title="Jam buka Minggu", decider=Decider.RAPAT_BERSAMA,
                                        clinic=jemur)
    with pytest.raises(ValidationError):
        services.create_manual_task(actor=h, clinic=jemur, title="x", target=f"user:{people['yani'].pk}",
                                    decision=decision)
    services.settle_decision(decision, actor=h, decision_text="Buka 09.00 mulai November")
    client.force_login(h)
    form = client.get(reverse("direktur:task_new"), {"keputusan": decision.pk}).content.decode()
    assert "Tindak lanjut: Jam buka Minggu" in form and "Buka 09.00 mulai November" in form
    res = client.post(reverse("direktur:task_new"), {
        "keputusan": decision.pk, "cabang": jemur.pk, "judul": "Umumkan jam buka baru",
        "uraian": "Buka 09.00", "penerima": f"user:{people['heni'].pk}", "prioritas": "SEDANG"})
    assert res.status_code == 302 and res.url == reverse("direktur:decision_detail", args=[decision.pk])
    task = ActionItem.objects.get(title="Umumkan jam buka baru")
    assert task.source_type == "keputusan" and task.source_id == decision.pk
    page = client.get(reverse("direktur:decision_detail", args=[decision.pk])).content.decode()
    assert "Umumkan jam buka baru" in page and "Buat task tindak lanjut" in page
    assert DecisionStatus.DITETAPKAN == decision.status
