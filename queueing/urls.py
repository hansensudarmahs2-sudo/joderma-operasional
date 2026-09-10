from django.urls import path

from . import views

app_name = "queueing"

urlpatterns = [
    path("", views.board, name="board"),
    path("layar/", views.public_board, name="public_board"),
    path("baru/", views.create, name="create"),
    path("<int:pk>/status/", views.set_status, name="set_status"),
    path("<int:pk>/pembayaran/", views.set_payment, name="set_payment"),
    path("<int:pk>/urutan/", views.move, name="move"),
    path("<int:pk>/prioritas/", views.priority, name="priority"),
    path("<int:pk>/", views.detail, name="detail"),
]
