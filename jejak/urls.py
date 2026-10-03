from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("perangkat/", views.devices, name="devices"),
]
