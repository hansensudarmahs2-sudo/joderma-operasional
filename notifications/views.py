from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification
from .services import mark_read


@login_required
def list_view(request):
    items = Notification.objects.filter(user=request.user)[:100]
    return render(request, "notifications/list.html", {"items": items})


@login_required
@require_POST
def mark_all(request):
    mark_read(request.user)
    return redirect("notifications:list")


@login_required
def open_one(request, pk: int):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    mark_read(request.user, notif.pk)
    return redirect(notif.url or "core:dashboard")
