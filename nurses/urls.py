from django.urls import path

from . import views

app_name = "nurses"

urlpatterns = [
    path("", views.board, name="board"),
    path("tally/", views.create_tally, name="tally_create"),
    path("roster/", views.roster_form, name="roster"),
    path("tindakan/", views.assign, name="assign"),
    path("tindakan/<int:pk>/mulai/", views.start, name="start"),
    path("tindakan/<int:pk>/selesai/", views.complete, name="complete"),
    path("tindakan/<int:pk>/batal/", views.cancel, name="cancel"),
    path("roster/<int:pk>/skip/", views.skip, name="skip"),
    path("roster/<int:pk>/ketersediaan/", views.availability, name="availability"),
    path("ledger/", views.ledger, name="ledger"),
    path("roster/<int:pk>/serahkan/", views.hand_over_view, name="hand_over"),
    path("roster/<int:pk>/geser/", views.move_view, name="move"),
    path("roster/sinkron/", views.sync_view, name="sync"),
]
