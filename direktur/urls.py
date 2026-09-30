from django.urls import path

from . import views

app_name = "direktur"

urlpatterns = [
    path("", views.team, name="team"),
    path("ringkasan/", views.overview, name="overview"),
    path("kanban/", views.kanban_page, name="kanban"),
    path("prioritas/", views.matrix_page, name="matrix"),
    path("jadwal/", views.gantt_page, name="gantt"),
    path("keputusan/", views.decisions, name="decisions"),
    path("keputusan/<int:pk>/", views.decision_detail, name="decision_detail"),
    path("checklist/", views.checklist, name="checklist"),
    path("checklist/<int:item_id>/catat/", views.record, name="record"),
    path("summary/kirim/", views.summary_send, name="summary_send"),
    path("temuan/<int:pk>/selesai/", views.finding_close, name="finding_close"),
    path("catatan/", views.notes, name="notes"),
    path("catatan/<int:pk>/arsip/", views.note_archive, name="note_archive"),
    path("catatan/<int:pk>/jadikan-task/", views.note_convert, name="note_convert"),
    path("task/baru/", views.task_new, name="task_new"),
]
