"""Fase 3: koreksi respons checklist wajib beralasan + audit trail (PRD 8.1)."""
from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from audit.models import AuditAction, AuditEvent
from checklists.models import ChecklistResponse, ResponseResult
from checklists.services import record_response

pytestmark = pytest.mark.django_db


def _get(day, label):
    return ChecklistResponse.objects.get(run__operational_day=day, label=label)


def test_first_time_recording_does_not_require_reason(day, kasir):
    r = _get(day, "Alat lengkap")
    assert r.result == ResponseResult.BELUM

    record_response(r, user=kasir, result=ResponseResult.OK)
    r.refresh_from_db()

    assert r.result == ResponseResult.OK
    events = AuditEvent.objects.filter(entity_type="checklistresponse", entity_id=str(r.pk))
    assert events.filter(action=AuditAction.UPDATE).exists()
    assert not events.filter(action=AuditAction.CORRECTION).exists()


def test_correction_after_checked_requires_reason(day, kasir):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.OK)
    r.refresh_from_db()

    with pytest.raises(ValidationError) as exc:
        record_response(r, user=kasir, result=ResponseResult.RUSAK, note="ternyata rusak")
    assert "alasan" in " ".join(exc.value.messages).lower()

    # Data tidak boleh tertimpa diam-diam bila alasan tidak diberikan.
    r.refresh_from_db()
    assert r.result == ResponseResult.OK


def test_correction_with_reason_creates_correction_audit_event(day, kasir):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.OK)
    r.refresh_from_db()
    version_after_first = r.version

    record_response(
        r,
        user=kasir,
        result=ResponseResult.RUSAK,
        note="ternyata rusak setelah dicek ulang",
        reason="Ditemukan kerusakan setelah pemeriksaan awal keliru.",
    )
    r.refresh_from_db()

    assert r.result == ResponseResult.RUSAK
    assert r.version == version_after_first + 1

    correction_events = AuditEvent.objects.filter(
        entity_type="checklistresponse", entity_id=str(r.pk), action=AuditAction.CORRECTION
    )
    assert correction_events.count() == 1
    event = correction_events.first()
    assert event.reason == "Ditemukan kerusakan setelah pemeriksaan awal keliru."
    assert event.before_json["result"] == ResponseResult.OK
    assert event.after_json["result"] == ResponseResult.RUSAK


def test_correction_reason_cannot_be_blank_whitespace(day, kasir):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.OK)
    r.refresh_from_db()

    with pytest.raises(ValidationError):
        record_response(
            r, user=kasir, result=ResponseResult.TIDAK_LENGKAP, note="kurang", reason="   "
        )


def test_multiple_corrections_each_produce_distinct_audit_event(day, kasir):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.OK)
    r.refresh_from_db()

    record_response(
        r,
        user=kasir,
        result=ResponseResult.TIDAK_LENGKAP,
        note="kurang lengkap",
        reason="Ada alat yang belum tersedia saat dicek ulang.",
    )
    r.refresh_from_db()

    record_response(
        r,
        user=kasir,
        result=ResponseResult.OK,
        note="sudah lengkap",
        reason="Alat sudah dilengkapi.",
    )
    r.refresh_from_db()

    correction_events = AuditEvent.objects.filter(
        entity_type="checklistresponse", entity_id=str(r.pk), action=AuditAction.CORRECTION
    )
    assert correction_events.count() == 2
