from django.urls import path

from . import views

app_name = "cash"

urlpatterns = [
    path("", views.index, name="index"),
    path("sesi/<str:session_type>/", views.form, name="form"),
    path("sesi/<int:pk>/simpan/", views.save, name="save"),
    path("sesi/<int:pk>/ajukan/", views.submit, name="submit"),
    path("sesi/<int:pk>/review/", views.review, name="review"),
    path("sesi/<int:pk>/verifikasi/", views.verify_action, name="verify"),
    path("sesi/<int:pk>/koreksi/", views.correct, name="correct"),
]
