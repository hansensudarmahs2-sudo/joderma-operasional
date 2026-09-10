from django.urls import path

from . import views

app_name = "breaks"

urlpatterns = [
    path("", views.list_view, name="list"),
    path("baru/", views.create, name="create"),
    path("<int:pk>/ubah/", views.update, name="update"),
    path("<int:pk>/batal/", views.cancel, name="cancel"),
]
