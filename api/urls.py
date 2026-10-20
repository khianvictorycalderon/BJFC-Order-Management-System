from django.urls import path
from . import views

urlpatterns = [
    path("", views.test_api_response, name="test_api_response"),
    path("login/", views.login_api, name="login api endpoint"),
    path("register/", views.register, name="register"),
    path(
        "admin/landing-page/",
        views.admin_landing_page,
        name="admin-landing-page",
    ),
]
