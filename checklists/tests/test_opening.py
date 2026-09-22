"""Test checklist: validasi respons, review, dan turunan tindak lanjut."""
import pytest
from django.core.exceptions import ValidationError

from checklists.models import ChecklistResponse, ResponseResult, RunStatus
from checklists.services import (
    create_action_item_from_response,
    create_damage_from_response,
    record_response,
    review_run,
    run_progress,
)
from core.models import ActionItem
from issues.models import Issue, IssueType

pytestmark = pytest.mark.django_db


def _get(day, label):
    return ChecklistResponse.objects.get(run__operational_day=day, label=label)


def test_note_required_when_not_ok(day, kasir):
    r = _get(day, "Alat lengkap")
    with pytest.raises(ValidationError) as exc:
        record_response(r, user=kasir, result=ResponseResult.RUSAK, note="")
    assert "catatan" in " ".join(exc.value.messages).lower()


def test_quantity_required_and_non_negative(day, kasir):
    r = _get(day, "Sarung tangan")
    with pytest.raises(ValidationError):
        record_response(r, user=kasir, result=ResponseResult.OK, quantity=None)
    with pytest.raises(ValidationError):
        record_response(r, user=kasir, result=ResponseResult.OK, quantity=-3)
    record_response(r, user=kasir, result=ResponseResult.OK, quantity=25)
    r.refresh_from_db()
    assert r.quantity == 25 and r.checked_by == kasir and r.checked_at is not None


def test_below_minimum_flag(day, kasir):
    r = _get(day, "Sarung tangan")
    record_response(
        r, user=kasir, result=ResponseResult.TIDAK_LENGKAP, quantity=5, note="stok menipis"
    )
    r.refresh_from_db()
    assert r.below_minimum is True


def test_optimistic_locking_rejects_stale_update(day, kasir):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.OK)
    with pytest.raises(ValidationError) as exc:
        record_response(r, user=kasir, result=ResponseResult.OK, expected_version=1)
    assert "pengguna lain" in " ".join(exc.value.messages).lower()


def test_review_requires_exception_reason(day, kasir, supervisor):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.RUSAK, note="lampu mati")
    run = r.run

    with pytest.raises(ValidationError):
        review_run(run, supervisor)
    with pytest.raises(ValidationError):
        review_run(run, supervisor, accept_with_exception=True, reason="")

    review_run(run, supervisor, accept_with_exception=True, reason="Alat cadangan tersedia")
    run.refresh_from_db()
    assert run.status == RunStatus.DITERIMA_DENGAN_CATATAN


def test_damage_report_from_broken_item(day, kasir):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.RUSAK, note="dermatoskop mati")
    issue = create_damage_from_response(r, kasir)
    assert issue.issue_type == IssueType.KERUSAKAN
    assert issue.number.startswith("DMG-")
    assert Issue.objects.count() == 1


def test_damage_report_rejected_for_ok_item(day, kasir):
    r = _get(day, "Alat lengkap")
    record_response(r, user=kasir, result=ResponseResult.OK)
    with pytest.raises(ValidationError):
        create_damage_from_response(r, kasir)


def test_action_item_from_incomplete(day, kasir):
    r = _get(day, "Sarung tangan")
    record_response(r, user=kasir, result=ResponseResult.TIDAK_LENGKAP, quantity=3, note="sisa 3")
    item = create_action_item_from_response(r, kasir)
    assert ActionItem.objects.filter(pk=item.pk, source_type="checklistresponse").exists()


def test_run_progress_counts(day, kasir):
    progress = run_progress(_get(day, "Alat lengkap").run)
    assert progress["total"] == 3 and progress["done"] == 0
    assert len(progress["required_pending"]) == 2
