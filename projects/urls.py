from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("baru/", views.project_new, name="new"),
    path("<int:pk>/", views.project_detail, name="detail"),
    path("<int:pk>/task/<int:task_pk>/", views.task_detail, name="task_detail"),
    # Aksi penerima Owner dari kartu "Tugas saya (project)" di dashboard Owner (hanya POST).
    path("tugas-saya/<int:pk>/selesai/", views.my_submit, name="my_submit"),
    path("tugas-saya/task/<int:pk>/balas/", views.my_comment, name="my_comment"),
    path("tugas-saya/<int:pk>/tolak/", views.my_decline, name="my_decline"),
]
