"""Leader/co-leader yang juga penerima task project-nya boleh selesai tanpa bukti (keputusan PO 14 Okt 2026).

Sebabnya: hasil kerja leader sering berupa tangkapan layar situs dsb., bukan foto. Tanpa bukti hanya
diteruskan sesudah peringatan dilewati (``tanpa_bukti=1``), sama dengan Tandai selesai milik pengatur.
Penerima biasa, dan Owner/Direktur yang tidak memimpin project itu, tetap wajib bukti.
"""
from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from accounts.models import Role, User, UserRole
from core.models import Clinic, TaskAssignmentMode, TaskAssignmentStatus, TaskEvent, TaskEventType
from core.views import LEADER_NO_EVIDENCE, NO_EVIDENCE_WARNING
from projects import services as ps

pytestmark = pytest.mark.django_db
PASSWORD = "TestPassword123!"
REQUIRED = "Selesai — lampirkan bukti (wajib)"
OPTIONAL = "Tetap tandai selesai tanpa bukti"


def _user(clinic, name, *roles):
    u = User.objects.create_user(username=name, password=PASSWORD, display_name=name.title())
    for r in roles:
        UserRole.objects.create(user=u, clinic=clinic, role=r)
    return u


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 30)).save(buf, format="PNG")
    return SimpleUploadedFile("bukti.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def clinic(db):
    return Clinic.objects.create(code="jemur", name="Jemur", open_time="14:00", close_time="22:00")


@pytest.fixture
def aom1(clinic):
    return _user(clinic, "aom1", Role.AOM)


@pytest.fixture
def sa(clinic):
    return _user(clinic, "staf_a", Role.STAF)


@pytest.fixture
def sb(clinic):
    return _user(clinic, "staf_b", Role.STAF)


@pytest.fixture
def sc(clinic):
    return _user(clinic, "staf_c", Role.STAF)


@pytest.fixture
def project(aom1, sa, sb):
    """Dibuat aom1; leader staf A; co-leader staf B."""
    return ps.create_project(actor=aom1, name="Website klinik", leader=sa, co_leaders=[sb])


def _assignment(project, actor, user):
    item = ps.add_task(project, actor=actor, title="Perbarui halaman layanan", user_ids=[user.pk],
                       mode=TaskAssignmentMode.INDIVIDUAL)
    return item.task_assignments.get(assignee=user)


def _submit(client, user, assignment, **data):
    client.force_login(user)
    res = client.post(reverse("core:assignment_submit", args=[assignment.pk]), data, follow=True)
    assignment.refresh_from_db()
    return [str(m) for m in res.context["messages"]]


@pytest.mark.parametrize("who", ["sa", "sb"])
def test_leader_and_co_leader_may_finish_without_evidence_after_warning(client, request, project, aom1, who):
    user = request.getfixturevalue(who)
    a = _assignment(project, aom1, user)
    msgs = _submit(client, user, a, catatan="Sudah tayang")
    assert NO_EVIDENCE_WARNING in msgs and a.status == TaskAssignmentStatus.OPEN
    msgs = _submit(client, user, a, catatan="Sudah tayang", tanpa_bukti="1")
    assert a.status == TaskAssignmentStatus.CONFIRMED, msgs
    note = TaskEvent.objects.get(assignment=a, event_type=TaskEventType.SUBMITTED).note
    assert note == f"Sudah tayang · {LEADER_NO_EVIDENCE}"


def test_leader_note_optional(client, project, aom1, sa):
    a = _assignment(project, aom1, sa)
    _submit(client, sa, a, tanpa_bukti="1")
    assert a.status == TaskAssignmentStatus.CONFIRMED
    assert TaskEvent.objects.get(assignment=a, event_type=TaskEventType.SUBMITTED).note == LEADER_NO_EVIDENCE


def test_leader_with_evidence_has_no_extra_note(client, project, aom1, sa):
    a = _assignment(project, aom1, sa)
    _submit(client, sa, a, catatan="Tangkapan layar", foto=_png())
    assert a.status == TaskAssignmentStatus.CONFIRMED
    assert TaskEvent.objects.get(assignment=a, event_type=TaskEventType.SUBMITTED).note == "Tangkapan layar"


def test_plain_recipient_still_needs_evidence(client, project, aom1, sc):
    a = _assignment(project, aom1, sc)
    msgs = _submit(client, sc, a, catatan="Sudah", tanpa_bukti="1")
    assert "Bukti wajib: lampirkan foto atau dokumen." in msgs and a.status == TaskAssignmentStatus.OPEN


def test_leader_of_another_project_still_needs_evidence(client, aom1, sa, sc, project):
    other = ps.create_project(actor=aom1, name="Rak gudang", leader=sc)
    a = _assignment(other, aom1, sa)
    msgs = _submit(client, sa, a, tanpa_bukti="1")
    assert "Bukti wajib: lampirkan foto atau dokumen." in msgs and a.status == TaskAssignmentStatus.OPEN


def test_project_creator_direktur_not_leader_still_needs_evidence(client, project, aom1):
    a = _assignment(project, aom1, aom1)  # aom1 membuat project tetapi bukan leader/co-leader
    msgs = _submit(client, aom1, a, tanpa_bukti="1")
    assert "Bukti wajib: lampirkan foto atau dokumen." in msgs and a.status == TaskAssignmentStatus.OPEN


def test_leads_item_project(project, aom1, sa, sb, sc):
    item = _assignment(project, aom1, sc).action_item
    assert ps.leads_item_project(sa, item) and ps.leads_item_project(sb, item)
    assert not ps.leads_item_project(sc, item) and not ps.leads_item_project(aom1, item)


def test_staff_card_shows_optional_form_only_for_leader(client, project, aom1, sa, sc):
    _assignment(project, aom1, sa)
    _assignment(project, aom1, sc)
    client.force_login(sa)
    body = client.get(reverse("core:today")).content.decode()
    assert OPTIONAL in body and REQUIRED not in body
    client.force_login(sc)
    body = client.get(reverse("core:today")).content.decode()
    assert REQUIRED in body and OPTIONAL not in body


def test_owner_leader_card_and_submit(client, clinic, aom1):
    owner = _user(clinic, "owner1", Role.OWNER)
    proj = ps.create_project(actor=aom1, name="Profil Google", leader=owner)
    a = _assignment(proj, aom1, owner)
    client.force_login(owner)
    body = client.get(reverse("owner:dashboard")).content.decode()
    assert OPTIONAL in body and REQUIRED not in body
    client.post(reverse("projects:my_submit", args=[a.pk]), {"tanpa_bukti": "1"})
    a.refresh_from_db()
    assert a.status == TaskAssignmentStatus.CONFIRMED


def test_direktur_task_detail_optional_for_leader(client, clinic, aom1, sa):
    proj = ps.create_project(actor=aom1, name="Sistem antrean", leader=aom1)
    a = _assignment(proj, aom1, aom1)
    client.force_login(aom1)
    body = client.get(reverse("direktur:task_detail", args=[a.action_item.pk])).content.decode()
    assert OPTIONAL in body and REQUIRED not in body
