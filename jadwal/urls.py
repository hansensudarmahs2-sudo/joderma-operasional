from django.urls import path

from . import views

app_name = "jadwal"

urlpatterns = [
    path("", views.roster, name="roster"),
    path("tugas/", views.plan, name="plan"),
    path("tugas/<str:date>/", views.day, name="day"),
]
