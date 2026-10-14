from django.urls import path
from . import views

urlpatterns = [
    path("", views.test_api_response, name="test_api_response"),
    path("register/", views.register_api, name="register_api"),
    path("login/", views.login_api, name="login_api"),
]