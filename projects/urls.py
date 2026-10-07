from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("baru/", views.project_new, name="new"),
    path("<int:pk>/", views.project_detail, name="detail"),
    path("<int:pk>/task/<int:task_pk>/", views.task_detail, name="task_detail"),
]
