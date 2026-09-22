import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole

pytestmark = pytest.mark.django_db


def test_sdm_can_assign_multiple_roles_in_active_clinic(client, admin_teknis, clinic):
    target = User.objects.create_user(username="rangkap", password="TestPassword123!")
    client.login(username=admin_teknis.username, password="TestPassword123!")
    response = client.post(
        reverse("accounts:user_detail", args=[target.pk]),
        {
            "username": target.username,
            "display_name": "Perawat Koordinator",
            "job_title": "Perawat",
            "phone": "",
            "is_active": "on",
            "roles": [Role.STAF, Role.PERAWAT, Role.SUPERVISOR],
            "capabilities": [],
        },
    )
    assert response.status_code == 302
    assert set(target.user_roles.values_list("role", flat=True)) == {Role.STAF, Role.PERAWAT, Role.SUPERVISOR}


def test_sdm_edit_does_not_remove_roles_in_other_clinic(client, admin_teknis, clinic, clinic_b):
    target = User.objects.create_user(username="lintas_cabang", password="TestPassword123!")
    UserRole.objects.create(user=target, clinic=clinic_b, role=Role.APOTEKER)
    client.login(username=admin_teknis.username, password="TestPassword123!")
    response = client.post(
        reverse("accounts:user_detail", args=[target.pk]),
        {
            "username": target.username,
            "display_name": "Apoteker",
            "job_title": "Apoteker",
            "phone": "",
            "is_active": "on",
            "roles": [Role.STAF, Role.APOTEKER],
            "capabilities": [],
        },
    )
    assert response.status_code == 302
    assert UserRole.objects.filter(user=target, clinic=clinic_b, role=Role.APOTEKER).exists()


def test_sdm_can_toggle_user_active_without_deleting_roles(client, admin_teknis, clinic):
    target = User.objects.create_user(username="nonaktifkan", password="TestPassword123!")
    UserRole.objects.create(user=target, clinic=clinic, role=Role.PERAWAT)
    client.login(username=admin_teknis.username, password="TestPassword123!")

    response = client.post(reverse("accounts:user_toggle_active", args=[target.pk]))
    target.refresh_from_db()
    assert response.status_code == 302
    assert target.is_active is False
    assert target.deactivated_at is not None
    assert UserRole.objects.filter(user=target, clinic=clinic, role=Role.PERAWAT).exists()

    client.post(reverse("accounts:user_toggle_active", args=[target.pk]))
    target.refresh_from_db()
    assert target.is_active is True
    assert target.deactivated_at is None
