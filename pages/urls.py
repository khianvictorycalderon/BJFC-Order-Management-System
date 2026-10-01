from django.urls import path
from . import views

urlpatterns = [
    path("", views.public_test, name="public_test"),
    path("private/", views.private_test, name="private_test")
]