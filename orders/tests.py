import pytest
from django.urls import reverse

from accounts.models import Role, User, UserRole
from .models import OnlineOrder, OnlineOrderStatus
from .services import normalize_rm_number

pytestmark = pytest.mark.django_db


def _user(clinic, username, role):
    user = User.objects.create_user(username=username, password="TestPassword123!")
    UserRole.objects.create(user=user, clinic=clinic, role=role)
    return user


def test_online_can_create_order_for_pharmacy(client, clinic):
    online = _user(clinic, "online_order", Role.ONLINE)
    assert client.login(username=online.username, password="TestPassword123!")
    response = client.post(
        reverse("orders:create"),
        {"customer_name": "Pelanggan Dummy", "customer_contact": "0812", "rm_number": "c7548", "customer_address": "Alamat dummy", "product_name": "Sunscreen", "quantity": 2, "note": "Kirim sore"},
    )
    assert response.status_code == 302
    order = OnlineOrder.objects.get()
    assert order.created_by == online
    assert order.status == OnlineOrderStatus.DRAFT
    assert order.rm_number == "JC-7548"
    assert order.customer_address == "Alamat dummy"
    client.post(reverse("orders:add_item", args=[order.pk]), {"product_name": "Vitamin", "quantity": 1})
    order.refresh_from_db()
    assert order.items.count() == 2
    client.post(reverse("orders:submit", args=[order.pk]))
    order.refresh_from_db()
    assert order.status == OnlineOrderStatus.BARU


def test_pharmacist_can_process_order_but_online_cannot_change_status(client, clinic):
    online = _user(clinic, "online_order2", Role.ONLINE)
    pharmacist = _user(clinic, "apoteker_order", Role.APOTEKER)
    client.login(username=online.username, password="TestPassword123!")
    client.post(reverse("orders:create"), {"customer_name": "P", "customer_contact": "08", "rm_number": "7548", "customer_address": "Alamat", "product_name": "Produk", "quantity": 1})
    order = OnlineOrder.objects.get()
    response = client.post(reverse("orders:update_status", args=[order.pk]), {"status": OnlineOrderStatus.SIAP, "note": "Siap"})
    assert response.status_code == 403
    client.login(username=pharmacist.username, password="TestPassword123!")
    response = client.post(reverse("orders:update_status", args=[order.pk]), {"status": OnlineOrderStatus.SIAP, "note": "Siap"})
    assert response.status_code == 302
    order.refresh_from_db()
    assert order.status == OnlineOrderStatus.SIAP
    assert order.handled_by == pharmacist


def test_rm_prefix_fallback_and_explicit_prefix(clinic):
    clinic.code = "citraland"
    assert normalize_rm_number(clinic, "7548") == "JC-7548"
    assert normalize_rm_number(clinic, "JJ-12") == "JJ-12"
    clinic.code = "cabang-baru"
    assert normalize_rm_number(clinic, "7548") == "J_-7548"
    assert normalize_rm_number(clinic, "c4567J_-") == "JC-4567"


def test_new_order_form_does_not_prefill_rm_placeholder(client, clinic):
    online = _user(clinic, "online_blank_rm", Role.ONLINE)
    client.login(username=online.username, password="TestPassword123!")
    response = client.get(reverse("orders:create"))
    assert response.status_code == 200
    assert 'value="J_-"' not in response.content.decode()


def test_order_form_has_product_search_and_dropdown(client, clinic):
    online = _user(clinic, "online_product_search", Role.ONLINE)
    client.login(username=online.username, password="TestPassword123!")
    response = client.get(reverse("orders:create"))
    body = response.content.decode()
    assert 'id="id_product_search"' in body
    assert 'id="id_product"' in body
