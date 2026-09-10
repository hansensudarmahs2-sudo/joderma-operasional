from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("ganti-password/", views.change_password, name="change_password"),
    path("pengguna/", views.user_list, name="user_list"),
    path("pengguna/baru/", views.user_create, name="user_create"),
    path("pengguna/<int:pk>/", views.user_detail, name="user_detail"),
]
