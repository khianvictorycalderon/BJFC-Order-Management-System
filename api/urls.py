from django.urls import path, re_path
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
        name="store_information",
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
    path("", views.test_api_response, name="test_api_response"),
    path("login/", views.login_api, name="login api endpoint"),
    path("register/", views.register, name="register"),
    re_path(r"^contact/messages/?$", views.contact_messages, name="contact_messages"),
    re_path(r"^admin/menu/items/?$", views.menu_items, name="admin_menu_items"),
    re_path(r"^admin/orders/info/?$", views.orders_info, name="admin_orders_info"),
    re_path(r"^admin/feedbacks/info/?$", views.feedbacks_info, name="admin_feedbacks_info")
]
    path(
        "admin/landing-page/",
        views.admin_landing_page,
        name="admin-landing-page",
    ),
    path("admin/users/", views.admin_users, name="admin-users"),
]
