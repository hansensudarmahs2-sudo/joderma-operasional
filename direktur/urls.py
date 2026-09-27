from django.urls import path

from . import views

app_name = "direktur"

urlpatterns = [
    path("", views.team, name="team"),
    path("checklist/", views.checklist, name="checklist"),
    path("checklist/<int:item_id>/catat/", views.record, name="record"),
    path("temuan/<int:pk>/selesai/", views.finding_close, name="finding_close"),
    path("catatan/", views.notes, name="notes"),
    path("catatan/<int:pk>/arsip/", views.note_archive, name="note_archive"),
    path("catatan/<int:pk>/jadikan-task/", views.note_convert, name="note_convert"),
    path("task/baru/", views.task_new, name="task_new"),
]
