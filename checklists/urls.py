from django.urls import path

from . import views

app_name = "checklists"

urlpatterns = [
    path("", views.opening_index, name="index"),
    path("area/<int:run_id>/", views.run_detail, name="run"),
    path("respons/<int:pk>/simpan/", views.save_response, name="save_response"),
    path("respons/<int:pk>/kerusakan/", views.make_damage, name="make_damage"),
    path("respons/<int:pk>/tindak-lanjut/", views.make_action_item, name="make_action"),
    path("review/", views.review, name="review"),
    path("review/<int:run_id>/", views.review_action, name="review_action"),
    path("template/", views.template_list, name="templates"),
]
