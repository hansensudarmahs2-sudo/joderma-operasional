from django.urls import path

from . import views

app_name = "stok"

urlpatterns = [
    path("", views.index, name="index"),
    path("unggah/", views.unggah, name="unggah"),
    path("parameter/", views.parameter, name="parameter"),
]
