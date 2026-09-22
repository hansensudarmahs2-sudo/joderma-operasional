from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.index, name="index"),
    path("baru/", views.create, name="create"),
    path("draft/<int:pk>/", views.draft, name="draft"),
    path("draft/<int:pk>/tambah/", views.add_item, name="add_item"),
    path("draft/<int:pk>/kirim/", views.submit, name="submit"),
    path("<int:pk>/status/", views.update_status, name="update_status"),
]
