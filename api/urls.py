from django.urls import path
from . import views

urlpatterns = [
    path("", views.test_api_response, name="test_api_response")
]