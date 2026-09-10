from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import LoginAttempt, User, UserCapability, UserRole


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "display_name", "job_title", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("JoDerma", {"fields": ("display_name", "job_title", "phone", "must_change_password")}),
    )


admin.site.register([UserRole, UserCapability, LoginAttempt])
