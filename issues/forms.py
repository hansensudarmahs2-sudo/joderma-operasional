from __future__ import annotations

from django import forms

from core.models import Priority

from .models import Asset, Channel, DamageCategory, ImpactLevel, Issue, IssueType, ReporterSource


class IssueForm(forms.ModelForm):
    """Field berubah sesuai tipe catatan (PRD 13.2)."""

    class Meta:
        model = Issue
        fields = [
            "issue_type",
            "title",
            "description",
            "category",
            "severity",
            "is_restricted",
            "is_anonymous",
            "reporter_source",
            "reporter_contact",
            "channel",
            "occurred_at",
            "followup_preference",
            "benefit",
            "location",
            "asset",
            "impact",
        ]
        labels = {
            "issue_type": "Tipe catatan",
            "title": "Ringkasan",
            "description": "Uraian",
            "category": "Kategori",
            "severity": "Tingkat dampak/urgensi",
            "is_restricted": "Tandai terbatas",
            "is_anonymous": "Anonim terhadap staf biasa",
            "reporter_source": "Sumber pelapor",
            "reporter_contact": "Kontak pelapor (opsional)",
            "channel": "Kanal",
            "occurred_at": "Waktu kejadian",
            "followup_preference": "Preferensi tindak lanjut",
            "benefit": "Manfaat/dampak",
            "location": "Lokasi",
            "asset": "Aset/peralatan",
            "impact": "Dampak penggunaan",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "benefit": forms.Textarea(attrs={"rows": 3}),
            "occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    # Field yang hanya relevan untuk tipe tertentu (PRD 13.2: field berubah
    # sesuai tipe). Dipakai template untuk menyembunyikan yang tidak perlu.
    FIELDS_BY_TYPE = {
        IssueType.KOMPLAIN: [
            "reporter_source", "reporter_contact", "channel",
            "occurred_at", "followup_preference", "is_restricted",
        ],
        IssueType.MASUKAN: ["benefit", "is_anonymous"],
        IssueType.KERUSAKAN: ["location", "asset", "impact"],
    }
    COMMON_FIELDS = ["issue_type", "title", "description", "category", "severity"]

    def __init__(self, *args, clinic=None, initial_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        if clinic is not None:
            self.fields["asset"].queryset = Asset.objects.filter(clinic=clinic, active=True)
        self.fields["asset"].required = False
        for name in ("reporter_source", "channel", "impact", "category"):
            self.fields[name].required = False

        # Pilih tipe otomatis bila pengguna datang dari menu Komplain/Masukan/Kerusakan,
        # sehingga tidak perlu memilih ulang apa yang sudah jelas dari navigasi.
        if initial_type in dict(IssueType.choices) and not self.data:
            self.fields["issue_type"].initial = initial_type

        # Label tingkat menyesuaikan konteks agar tidak rancu
        self.fields["severity"].label = "Tingkat dampak"

    def type_field_map(self) -> dict[str, list[str]]:
        """Nama field HTML per tipe, untuk dipakai script progressive disclosure."""
        return {k: list(v) for k, v in self.FIELDS_BY_TYPE.items()}

    def clean(self):
        data = super().clean()
        issue_type = data.get("issue_type")
        if issue_type == IssueType.KOMPLAIN and not data.get("reporter_source"):
            self.add_error("reporter_source", "Sumber pelapor wajib diisi untuk komplain.")
        if issue_type == IssueType.KERUSAKAN:
            if not data.get("location") and not data.get("asset"):
                self.add_error("location", "Lokasi atau aset wajib diisi untuk laporan kerusakan.")
            if not data.get("impact"):
                self.add_error("impact", "Dampak penggunaan wajib dipilih untuk kerusakan.")
        return data


class AttachmentForm(forms.Form):
    file = forms.FileField(label="Berkas (JPG, PNG, PDF, maks 5 MB)")
