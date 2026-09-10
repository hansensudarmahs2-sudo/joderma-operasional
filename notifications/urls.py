from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.list_view, name="list"),
    path("baca/", views.mark_all, name="mark_all"),
    path("<int:pk>/buka/", views.open_one, name="open"),
]
