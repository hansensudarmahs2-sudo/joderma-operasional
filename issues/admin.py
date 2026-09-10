from django.contrib import admin

from .models import Asset, Issue, IssueAssignment, IssueUpdate


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("number", "issue_type", "title", "severity", "status")
    list_filter = ("issue_type", "status", "severity")
    search_fields = ("number", "title")


admin.site.register([Asset, IssueAssignment, IssueUpdate])
