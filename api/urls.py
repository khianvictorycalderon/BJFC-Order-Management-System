from django.urls import path
from . import views

urlpatterns = [
    path(
        "register/",
        views.register,
        name="register",
    ),

    path(
        "admin/orders/",
        views.admin_orders,
        name="admin_orders",
    ),

    path(
        "admin/orders/<int:pk>/status/",
        views.admin_order_status,
        name="admin_order_status",
    ),

    path(
        "admin/password/",
        views.admin_password,
        name="admin_password",
    ),

    path(
        "admin/pages/<slug:slug>/",
        views.page_content,
        name="page_content",
    ),
    path(
        "admin/store-information/",
        views.store_information,
        name="store-information",
    ),
    path(
        "profile/",
        views.customer_profile,
        name="customer_profile",
    ),
    path("login/", 
        views.login_api,
        name="login api endpoint"
    ),

]