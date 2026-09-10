from django.contrib import admin

from .models import (
    CommissionTurnEvent,
    NurseEligibility,
    NurseRosterEntry,
    ProcedureAssignment,
    ProcedureCategory,
)

admin.site.register(
    [ProcedureCategory, NurseEligibility, NurseRosterEntry, ProcedureAssignment, CommissionTurnEvent]
)
