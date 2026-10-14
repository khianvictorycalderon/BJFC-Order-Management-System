from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_api, name="login api endpoint")
]