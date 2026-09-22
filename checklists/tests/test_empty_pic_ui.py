"""Fase 5: PIC kosong menghasilkan pesan dapat dipahami di VIEW layer (plan 13/14).

Fase 1/2 sudah melempar ValidationError server-side saat target PIC kosong
(lihat core.task_services.resolve_task_recipients dan
checklists.services.resolve_followup_audience). Test ini membuktikan VIEW
yang memicu jalur tersebut (checklists.views.make_action_item) menampilkan
pesan ramah lewat Django messages, bukan crash 500.
"""
from __future__ import annotations

import pytest
from django.urls import reverse

from checklists.models import ChecklistArea, ChecklistSession, ChecklistResponse, ResponseResult
from checklists.services import create_template_version, record_response
from core.services import get_or_create_day
from accounts.models import PicFunction

pytestmark = pytest.mark.django_db


def test_make_action_item_view_shows_friendly_message_for_empty_pic_function(
    client, clinic, supervisor
):
    """Template menargetkan fungsi PIC yang belum ada penugasannya (mis. Citraland kosong)."""
    create_template_version(
        clinic=clinic,
        area=ChecklistArea.AKSES_UMUM,
        session=ChecklistSession.OPENING,
        name="Akses umum",
        items=[{"label": "Cek pintu darurat"}],
        user=supervisor,
        target_pic_function=PicFunction.CASHIER,  # belum ada PicAssignment aktif untuk fungsi ini
    )
    day, _ = get_or_create_day(clinic, date="2026-09-24", user=supervisor)
    response = ChecklistResponse.objects.get(
        run__operational_day=day, run__area=ChecklistArea.AKSES_UMUM, label="Cek pintu darurat"
    )
    record_response(response, user=supervisor, result=ResponseResult.RUSAK, note="terkunci")

    client.login(username="supervisor", password="TestPassword123!")
    resp = client.post(reverse("checklists:make_action", args=[response.pk]))

    # Tidak crash (500); redirect kembali ke halaman run dengan pesan error ramah,
    # bukan exception yang bocor ke pengguna.
    assert resp.status_code == 302
    followed = client.get(resp.url)
    assert followed.status_code == 200
    body = followed.content.decode()
    assert "tidak ada penerima" in body.lower()
