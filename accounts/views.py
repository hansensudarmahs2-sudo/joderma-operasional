"""Autentikasi, throttling login, dan admin pengguna (PRD 13.2, 15.1)."""
from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audit.middleware import client_ip
from audit.models import AuditAction
from audit.services import log_event
from core.permissions import can_manage_users, require
from core.services import active_clinic
from django.conf import settings

from .forms import ChangePasswordForm, LoginForm, UserForm
from .models import LoginAttempt, Role, User, UserCapability, UserRole


def _is_locked_out(username: str) -> bool:
    window = timezone.now() - timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
    failures = LoginAttempt.objects.filter(
        username=username, successful=False, attempted_at__gte=window
    ).count()
    return failures >= settings.LOGIN_MAX_ATTEMPTS


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

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
            from core.services import active_clinic
            from jejak.models import Event
            from jejak.services import stamp

            stamp(request, Event.LOGIN, clinic=active_clinic(user), user=user)
            if user.must_change_password:
                messages.info(request, "Silakan ganti kata sandi Anda.")
                return redirect("accounts:change_password")
            nxt = request.GET.get("next", "")
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                                       require_https=request.is_secure()):
                return redirect(nxt)
            return redirect("home")

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
        return redirect("home")
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


def _assert_no_admin_lockout(target: User, *, new_roles: set, new_active: bool, actor: User):
    """Cegah klinik terkunci tanpa admin (PRD 18: penonaktifan tidak menghapus riwayat).

    Dua pengaman:
    1. Admin tidak boleh menonaktifkan akunnya sendiri — bila salah klik, tidak ada
       yang dapat memulihkan selain akses shell ke server.
    2. Admin aktif terakhir tidak boleh dicabut perannya atau dinonaktifkan.
    """
    from django.core.exceptions import ValidationError

    losing_admin = Role.ADMIN not in new_roles
    being_deactivated = not new_active

    if target.pk == actor.pk and being_deactivated:
        raise ValidationError(
            "Anda tidak dapat menonaktifkan akun Anda sendiri. "
            "Minta admin lain melakukannya agar klinik tidak kehilangan akses pengelolaan."
        )

    if not (losing_admin or being_deactivated):
        return

    remaining = (
        User.objects.filter(is_active=True, user_roles__role=Role.ADMIN)
        .exclude(pk=target.pk)
        .distinct()
        .count()
    )
    superusers = User.objects.filter(is_active=True, is_superuser=True).exclude(pk=target.pk).count()

    if remaining == 0 and superusers == 0:
        raise ValidationError(
            "Tindakan ini akan menyisakan klinik tanpa admin aktif. "
            "Tetapkan admin pengganti terlebih dahulu."
        )


