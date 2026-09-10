from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.index, name="index"),
    path("ekspor/<str:dataset>/", views.export_csv, name="export"),
]
