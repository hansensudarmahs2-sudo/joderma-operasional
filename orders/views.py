from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import require
from core.services import active_clinic

from .forms import OnlineOrderForm, OnlineOrderItemForm, OnlineOrderStatusForm
from .models import OnlineOrder, OnlineOrderStatus
from .services import add_order_item, can_manage_online_orders, can_process_online_orders, create_online_order, submit_order, update_order_status


@login_required
def index(request):
    clinic = active_clinic(request.user)
    if not (can_manage_online_orders(request.user) or can_process_online_orders(request.user)):
        raise PermissionDenied("Menu order online tidak tersedia untuk role ini.")
    orders = OnlineOrder.objects.filter(clinic=clinic).select_related("created_by", "handled_by")
    if not can_manage_online_orders(request.user):
        orders = orders.exclude(status=OnlineOrderStatus.DRAFT)
    return render(request, "orders/index.html", {"orders": orders, "can_create": can_manage_online_orders(request.user), "can_process": can_process_online_orders(request.user), "status_choices": OnlineOrderStatus.choices})


@login_required
@require(lambda user: can_manage_online_orders(user))
def create(request):
    if request.method == "POST":
        form = OnlineOrderForm(request.POST)
        if form.is_valid():
            order = create_online_order(clinic=active_clinic(request.user), user=request.user, **form.cleaned_data)
            messages.success(request, "Order produk online berhasil dibuat dan diteruskan ke farmasi.")
            return redirect("orders:draft", pk=order.pk)
    else:
        form = OnlineOrderForm()
    return render(request, "orders/form.html", {"form": form})


@login_required
def draft(request, pk):
    order = get_object_or_404(OnlineOrder, pk=pk, clinic=active_clinic(request.user), status=OnlineOrderStatus.DRAFT)
    if not can_manage_online_orders(request.user):
        raise PermissionDenied("Draft order hanya dapat dikelola koordinator online.")
    return render(request, "orders/draft.html", {"order": order, "form": OnlineOrderItemForm()})


@login_required
@require_POST
def add_item(request, pk):
    order = get_object_or_404(OnlineOrder, pk=pk, clinic=active_clinic(request.user), status=OnlineOrderStatus.DRAFT)
    form = OnlineOrderItemForm(request.POST)
    if form.is_valid():
        add_order_item(order, user=request.user, **form.cleaned_data)
    return redirect("orders:draft", pk=order.pk)


@login_required
@require_POST
def submit(request, pk):
    order = get_object_or_404(OnlineOrder, pk=pk, clinic=active_clinic(request.user), status=OnlineOrderStatus.DRAFT)
    submit_order(order, user=request.user)
    messages.success(request, f"Order {order.order_no} dikirim ke farmasi.")
    return redirect("orders:index")


@login_required
@require(lambda user: can_process_online_orders(user))
@require_POST
def update_status(request, pk):
    order = get_object_or_404(OnlineOrder, pk=pk, clinic=active_clinic(request.user))
    form = OnlineOrderStatusForm(request.POST, instance=order)
    if form.is_valid():
        update_order_status(order, user=request.user, status=form.cleaned_data["status"], note=form.cleaned_data["note"])
        messages.success(request, f"Status {order.order_no} diperbarui.")
    return redirect("orders:index")
