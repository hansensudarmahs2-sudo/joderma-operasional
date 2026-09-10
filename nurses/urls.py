from django.urls import path

from . import views

app_name = "nurses"

urlpatterns = [
    path("", views.board, name="board"),
    path("roster/", views.roster_form, name="roster"),
    path("tindakan/", views.assign, name="assign"),
    path("tindakan/<int:pk>/mulai/", views.start, name="start"),
    path("tindakan/<int:pk>/selesai/", views.complete, name="complete"),
    path("tindakan/<int:pk>/batal/", views.cancel, name="cancel"),
    path("roster/<int:pk>/skip/", views.skip, name="skip"),
    path("roster/<int:pk>/ketersediaan/", views.availability, name="availability"),
    path("ledger/", views.ledger, name="ledger"),
]
