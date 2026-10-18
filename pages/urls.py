from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("menu/", views.menu, name="menu"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("private/", views.private_test, name="private_test"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard),
    path("my-orders", views.my_orders, name="my_orders"),
    path("my-orders/", views.my_orders),
    path("account", views.customer_account, name="customer_account"),
    path("account/", views.customer_account),

    # Admin Pages
    path("admin-panel/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-panel/menu/", views.admin_menu, name="admin_menu"),
    path("admin-panel/orders/", views.admin_orders, name="admin_orders"),
    path("admin-panel/feedback/", views.admin_feedback, name="admin_feedback"),
    path("admin-panel/settings/", RedirectView.as_view(pattern_name="admin_settings_home"), name="admin_settings"),
    path("admin-panel/settings/home/", views.admin_settings_home, name="admin_settings_home"),
    path("admin-panel/settings/about/", views.admin_settings_about, name="admin_settings_about"),
    path("admin-panel/settings/menu/", views.admin_settings_menu, name="admin_settings_menu"),
    path("admin-panel/settings/contact/", views.admin_settings_contact, name="admin_settings_contact"),
    path("admin-panel/account/", views.admin_account, name="admin_account"),
    path("admin-login/", views.admin_login_page, name="admin_login"),
    path("login/", views.login_page, name="login"),
    path("signup/", views.signup_page, name="signup"),
]
