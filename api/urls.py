from django.urls import path, re_path

from . import views

urlpatterns = [
    path("", views.test_api_response, name="test_api_response"),
    re_path(r"^login/?$", views.login_api, name="login_api"),
    re_path(r"^register/?$", views.register, name="register"),
    re_path(r"^admin/orders/?$", views.admin_orders, name="admin_orders"),
    re_path(r"^admin/orders/info/?$", views.orders_info, name="admin_orders_info"),
    re_path(r"^admin/orders/(?P<pk>\d+)/?$", views.admin_order_status, name="admin_order_status"),
    re_path(
        r"^admin/orders/(?P<pk>\d+)/status/?$",
        views.admin_order_status,
        name="admin_order_status_legacy",
    ),
    re_path(r"^admin/menu/items/?$", views.menu_items, name="admin_menu_items"),
    re_path(
        r"^admin/menu/items/(?P<pk>\d+)/?$",
        views.admin_menu_item,
        name="admin_menu_item",
    ),
    re_path(r"^admin/feedbacks/?$", views.admin_feedbacks, name="admin_feedbacks"),
    re_path(r"^admin/feedbacks/info/?$", views.feedbacks_info, name="admin_feedbacks_info"),
    re_path(
        r"^admin/contact/messages/?$",
        views.admin_contact_messages,
        name="admin_contact_messages",
    ),
    re_path(
        r"^admin/contact/messages/(?P<pk>\d+)/?$",
        views.admin_contact_message,
        name="admin_contact_message",
    ),
    re_path(r"^contact/messages/?$", views.contact_messages, name="contact_messages"),
    re_path(r"^customer/menu/items/?$", views.customer_menu_items, name="customer_menu_items"),
    re_path(r"^customer/orders/?$", views.customer_create_order, name="customer_create_order"),
    re_path(r"^customer/my-orders/?$", views.customer_orders, name="customer_orders"),
    re_path(
        r"^customer/(?P<user_id>\d+)/my-orders/?$",
        views.customer_update_order,
        name="customer_update_order",
    ),
    re_path(r"^customer/favorites/?$", views.customer_favorites, name="customer_favorites"),
    re_path(
        r"^customer/favorites/(?P<menu_item_id>\d+)/?$",
        views.customer_favorite,
        name="customer_favorite",
    ),
    re_path(
        r"^customer/(?P<user_id>\d+)/profile/?$",
        views.customer_profile,
        name="customer_profile_by_id",
    ),
    re_path(r"^customer/profile/?$", views.customer_profile, name="customer_profile"),
    re_path(
        r"^customer/(?P<user_id>\d+)/password/?$",
        views.customer_password,
        name="customer_password",
    ),
    re_path(r"^profile/?$", views.customer_profile, name="customer_profile_legacy"),
    re_path(r"^admin/profile/?$", views.admin_profile, name="admin_profile"),
    re_path(r"^admin/password/?$", views.admin_password, name="admin_password"),
    re_path(r"^admin/landing-page/?$", views.admin_landing_page, name="admin_landing_page"),
    re_path(r"^admin/menu-page/?$", views.menu_page, name="admin_menu_page"),
    re_path(r"^admin/about-page/?$", views.about_page, name="admin_about_page"),
    re_path(r"^admin/contact-page/?$", views.contact_page, name="admin_contact_page"),
    re_path(
        r"^admin/pages/(?P<slug>[\w-]+)/?$",
        views.page_content,
        name="page_content",
    ),
    re_path(r"^admin/store-information/?$", views.store_information, name="store_information"),
    re_path(r"^admin/users/?$", views.admin_users, name="admin_users"),
]
