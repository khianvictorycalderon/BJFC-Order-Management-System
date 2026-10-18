from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("menu/", views.menu, name="menu"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("private/", views.private_test, name="private_test"),

    # Admin Pages
    path("admin-panel/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-panel/menu/", views.admin_menu, name="admin_menu"),
    path("admin-panel/orders/", views.admin_orders, name="admin_orders"),
    path("admin-panel/feedback/", views.admin_feedback, name="admin_feedback"),
    path("admin-panel/settings/", views.admin_settings, name="admin_settings"),
    path("admin-panel/account/", views.admin_account, name="admin_account"),
    path("login/", views.login_page, name="login"),
    path("signup/", views.signup_page, name="signup"),
]

