from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import FoodItem, LandingPage, PageInfo, StoreInformation


customer_required = user_passes_test(
    lambda user: not user.is_staff,
    login_url="admin_dashboard",
    redirect_field_name=None,
)


def _authenticated_destination(req):
    return redirect("admin_dashboard" if req.user.is_staff else "dashboard")


def _page_content(slug, title, description):
    page = PageInfo.objects.filter(slug=slug).first()
    return {
        "title": page.title if page else title,
        "description": page.description if page else description,
    }


def _store_context():
    store = StoreInformation.objects.order_by("pk").first()
    return {
        "store": {
            "name": store.storename,
            "phone": store.contact,
            "address": store.address,
            "email": store.email,
        }
        if store
        else {},
    }


def home(req):
    landing = LandingPage.objects.order_by("pk").first()
    title = landing.main_heading if landing else "Fresh, crispy chicken for every craving"
    description = (
        landing.subheading_description
        if landing
        else "Enjoy delicious fried chicken, made fresh and served with a smile."
    )
    context = {
        "hero": {
            "title": title,
            "lines": [description],
            "cta_label": (landing.button_text if landing else "") or "Order Now",
            "cta_url": (landing.button_link if landing else "") or "/menu/",
            "image_url": (landing.hero_image if landing else "") or "/static/images/hero-art.jpg",
        },
        **_store_context(),
    }
    return render(req, "public/home.html", context)

@login_required(login_url="login")
@customer_required
def private_test(req):
    return render(req, "private/test.html")


# Menu page
def menu(req):
    meals = []
    fallback_images = [
        "/static/images/menu/chicken1.png",
        "/static/images/menu/chicken2.png",
        "/static/images/menu/chicken3.png",
        "/static/images/menu/chicken4.png",
    ]
    items = (
        FoodItem.objects.filter(available=True)
        .order_by("name", "pk")
    )
    for index, item in enumerate(items):
        try:
            image_url = item.image.url if item.image else fallback_images[index % len(fallback_images)]
        except ValueError:
            image_url = fallback_images[index % len(fallback_images)]
        entry = {
            "id": item.pk,
            "name": item.name,
            "price": item.price,
            "description": item.description,
            "image_url": image_url,
        }
        meals.append(entry)

    context = {
        "meals": meals,
        "menu_page": _page_content(
            "menu",
            "SIGNATURE FRIED CHICKEN",
            "Golden, crunchy, and juicy chicken with our signature crispy coating.",
        ),
        **_store_context(),
    }

    return render(req, "public/menu.html", context)

def about(req):
    return render(req, "public/about.html", {
        "about_page": _page_content(
            "about",
            "About BJFC",
            "Learn more about BJFC and our food.",
        ),
        **_store_context(),
    })


def contact(req):
    return render(req, "public/contact.html", {
        "contact_page": _page_content(
            "contact",
            "Contact Us",
            "We'd love to hear from you! Whether you have a question, want to place a bulk order, or just want to say hello, our team is ready to help.",
        ),
        **_store_context(),
    })


@login_required(login_url="login")
@customer_required
def dashboard(req):
    today = timezone.localdate()
    start_date = today - timedelta(days=6)
    orders = req.user.orders.all()
    daily_counts = {
        row["day"]: row["count"]
        for row in orders.filter(created_at__date__range=(start_date, today))
        .values(day=TruncDate("created_at"))
        .annotate(count=Count("pk"))
    }
    chart = [
        {
            "date": (start_date + timedelta(days=offset)).isoformat(),
            "count": daily_counts.get(start_date + timedelta(days=offset), 0),
        }
        for offset in range(7)
    ]
    return render(
        req,
        "private/dashboard.html",
        {
            "active_orders": orders.filter(
                status__in=("PENDING", "CONFIRMED", "PREPARING", "OUT_FOR_DELIVERY")
            ).count(),
            "completed_orders": orders.filter(status="COMPLETED").count(),
            "weekly_orders": sum(row["count"] for row in chart),
            "order_chart": chart,
        },
    )


@login_required(login_url="login")
@customer_required
def my_orders(req):
    return render(req, "private/my_orders.html", {"order_items": []})


@login_required(login_url="login")
@customer_required
def customer_account(req):
    return render(req, "private/account.html")


@require_POST
def logout_view(req):
    logout(req)
    return redirect("home")


# Admin pages
@staff_member_required(login_url="admin_login")
def admin_dashboard(req):
    return render(req, "private/layout/admin/dashboard.html")

@staff_member_required(login_url="admin_login")
def admin_menu(req):
    return render(req, "private/layout/admin/menu.html")

@staff_member_required(login_url="admin_login")
def admin_orders(req):
    return render(req, "private/layout/admin/order.html")

@staff_member_required(login_url="admin_login")
def admin_feedback(req):
    return render(req, "private/layout/admin/feedback.html")


@staff_member_required(login_url="admin_login")
def admin_users(req):
    return render(req, "private/layout/admin/users.html")


@staff_member_required(login_url="admin_login")
def admin_settings_home(req):
    return render(req, "private/layout/admin/settings_home.html")


@staff_member_required(login_url="admin_login")
def admin_settings_about(req):
    return render(req, "private/layout/admin/settings_about.html")


@staff_member_required(login_url="admin_login")
def admin_settings_menu(req):
    return render(req, "private/layout/admin/settings_menu.html")


@staff_member_required(login_url="admin_login")
def admin_settings_contact(req):
    return render(req, "private/layout/admin/settings_contact.html")


@staff_member_required(login_url="admin_login")
def admin_account(req):
    return render(req, "private/layout/admin/account.html")
  
def login_page(req):
    if req.user.is_authenticated:
        return _authenticated_destination(req)
    next_url = req.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={req.get_host()}):
        next_url = ""
    return render(req, "public/login.html", {"next_url": next_url})


def signup_page(req):
    if req.user.is_authenticated:
        return _authenticated_destination(req)
    return render(req, "public/signup.html")


def admin_login_page(req):
    if req.user.is_authenticated:
        return _authenticated_destination(req)
    return render(req, "public/admin_login.html")
