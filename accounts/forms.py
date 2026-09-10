from __future__ import annotations

from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import Capability, Role, User


class LoginForm(forms.Form):
    username = forms.CharField(label="Nama pengguna", max_length=150)
    password = forms.CharField(label="Kata sandi", widget=forms.PasswordInput)


class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(label="Kata sandi saat ini", widget=forms.PasswordInput)
    new_password = forms.CharField(label="Kata sandi baru", widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="Ulangi kata sandi baru", widget=forms.PasswordInput)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        value = self.cleaned_data["current_password"]
        if not self.user.check_password(value):
            raise forms.ValidationError("Kata sandi saat ini tidak cocok.")
        return value

    def clean(self):
        data = super().clean()
        new = data.get("new_password")
        confirm = data.get("confirm_password")
        if new and confirm and new != confirm:
            self.add_error("confirm_password", "Konfirmasi kata sandi tidak sama.")
        if new:
            validate_password(new, self.user)
        return data


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label="Kata sandi awal",
        widget=forms.PasswordInput,
        required=False,
        help_text="Minimal 12 karakter. Kosongkan bila tidak ingin mengubah.",
    )
    roles = forms.MultipleChoiceField(
        label="Peran", choices=Role.choices, widget=forms.CheckboxSelectMultiple, required=True
    )
    capabilities = forms.MultipleChoiceField(
        label="Kapabilitas tambahan",
        choices=Capability.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Hak bisnis sensitif harus diberikan eksplisit.",
    )

    class Meta:
        model = User
        fields = ["username", "display_name", "job_title", "phone", "is_active"]
        labels = {"username": "Nama pengguna", "is_active": "Aktif"}

    def clean_password(self):
        value = self.cleaned_data.get("password")
        if value:
            validate_password(value)
        return value

    def clean(self):
        data = super().clean()
        if not self.instance.pk and not data.get("password"):
            self.add_error("password", "Kata sandi awal wajib diisi untuk pengguna baru.")
        return data