@login_required
@require(can_manage_users)
def user_detail(request, pk: int):
    clinic = active_clinic(request.user)
    user = get_object_or_404(User, pk=pk)
    initial = {
        "roles": list(user.user_roles.filter(clinic=clinic).values_list("role", flat=True)),
        "capabilities": list(user.extra_capabilities.values_list("capability", flat=True)),
    }
    form = UserForm(request.POST or None, instance=user, initial=initial)
    if request.method == "POST" and form.is_valid():
        from django.core.exceptions import ValidationError

        try:
            _assert_no_admin_lockout(
                user,
                new_roles=set(form.cleaned_data.get("roles") or []),
                new_active=bool(form.cleaned_data.get("is_active")),
                actor=request.user,
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return render(request, "accounts/user_form.html", {"form": form, "target": user})

        obj = form.save(commit=False)
        if form.cleaned_data.get("password"):
            obj.set_password(form.cleaned_data["password"])
            obj.must_change_password = True
        if obj.is_active:
            obj.deactivated_at = None
        elif user.deactivated_at is None:
            obj.deactivated_at = timezone.now()
        obj.save()
        _sync_roles(obj, form, request)
        messages.success(request, "Pengguna diperbarui.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "target": user})


@login_required
@require(can_manage_users)
@require_POST
def user_toggle_active(request, pk: int):
    """Aktif/nonaktifkan akun tanpa menghapus riwayat atau role."""
    from django.core.exceptions import ValidationError

    user = get_object_or_404(User, pk=pk)
    new_active = not user.is_active
    roles = set(user.user_roles.filter(clinic=active_clinic(request.user)).values_list("role", flat=True))
    try:
        _assert_no_admin_lockout(
            user,
            new_roles=roles,
            new_active=new_active,
            actor=request.user,
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("accounts:user_list")

    user.is_active = new_active
    user.deactivated_at = None if new_active else timezone.now()
    user.save(update_fields=["is_active", "deactivated_at"])
    log_event(
        action=AuditAction.PERMISSION_CHANGED,
        entity_type="user",
        entity_id=user.pk,
        entity_label=str(user),
        actor=request.user,
        before={"is_active": not new_active},
        after={"is_active": new_active},
    )
    messages.success(request, f"Pengguna {user.username} {'diaktifkan' if new_active else 'dinonaktifkan'}.")
    return redirect("accounts:user_list")


def _sync_roles(user: User, form: UserForm, request) -> None:
    clinic = active_clinic(request.user)
    wanted_roles = set(form.cleaned_data.get("roles") or [])
    current_roles = set(user.user_roles.filter(clinic=clinic).values_list("role", flat=True))
    for role in wanted_roles - current_roles:
        UserRole.objects.create(user=user, clinic=clinic, role=role, granted_by=request.user)
    UserRole.objects.filter(user=user, clinic=clinic, role__in=current_roles - wanted_roles).delete()

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


def can_reset_roles(user) -> bool:
    """Reset peran ke default: Admin, superuser bootstrap, atau Direktur Operasional."""
    from core.permissions import is_admin, is_aom, is_bootstrap_superuser

    return is_admin(user) or is_bootstrap_superuser(user) or is_aom(user)


@login_required
@require(can_reset_roles)
def role_reset(request):
    """Pratinjau lalu terapkan peran standar (docs/KEBUTUHAN_REDEFINISI_PERAN.md)."""
    from django.core.exceptions import ValidationError

    from .peran_standar import DEFAULT_PASSWORD, apply_plan, build_plan, describe

    try:
        plans, clinics = build_plan()
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("accounts:user_list" if can_manage_users(request.user) else "home")
    if request.method == "POST":
        if request.POST.get("konfirmasi") != "1":
            messages.error(request, "Centang konfirmasi sebelum menerapkan.")
            return redirect("accounts:role_reset")
        n = apply_plan(plans, actor=request.user)
        messages.success(request, f"Peran dikembalikan ke default: {n} akun berubah.")
        return redirect("accounts:role_reset")
    rows = [{"plan": p, "lines": describe(p)} for p in plans]
    return render(
        request,
        "accounts/role_reset.html",
        {
            "rows": rows,
            "changed": [r for r in rows if r["lines"]],
            "clinics": clinics,
            "default_password": DEFAULT_PASSWORD,
        },
    )


@login_required
@require_POST
def switch_clinic(request):
    """Pengalih cabang di kanan atas: berlaku untuk hari ini, hanya cabang yang dapat diakses."""
    from core.models import local_today
    from core.permissions import user_clinic_queryset
    from core.services import CLINIC_SESSION_KEY

    clinic = user_clinic_queryset(request.user).filter(pk=request.POST.get("cabang") or 0).first()
    if clinic is None:
        messages.error(request, "Cabang tidak tersedia untuk akun Anda.")
    else:
        request.session[CLINIC_SESSION_KEY] = {"id": clinic.pk, "date": local_today().isoformat()}
        messages.success(request, f"Bekerja di {clinic.name} untuk hari ini.")
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return redirect(nxt)
    return redirect("home")
