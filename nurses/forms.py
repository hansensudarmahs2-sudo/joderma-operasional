from django import forms

from .models import NurseActionTally


class NurseActionTallyForm(forms.ModelForm):
    class Meta:
        model = NurseActionTally
        fields = ("nurse", "rm_number", "patient_name", "action_name", "tally")
        labels = {"nurse": "Perawat", "rm_number": "Nomor RM", "patient_name": "Nama pasien", "action_name": "Tindakan", "tally": "Jumlah"}

    def __init__(self, *args, nurse_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if nurse_queryset is not None:
            self.fields["nurse"].queryset = nurse_queryset
