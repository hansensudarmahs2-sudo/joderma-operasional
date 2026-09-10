"""Autentikasi, throttling login, dan admin pengguna (PRD 13.2, 15.1)."""
from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.middleware import client_ip
from audit.models import AuditAction
from audit.services import log_event
from core.permissions import can_manage_users, require
from core.services import active_clinic
from django.conf import settings

from .forms import ChangePasswordForm, LoginForm, UserForm
from .models import LoginAttempt, User, UserCapability, UserRole


def _is_locked_out(username: str) -> bool:
    window = timezone.now() - timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
    failures = LoginAttempt.objects.filter(
        username=username, successful=False, attempted_at__gte=window
    ).count()
    return failures >= settings.LOGIN_MAX_ATTEMPTS


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"].strip()
        password = form.cleaned_data["password"]
        ip = client_ip(request)

        if _is_locked_out(username):
            messages.error(
                request,
                "Terlalu banyak percobaan gagal. Coba lagi beberapa menit lagi atau hubungi admin.",
            )
            log_event(
                action=AuditAction.LOGIN_FAILED,
                entity_type="user",
                entity_id=username,
                entity_label=username,
                reason="Lockout aktif",
            )
            return render(request, "accounts/login.html", {"form": form})

        user = authenticate(request, username=username, password=password)
        LoginAttempt.objects.create(username=username, ip_address=ip, successful=bool(user))

        if user is None:
            # Pesan gagal generik (PRD 13.2)
            messages.error(request, "Nama pengguna atau kata sandi salah.")
            log_event(
                action=AuditAction.LOGIN_FAILED,
                entity_type="user",
                entity_id=username,
                entity_label=username,
            )
        else:
            login(request, user)
            log_event(
                action=AuditAction.LOGIN_SUCCESS,
                entity_type="user",
                entity_id=user.pk,
                entity_label=str(user),
                actor=user,
            )
            if user.must_change_password:
                messages.info(request, "Silakan ganti kata sandi Anda.")
                return redirect("accounts:change_password")
            return redirect(request.GET.get("next") or "core:dashboard")

    return render(request, "accounts/login.html", {"form": form})


@require_POST
@login_required
def logout_view(request):
    log_event(
        action=AuditAction.LOGOUT,
        entity_type="user",
        entity_id=request.user.pk,
        entity_label=str(request.user),
        actor=request.user,
    )
    logout(request)
    messages.success(request, "Anda telah keluar.")
    return redirect("accounts:login")


@login_required
def change_password(request):
    form = ChangePasswordForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["new_password"])
        request.user.must_change_password = False
        request.user.save()
        update_session_auth_hash(request, request.user)
        log_event(
            action=AuditAction.PASSWORD_CHANGED,
            entity_type="user",
            entity_id=request.user.pk,
            entity_label=str(request.user),
            actor=request.user,
        )
        messages.success(request, "Kata sandi berhasil diubah.")
        return redirect("core:dashboard")
    return render(request, "accounts/change_password.html", {"form": form})


@login_required
@require(can_manage_users)
def user_list(request):
    users = User.objects.prefetch_related("user_roles", "extra_capabilities").order_by("username")
    return render(request, "accounts/user_list.html", {"users": users})


@login_required
@require(can_manage_users)
def user_create(request):
    form = UserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.set_password(form.cleaned_data["password"])
        user.must_change_password = True
        user.save()
        _sync_roles(user, form, request)
        messages.success(request, f"Pengguna {user} dibuat.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "creating": True})


@login_required
@require(can_manage_users)
def user_detail(request, pk: int):
    user = get_object_or_404(User, pk=pk)
    initial = {
        "roles": list(user.user_roles.values_list("role", flat=True)),
        "capabilities": list(user.extra_capabilities.values_list("capability", flat=True)),
    }
    form = UserForm(request.POST or None, instance=user, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if form.cleaned_data.get("password"):
            obj.set_password(form.cleaned_data["password"])
            obj.must_change_password = True
        if not obj.is_active and user.deactivated_at is None:
            obj.deactivated_at = timezone.now()
        obj.save()
        _sync_roles(obj, form, request)
        messages.success(request, "Pengguna diperbarui.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "target": user})


def _sync_roles(user: User, form: UserForm, request) -> None:
    clinic = active_clinic()
    wanted_roles = set(form.cleaned_data.get("roles") or [])
    current_roles = set(user.user_roles.values_list("role", flat=True))
    for role in wanted_roles - current_roles:
        UserRole.objects.create(user=user, clinic=clinic, role=role, granted_by=request.user)
    UserRole.objects.filter(user=user, role__in=current_roles - wanted_roles).delete()

    wanted_caps = set(form.cleaned_data.get("capabilities") or [])
    current_caps = set(user.extra_capabilities.values_list("capability", flat=True))
    for cap in wanted_caps - current_caps:
        UserCapability.objects.create(user=user, capability=cap, granted_by=request.user)
    UserCapability.objects.filter(user=user, capability__in=current_caps - wanted_caps).delete()

    log_event(
        action=AuditAction.PERMISSION_CHANGED,
        entity_type="user",
        entity_id=user.pk,
        entity_label=str(user),
        actor=request.user,
        before={"roles": sorted(current_roles), "capabilities": sorted(current_caps)},
        after={"roles": sorted(wanted_roles), "capabilities": sorted(wanted_caps)},
    )
