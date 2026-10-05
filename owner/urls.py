from django.urls import path

from . import views

app_name = "owner"

urlpatterns = [
    path("", views.dashboard_page, name="dashboard"),
    path("permintaan/baru/", views.request_new, name="request_new"),
    path("permintaan/<int:pk>/", views.request_detail, name="request_detail"),
    path("summary/", views.summary, name="summary"),
    path("summary/unduh/", views.summary_pdf, name="summary_pdf"),
    path("jadwal/", views.jadwal, name="jadwal"),
]
