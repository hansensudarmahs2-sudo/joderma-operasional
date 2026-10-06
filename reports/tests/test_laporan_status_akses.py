"""Siapa yang boleh mengubah status Laporan staf (7 Okt 2026): supervisor, PIC, Direktur Operasional."""
import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from accounts.models import Role, User, UserRole
from reports.models import ReportStatus
from reports.services import change_laporan_status, create_laporan

pytestmark = pytest.mark.django_db


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password="TestPassword123!", display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _laporan(clinic, user):
    return create_laporan(clinic=clinic, user=user, title="Tissue habis tiap Sabtu", description="Usul tambah stok.")


@pytest.mark.parametrize("who", ["pelapor", "staf_lain", "owner"])
def test_staff_reporter_and_owner_cannot_change_laporan_status(clinic, staf, who):
    laporan = _laporan(clinic, staf)
    actor = {"pelapor": staf, "staf_lain": _user(clinic, "yani", Role.STAF),
             "owner": _user(clinic, "yohanes", Role.OWNER)}[who]
    with pytest.raises(PermissionDenied):
        change_laporan_status(laporan, user=actor, to_status=ReportStatus.UNDER_REVIEW)
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.OPEN


@pytest.mark.parametrize("roles", [(Role.SUPERVISOR,), (Role.PIC, Role.FRONT_DESK), (Role.AOM,)])
def test_supervisor_pic_and_director_can_change_laporan_status(clinic, staf, roles):
    laporan = _laporan(clinic, staf)
    change_laporan_status(laporan, user=_user(clinic, "penangan", *roles), to_status=ReportStatus.UNDER_REVIEW)
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.UNDER_REVIEW


def test_handler_of_other_branch_cannot_change_laporan_status(clinic, clinic_b, staf):
    laporan = _laporan(clinic, staf)
    with pytest.raises(PermissionDenied):
        change_laporan_status(laporan, user=_user(clinic_b, "sup_b", Role.SUPERVISOR),
                              to_status=ReportStatus.UNDER_REVIEW)


def test_page_post_by_plain_staff_is_refused_and_stays_untriaged(client, clinic, staf):
    from reports.inbox import inbox_rows

    laporan = _laporan(clinic, staf)
    director = _user(clinic, "hansen1", Role.AOM)
    client.force_login(_user(clinic, "yani", Role.STAF))
    client.post(reverse("reports:laporan_page_detail", args=[laporan.pk]),
                {"status": ReportStatus.RESOLVED, "catatan": "beres"})
    assert client.post(reverse("reports:laporan_status", args=[laporan.pk]),
                       {"status": ReportStatus.RESOLVED}).status_code == 403
    laporan.refresh_from_db()
    assert laporan.status == ReportStatus.OPEN
    assert [r for r in inbox_rows(director, state="belum") if r["source_id"] == laporan.pk]


def test_status_form_hidden_from_plain_staff(client, clinic, staf, supervisor):
    laporan = _laporan(clinic, staf)
    url = reverse("reports:laporan_page_detail", args=[laporan.pk])
    client.force_login(staf)
    assert 'name="status"' not in client.get(url).content.decode()
    client.force_login(supervisor)
    assert 'name="status"' in client.get(url).content.decode()
