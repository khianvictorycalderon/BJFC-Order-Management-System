import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django import forms
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.db.models.functions import TruncDate
from django.http import FileResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods
from PIL import Image


from core.models import (
    ContactMessage,
    Favorite,
    FoodAddon,
    FoodCategory,
    FoodItem,
    LandingPage,
    Order,
    OrderAuditEvent,
    OrderItem,
    OrderAddressChange,
    OrderItemAddon,
    PageInfo,
    Rating,
    StoreInformation,
    User,
)
from .forms import PHONE_RE, ContactMessageForm, FoodItemForm, form_errors, parse_payload

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100

PENDING_STATUSES = (
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.PREPARING,
)

# Statuses an admin can set from the Orders page. (Cancelling is done by the customer.)
ADMIN_SETTABLE_STATUSES = (
    Order.Status.PENDING,
    Order.Status.OUT_FOR_DELIVERY,
    Order.Status.COMPLETED,
    Order.Status.INVALID,
)

PAGE_DEFAULTS = {
    "menu": {
        "title": "SIGNATURE FRIED CHICKEN",
        "description": "Golden, crunchy, and juicy chicken with our signature crispy coating.",
    },
    "about": {
        "title": "About BJFC",
        "description": "Learn more about BJFC and our food.",
    },
    "contact": {
        "title": "Contact Us",
        "description": "Get in touch with the BJFC team.",
    },
}

LANDING_FIELDS = (
    "main_heading",
    "subheading_description",
    "hero_image",
    "button_text",
    "button_link",
)
LANDING_DEFAULTS = {
    "main_heading": "Welcome to BJFC",
    "subheading_description": "Fresh, crispy favorites made for you.",
}

MENU_SORT_FIELDS = {
    "id": "id",
    "name": "name",
    "price": "price",
    "category": "category__name",
}


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #

def _json_body(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "Invalid JSON data."}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({"error": "Expected a JSON object."}, status=400)
    return data, None


def _admin_api(*methods):
    """Allow only the given HTTP methods and only authenticated staff users."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                response = JsonResponse({"error": "Method not allowed."}, status=405)
                response["Allow"] = ", ".join(methods)
                return response
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Authentication required."}, status=401)
            if not request.user.is_staff:
                return JsonResponse({"error": "Admin access required."}, status=403)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def _require_customer(request, user_id=None):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user_id is not None and request.user.pk != int(user_id):
        return JsonResponse({"error": "You can only access your own account."}, status=403)
    if request.user.is_staff:
        return JsonResponse({"error": "Customer access required."}, status=403)
    return None


def _pagination(request):
    error = JsonResponse(
        {"error": "'page' and 'size' must be positive integers."}, status=400
    )
    try:
        page = int(request.GET.get("page", "1"))
        size = int(request.GET.get("size", str(DEFAULT_PAGE_SIZE)))
    except (TypeError, ValueError):
        return None, error
    if page < 1 or size < 1:
        return None, error
    return (page, min(size, MAX_PAGE_SIZE)), None


def _item_sort(request):
    direction = request.GET.get("sort", "asc").lower()
    if direction not in ("asc", "desc"):
        return None, JsonResponse({"error": "'sort' must be 'asc' or 'desc'."}, status=400)
    return direction, None


def _list_params(request):
    """Validate ?page=&size=&sort= and return ((page, size, direction), error)."""
    pagination, error = _pagination(request)
    if error:
        return None, error
    direction, error = _item_sort(request)
    if error:
        return None, error
    page_number, size = pagination
    return (page_number, size, direction), None


def _ordering(direction, *fields):
    prefix = "-" if direction == "desc" else ""
    return [f"{prefix}{field}" for field in fields]


def _page_response(queryset, page_number, size, key, serializer):
    paginator = Paginator(queryset, size)
    try:
        page = paginator.page(page_number)
        objects = page.object_list
        has_next = page.has_next()
        has_previous = page.has_previous()
    except EmptyPage:
        objects = []
        has_next = False
        has_previous = paginator.num_pages > 0
    return {
        key: [serializer(obj) for obj in objects],
        "pagination": {
            "page": page_number,
            "size": size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": has_next,
            "has_previous": has_previous,
        },
    }


# --------------------------------------------------------------------------- #
# Serializers
# --------------------------------------------------------------------------- #

def _serialize_addon(addon):
    return {
        "id": addon.pk,
        "name": addon.name,
        "price": str(addon.price),
        "available": addon.available,
    }


def _serialize_food_item(item):
    try:
        image = item.image.url if item.image else None
    except ValueError:
        image = None
    return {
        "id": item.pk,
        "name": item.name,
        "description": item.description,
        "price": str(item.price),
        "available": item.available,
        "image": image,
        "category": (
            {"id": item.category_id, "name": item.category.name}
            if item.category_id
            else None
        ),
        "addons": [_serialize_addon(addon) for addon in item.addons.filter(available=True)],
    }


def _orders_with_relations(queryset=None):
    """Orders with everything `_serialize_order` needs, fetched up front."""
    if queryset is None:
        queryset = Order.objects.all()
    return queryset.select_related("customer").prefetch_related(
        "items__food_item",
        "items__selected_addons",
        Prefetch(
            "address_changes",
            queryset=OrderAddressChange.objects.select_related("changed_by"),
        ),
    )


def _serialize_order(order, include_history=False):
    customer_name = order.customer.get_full_name() or order.customer.username
    estimated = order.estimated_time.isoformat() if order.estimated_time else None
    return {
        "id": order.pk,
        "order_number": f"BJFC-{order.pk:06d}",
        "customer": {
            "id": order.customer_id,
            "name": customer_name,
            "username": order.customer.username,
            "email": order.customer.email,
            "phone": order.customer.phone_number,
        },
        "customer_name": customer_name,
        "status": order.status,
        "status_display": order.get_status_display(),
        "created_at": order.created_at.isoformat(),
        "estimated_time": estimated,
        "eta": estimated,
        "total_amount": str(order.total_amount),
        "order_type": order.order_type,
        "order_type_display": order.get_order_type_display(),
        "contact_phone": order.contact_phone,
        "address": order.delivery_address,
        "delivery_address": order.delivery_address,
        "is_paid": order.is_paid,
        "payment_status": "PAID" if order.is_paid else "UNPAID",
        "payment_display": "Paid" if order.is_paid else "Not yet paid",
        "payment_method": order.payment_method,
        "payment_method_display": order.get_payment_method_display(),
        "payment_review_status": order.payment_review_status,
        "payment_review_display": order.get_payment_review_status_display(),
        "gcash_receipt": (
            f"/api/orders/{order.pk}/gcash-receipt" if order.gcash_receipt else None
        ),
        "receipt_invalid_reason": order.receipt_invalid_reason,
        "invalid_reason": order.invalid_reason,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "can_cancel": order.can_customer_cancel,
        "can_edit_address": order.can_customer_edit_address,
        # Uses the prefetched data; do not add select_related/prefetch_related here.
        "items": [
            {
                "food_item_id": item.food_item_id,
                "food_item_name": item.food_item.name,
                "quantity": item.quantity,
                "price": str(item.price),
                "addons": [
                    {"name": addon.name, "price": str(addon.price)}
                    for addon in item.selected_addons.all()
                ],
            }
            for item in order.items.all()
        ],
        **(
            {"address_history": _serialize_address_history(order)}
            if include_history
            else {}
        ),
    }


def _record_order_event(order, event_type, details, actor):
    OrderAuditEvent.objects.create(
        order=order,
        event_type=event_type,
        details=details,
        actor=actor,
    )


def _serialize_audit_event(event):
    actor = event.actor
    return {
        "id": event.pk,
        "order_id": event.order_id,
        "order_number": f"BJFC-{event.order_id:06d}",
        "customer": event.order.customer.get_full_name() or event.order.customer.username,
        "event_type": event.event_type,
        "details": event.details,
        "actor": (actor.get_full_name() or actor.username) if actor else "System",
        "created_at": event.created_at.isoformat(),
    }


def _serialize_address_history(order):
    history = []
    for change in order.address_changes.all():  # prefetched, oldest first
        who = change.changed_by
        history.append(
            {
                "old_address": change.old_address,
                "new_address": change.new_address,
                "changed_by": (who.get_full_name() or who.username) if who else "Unknown",
                "changed_at": change.changed_at.isoformat(),
            }
        )
    return history


def _serialize_feedback(rating):
    customer_name = rating.customer.get_full_name() or rating.customer.username
    date = rating.date.isoformat()
    return {
        "id": rating.pk,
        "customer": {
            "id": rating.customer_id,
            "name": customer_name,
            "email": rating.customer.email,
            "phone": rating.customer.phone_number,
        },
        "customer_name": customer_name,
        "email": rating.customer.email,
        "phone": rating.customer.phone_number,
        "rating": rating.score,
        "score": rating.score,
        "review": rating.review,
        "message": rating.review,
        "date": date,
        "created_at": date,
    }


def _serialize_contact(message):
    return {
        "id": message.pk,
        "name": message.name,
        "sender_name": (
            (message.sender.get_full_name() or message.sender.username)
            if message.sender_id
            else "Guest"
        ),
        "email": message.email,
        "phone": message.phone,
        "message": message.message,
        "status": message.status,
        "created_at": message.created_at.isoformat(),
    }


def _serialize_user(user):
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "display_name": user.get_full_name() or user.username,
        "phone_number": user.phone_number,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
    }


def _serialize_landing_page(page):
    return {"id": page.pk, **{field: getattr(page, field) for field in LANDING_FIELDS}}



def _serialize_page(page):
    return {"title": page.title, "description": page.description}


def _serialize_store(store):
    return {
        "email": store.email,
        "contact": store.contact,
        "address": store.address,
    }


# --------------------------------------------------------------------------- #
# Health check, authentication
# --------------------------------------------------------------------------- #

@require_http_methods(["GET"])
def test_api_response(request):
    return JsonResponse({"message": "API is running."})


def _authenticate_by_username_or_email(request, identifier, password):
    """Log in with either a username or an email address.

    The text is tried as a username first, so usernames that happen to look like
    an email (e.g. the default admin account) keep working. If that fails and it
    contains "@", it is looked up as an email (case-insensitive). An email that
    is shared by more than one account is refused as ambiguous.
    """
    user = authenticate(request=request, username=identifier, password=password)
    if user is None and "@" in identifier:
        matches = list(User.objects.filter(email__iexact=identifier)[:2])
        if len(matches) == 1:
            user = authenticate(
                request=request, username=matches[0].get_username(), password=password
            )
    return user


@csrf_protect
@require_http_methods(["POST"])
def login_api(request):
    data, error = _json_body(request)
    if error:
        return error
    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return JsonResponse({"error": "Username or email and password are required."}, status=400)
    admin_only = data.get("admin_only", False)
    if not isinstance(admin_only, bool):
        return JsonResponse({"error": "'admin_only' must be a boolean."}, status=400)
    user = _authenticate_by_username_or_email(request, username.strip(), password)
    if user is None:
        return JsonResponse({"error": "Invalid username/email or password."}, status=401)
    if not user.is_active:
        return JsonResponse({"error": "Account is inactive."}, status=403)
    if admin_only and not user.is_staff:
        return JsonResponse({"error": "Admin access required."}, status=403)
    login(request, user)
    return JsonResponse({"message": "Login successful.", "user": _serialize_user(user)}, status=200)


@csrf_protect
@require_http_methods(["POST"])
def register(request):
    data, error = _json_body(request)
    if error:
        return error
    required = ("username", "last_name", "first_name", "email", "password", "confirm_password")
    if any(not isinstance(data.get(field), str) for field in required):
        return JsonResponse({"error": "All fields are required and must be strings."}, status=400)
    values = {
        field: data[field].strip()
        for field in required
        if field not in ("password", "confirm_password")
    }
    password = data["password"]
    confirm_password = data["confirm_password"]
    if not all(values.values()) or not password or not confirm_password:
        return JsonResponse({"error": "All fields are required."}, status=400)
    try:
        validate_email(values["email"])
    except ValidationError:
        return JsonResponse({"error": "Invalid email address."}, status=400)
    if password != confirm_password:
        return JsonResponse({"error": "Passwords do not match."}, status=400)
    candidate = User(
        username=values["username"],
        email=values["email"].lower(),
        first_name=values["first_name"],
        last_name=values["last_name"],
    )
    try:
        validate_password(password, user=candidate)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)
    if User.objects.filter(email__iexact=values["email"]).exists():
        return JsonResponse({"error": "Email already registered."}, status=409)
    try:
        user = User.objects.create_user(
            username=values["username"],
            email=values["email"].lower(),
            first_name=values["first_name"],
            last_name=values["last_name"],
            password=password,
        )
    except IntegrityError:
        return JsonResponse({"error": "Username or email already registered."}, status=409)
    return JsonResponse({"message": "Account created.", "user": _serialize_user(user)}, status=201)


# --------------------------------------------------------------------------- #
# Admin: orders
# --------------------------------------------------------------------------- #

@_admin_api("GET")
def admin_dashboard(request):
    today = timezone.localdate()
    period = request.GET.get("period", "week")
    selected_date = request.GET.get("date")
    if selected_date:
        selected_date = parse_date(selected_date)
        if selected_date is None:
            return JsonResponse({"error": "'date' must use YYYY-MM-DD format."}, status=400)
        start_date = end_date = selected_date
    elif period == "week":
        start_date, end_date = today - timedelta(days=6), today
    elif period == "month":
        start_date, end_date = today - timedelta(days=29), today
    elif period == "all":
        start_date = end_date = None
    else:
        return JsonResponse({"error": "'period' must be 'week', 'month' or 'all'."}, status=400)

    orders = Order.objects.all()
    if start_date is not None:
        orders = orders.filter(created_at__date__range=(start_date, end_date))
    completed_orders = orders.filter(status=Order.Status.COMPLETED)
    chart_start = start_date or (today - timedelta(days=6))
    chart_end = end_date or today
    daily_sales = {
        row["day"]: row["sales"] or Decimal("0.00")
        for row in completed_orders.filter(created_at__date__range=(chart_start, chart_end))
        .values(day=TruncDate("created_at"))
        .annotate(sales=Sum("total_amount"))
    }
    weekly_sales = [
        {
            "date": (chart_start + timedelta(days=offset)).isoformat(),
            "sales": str(daily_sales.get(chart_start + timedelta(days=offset), Decimal("0.00"))),
        }
        for offset in range((chart_end - chart_start).days + 1)
    ]
    top_items = list(
        OrderItem.objects.filter(order__in=completed_orders)
        .values("food_item__name")
        .annotate(quantity=Sum("quantity"))
        .order_by("-quantity", "food_item__name")[:4]
    )
    recent_orders = _orders_with_relations().filter(
        created_at__date__range=(today - timedelta(days=1), today)
    ).order_by("-created_at", "-pk")[:10]
    return JsonResponse(
        {
            "total_sales": str(completed_orders.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")),
            "total_orders": orders.count(),
            "total_customers": User.objects.filter(is_staff=False).count(),
            "completed_orders": completed_orders.count(),
            "weekly_sales": weekly_sales,
            "top_items": top_items,
            "recent_orders": [_serialize_order(order) for order in recent_orders],
            "period": period,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }
    )


def _filter_orders_by_status(queryset, raw_filter):
    status_filter = (raw_filter or "").lower()
    if not status_filter:
        return queryset, None
    if status_filter == "pending":
        return queryset.filter(status__in=PENDING_STATUSES), None
    if status_filter == "completed":
        return queryset.filter(status=Order.Status.COMPLETED), None
    if status_filter.upper() in Order.Status.values:
        return queryset.filter(status=status_filter.upper()), None
    return None, JsonResponse({"error": "Invalid status filter."}, status=400)


@_admin_api("GET")
def admin_orders(request):
    queryset, error = _filter_orders_by_status(
        _orders_with_relations(), request.GET.get("filter")
    )
    if error:
        return error
    params, error = _list_params(request)
    if error:
        return error
    page_number, size, direction = params
    payment = (request.GET.get("payment") or "").lower()
    if payment == "paid":
        queryset = queryset.filter(is_paid=True)
    elif payment == "unpaid":
        queryset = queryset.filter(is_paid=False)
    elif payment:
        return JsonResponse({"error": "Invalid payment filter."}, status=400)
    order_type = (request.GET.get("type") or "").upper()
    if order_type in Order.OrderType.values:
        queryset = queryset.filter(order_type=order_type)
    elif order_type:
        return JsonResponse({"error": "Invalid order type filter."}, status=400)
    queryset = queryset.order_by(*_ordering(direction, "created_at", "pk"))
    result = _page_response(
        queryset,
        page_number,
        size,
        "orders",
        lambda order: _serialize_order(order, include_history=True),
    )
    result.update(result["pagination"])
    return JsonResponse(result)


def _set_order_status(request, order_id):
    data, error = _json_body(request)
    if error:
        return error
    status = data.get("status")
    if status is None and isinstance(data.get("is_complete"), bool):
        status = Order.Status.COMPLETED if data["is_complete"] else Order.Status.PENDING
    is_paid = data.get("is_paid")
    payment_action = data.get("payment_action")
    invalid_reason = data.get("invalid_reason")
    receipt_reason = data.get("reason")
    if status is None and is_paid is None and payment_action is None:
        return JsonResponse({"error": "A valid order status or payment state is required."}, status=400)
    if status is not None:
        if not isinstance(status, str) or status.upper() not in Order.Status.values:
            return JsonResponse({"error": "A valid order status is required."}, status=400)
        status = status.upper()
        if status not in ADMIN_SETTABLE_STATUSES:
            return JsonResponse(
                {"error": "Status must be PENDING, OUT_FOR_DELIVERY, COMPLETED or INVALID."},
                status=400,
            )
    if is_paid is not None and not isinstance(is_paid, bool):
        return JsonResponse({"error": "'is_paid' must be true or false."}, status=400)
    if payment_action is not None and payment_action != "invalid_receipt":
        return JsonResponse({"error": "Invalid payment action."}, status=400)
    if payment_action is not None and is_paid is not None:
        return JsonResponse(
            {"error": "Receipt review and payment state must be updated separately."},
            status=400,
        )
    if status == Order.Status.INVALID and (
        not isinstance(invalid_reason, str) or not invalid_reason.strip()
    ):
        return JsonResponse({"error": "A reason is required when marking an order invalid."}, status=400)
    if payment_action == "invalid_receipt" and (
        not isinstance(receipt_reason, str) or not receipt_reason.strip()
    ):
        return JsonResponse({"error": "A reason is required when rejecting a GCash receipt."}, status=400)

    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return JsonResponse({"error": "Order not found."}, status=404)
        if order.status == Order.Status.CANCELLED:
            return JsonResponse({"error": "Cancelled orders can't be updated."}, status=409)
        if payment_action == "invalid_receipt" and (
            order.payment_method != Order.PaymentMethod.GCASH or not order.gcash_receipt
        ):
            return JsonResponse(
                {"error": "Only an uploaded GCash receipt can be marked invalid."}, status=409
            )
        if payment_action == "invalid_receipt" and order.is_paid:
            return JsonResponse({"error": "Verified payment receipts can't be rejected."}, status=409)
        if is_paid and order.payment_method == Order.PaymentMethod.GCASH and not order.gcash_receipt:
            return JsonResponse(
                {"error": "A GCash receipt must be uploaded before payment can be verified."},
                status=409,
            )
        if (
            is_paid
            and order.payment_method == Order.PaymentMethod.GCASH
            and order.payment_review_status == Order.PaymentReviewStatus.INVALID
        ):
            return JsonResponse(
                {"error": "The customer must submit a replacement receipt before payment can be verified."},
                status=409,
            )
        if (
            status == Order.Status.OUT_FOR_DELIVERY
            and order.order_type != Order.OrderType.DELIVERY
        ):
            return JsonResponse(
                {"error": "Only delivery orders can be marked Out for Delivery."}, status=400
            )
        update_fields = []
        if status is not None and status != order.status:
            previous_status = order.get_status_display()
            order.status = status
            update_fields.append("status")
            if status == Order.Status.INVALID:
                order.invalid_reason = invalid_reason.strip()
                update_fields.append("invalid_reason")
                _record_order_event(
                    order,
                    "ORDER_INVALID",
                    f"Order marked invalid: {order.invalid_reason}",
                    request.user,
                )
            else:
                if order.invalid_reason:
                    order.invalid_reason = ""
                    update_fields.append("invalid_reason")
                _record_order_event(
                    order,
                    "STATUS_CHANGED",
                    f"Order status changed from {previous_status} to {order.get_status_display()}.",
                    request.user,
                )
        if payment_action == "invalid_receipt":
            order.payment_review_status = Order.PaymentReviewStatus.INVALID
            order.receipt_invalid_reason = receipt_reason.strip()
            order.is_paid = False
            order.paid_at = None
            update_fields.extend(
                ["payment_review_status", "receipt_invalid_reason", "is_paid", "paid_at"]
            )
            _record_order_event(
                order,
                "RECEIPT_REJECTED",
                f"GCash receipt marked invalid: {order.receipt_invalid_reason}",
                request.user,
            )
        if is_paid is not None and is_paid != order.is_paid:
            order.is_paid = is_paid
            order.paid_at = timezone.now() if is_paid else None
            update_fields += ["is_paid", "paid_at"]
            if is_paid and order.payment_method == Order.PaymentMethod.GCASH:
                order.payment_review_status = Order.PaymentReviewStatus.VERIFIED
                update_fields.append("payment_review_status")
                event_type = "PAYMENT_VERIFIED"
                details = "GCash payment manually verified by admin."
            else:
                if (
                    not is_paid
                    and order.payment_method == Order.PaymentMethod.GCASH
                    and order.payment_review_status == Order.PaymentReviewStatus.VERIFIED
                ):
                    order.payment_review_status = Order.PaymentReviewStatus.PENDING
                    update_fields.append("payment_review_status")
                event_type = "PAYMENT_MARKED_PAID" if is_paid else "PAYMENT_MARKED_UNPAID"
                details = "Payment marked paid." if is_paid else "Payment marked unpaid."
            _record_order_event(order, event_type, details, request.user)
        if update_fields:
            order.save(update_fields=update_fields)
    order = _orders_with_relations().get(pk=order.pk)
    return JsonResponse(
        {"message": "Order updated.", "order": _serialize_order(order, include_history=True)}
    )


@_admin_api("PATCH")
def admin_order_status(request, pk):
    return _set_order_status(request, pk)


@_admin_api("GET")
def orders_info(request):
    today = timezone.localdate()
    pending = Order.objects.filter(status__in=PENDING_STATUSES).count()
    completed_today = Order.objects.filter(
        status=Order.Status.COMPLETED,
        created_at__date=today,
    ).count()
    return JsonResponse({"pending_orders": pending, "completed_today": completed_today})


@_admin_api("GET")
def admin_transaction_history(request):
    params, error = _list_params(request)
    if error:
        return error
    page_number, size, direction = params
    queryset = OrderAuditEvent.objects.select_related(
        "order__customer", "actor"
    ).order_by(*_ordering(direction, "created_at", "pk"))
    result = _page_response(
        queryset,
        page_number,
        size,
        "events",
        _serialize_audit_event,
    )
    result.update(result["pagination"])
    return JsonResponse(result)


# --------------------------------------------------------------------------- #
# Admin: feedbacks
# --------------------------------------------------------------------------- #

@_admin_api("GET")
def admin_feedbacks(request):
    queryset = Rating.objects.select_related("customer")
    raw_score = request.GET.get("rating", request.GET.get("score"))
    if raw_score:
        try:
            score = int(raw_score)
        except ValueError:
            return JsonResponse({"error": "'rating' must be between 1 and 5."}, status=400)
        if score not in range(1, 6):
            return JsonResponse({"error": "'rating' must be between 1 and 5."}, status=400)
        queryset = queryset.filter(score=score)
    params, error = _list_params(request)
    if error:
        return error
    page_number, size, direction = params
    queryset = queryset.order_by(*_ordering(direction, "date", "pk"))
    return JsonResponse(_page_response(queryset, page_number, size, "feedbacks", _serialize_feedback))


@_admin_api("GET")
def feedbacks_info(request):
    summary = Rating.objects.aggregate(total=Count("id"), average=Avg("score"))
    counts = dict(
        Rating.objects.values_list("score").annotate(count=Count("id")).order_by("score")
    )
    total = summary["total"]
    positive = sum(counts.get(star, 0) for star in (4, 5))
    return JsonResponse(
        {
            "total_feedback": total,
            "average_rating": round(summary["average"], 2) if summary["average"] else 0,
            "rating_counts": {str(star): counts.get(star, 0) for star in range(1, 6)},
            "positive_feedback_percent": round(positive * 100 / total) if total else 0,
        }
    )


# --------------------------------------------------------------------------- #
# Menu items (admin + customer)
# --------------------------------------------------------------------------- #

def _menu_queryset(request, customer=False):
    queryset = FoodItem.objects.select_related("category").prefetch_related("addons")
    if customer:
        queryset = queryset.filter(available=True)
    search = (request.GET.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    category = request.GET.get("category")
    if category:
        if category.isdigit():
            queryset = queryset.filter(category_id=int(category))
        else:
            queryset = queryset.filter(category__name__iexact=category)
    return queryset


def _list_menu_items(request, customer=False):
    params, error = _list_params(request)
    if error:
        return error
    page_number, size, direction = params

    sort_by = request.GET.get("sort_by", "id").lower()
    if sort_by not in MENU_SORT_FIELDS:
        return JsonResponse(
            {"error": f"'sort_by' must be one of: {', '.join(MENU_SORT_FIELDS)}."},
            status=400,
        )

    queryset = _menu_queryset(request, customer=customer)
    if not customer and request.GET.get("available") is not None:
        raw = request.GET["available"].lower()
        if raw not in ("true", "false"):
            return JsonResponse({"error": "'available' must be 'true' or 'false'."}, status=400)
        queryset = queryset.filter(available=raw == "true")

    queryset = queryset.order_by(*_ordering(direction, MENU_SORT_FIELDS[sort_by], "pk"))
    result = _page_response(queryset, page_number, size, "items", _serialize_food_item)
    result["sort"] = direction
    result["sort_by"] = sort_by
    return JsonResponse(result)


def _parse_addon_input(data):
    addon_input = data.get("addons", data.get("addon_ids", []))
    if isinstance(addon_input, str):
        try:
            addon_input = json.loads(addon_input)
        except json.JSONDecodeError:
            addon_input = [part.strip() for part in addon_input.split(",") if part.strip()]
    if not isinstance(addon_input, list):
        return None, JsonResponse({"error": "'addons' must be a list."}, status=400)
    return addon_input, None


def _prepare_addons(addon_input):
    """Return ([("new" | "existing", addon), ...], error)."""
    prepared = []
    for value in addon_input:
        if isinstance(value, dict):
            name = value.get("name")
            raw_price = value.get("price", "0")
            if not isinstance(name, str) or not name.strip():
                return None, JsonResponse({"error": "Each add-on needs a name."}, status=400)
            try:
                price = Decimal(str(raw_price))
            except (InvalidOperation, TypeError, ValueError):
                return None, JsonResponse({"error": "Add-on prices must be valid numbers."}, status=400)
            if not price.is_finite() or price < 0:
                return None, JsonResponse(
                    {"error": "Add-on prices must be finite and non-negative."}, status=400
                )
            addon = FoodAddon(name=name.strip(), price=price)
            try:
                addon.full_clean()
            except ValidationError as exc:
                return None, JsonResponse({"errors": exc.message_dict}, status=400)
            prepared.append(("new", addon))
        else:
            try:
                addon = FoodAddon.objects.get(pk=int(value), available=True)
            except (TypeError, ValueError, FoodAddon.DoesNotExist):
                return None, JsonResponse({"error": "Invalid add-on ID."}, status=400)
            prepared.append(("existing", addon))
    return prepared, None


def _save_menu_item(request, item=None):
    try:
        data, files = parse_payload(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    addon_input, error = _parse_addon_input(data)
    if error:
        return error

    form_data = data.copy()
    if item is not None:
        # PATCH: fall back to the current values for any field not sent.
        for field in ("name", "description", "category", "price", "available"):
            if field not in form_data:
                form_data[field] = (
                    item.category_id if field == "category" else getattr(item, field)
                )
    elif "available" not in form_data:
        form_data["available"] = True

    form = FoodItemForm(form_data, files, instance=item)
    if not form.is_valid():
        return JsonResponse(
            {"error": "Validation failed.", "errors": form_errors(form)}, status=400
        )

    prepared_addons, error = _prepare_addons(addon_input)
    if error:
        return error

    try:
        with transaction.atomic():
            saved_item = form.save()
            if "addons" in data or "addon_ids" in data:
                addons = []
                for kind, addon in prepared_addons:
                    if kind == "new":
                        addon.save()
                    addons.append(addon)
                saved_item.addons.set(addons)
    except IntegrityError:
        return JsonResponse({"error": "Unable to save menu item."}, status=400)
    return JsonResponse(_serialize_food_item(saved_item), status=201 if item is None else 200)


@_admin_api("GET", "POST")
def menu_items(request):
    if request.method == "POST":
        return _save_menu_item(request)
    return _list_menu_items(request)


@_admin_api("PATCH", "DELETE")
def admin_menu_item(request, pk):
    try:
        item = FoodItem.objects.select_related("category").prefetch_related("addons").get(pk=pk)
    except FoodItem.DoesNotExist:
        return JsonResponse({"error": "Menu item not found."}, status=404)
    if request.method == "DELETE":
        try:
            item.delete()
        except IntegrityError:
            return JsonResponse({"error": "Menu item is used by an existing order."}, status=409)
        return JsonResponse({"message": "Menu item deleted.", "id": pk})
    return _save_menu_item(request, item)


@require_http_methods(["GET"])
def customer_menu_items(request):
    return _list_menu_items(request, customer=True)


# --------------------------------------------------------------------------- #
# Customer: orders
# --------------------------------------------------------------------------- #

MAX_ADDRESS_LENGTH = Order._meta.get_field("delivery_address").max_length


def _clean_order_type(value):
    if isinstance(value, str):
        normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
        if normalized in Order.OrderType.values:
            return normalized, None
    return None, JsonResponse(
        {"error": "'order_type' must be DINE_IN, PICKUP or DELIVERY."}, status=400
    )


def _clean_address(value):
    if not isinstance(value, str) or not value.strip():
        return None, JsonResponse({"error": "A delivery address is required."}, status=400)
    value = " ".join(value.split())
    if len(value) > MAX_ADDRESS_LENGTH:
        return None, JsonResponse(
            {"error": f"Address must be {MAX_ADDRESS_LENGTH} characters or fewer."}, status=400
        )
    return value, None


def _clean_phone(value):
    if not isinstance(value, str) or not value.strip():
        return None, JsonResponse(
            {"error": "A contact phone number is required for pickup and delivery orders."},
            status=400,
        )
    value = value.strip()
    if not PHONE_RE.match(value):
        return None, JsonResponse({"error": "Enter a valid phone number."}, status=400)
    return value, None


def _order_lines(requested_items):
    if not isinstance(requested_items, list) or not requested_items:
        return None, JsonResponse({"error": "'items' must be a non-empty list."}, status=400)
    lines = []
    total = Decimal("0.00")
    for requested in requested_items:
        if not isinstance(requested, dict):
            return None, JsonResponse({"error": "Each item must be an object."}, status=400)
        item_id = requested.get("menu_item_id", requested.get("id"))
        quantity = requested.get("quantity")
        try:
            quantity = int(quantity)
            food_item = FoodItem.objects.prefetch_related("addons").get(
                pk=int(item_id), available=True
            )
        except (TypeError, ValueError, FoodItem.DoesNotExist):
            return None, JsonResponse({"error": "Invalid or unavailable menu item."}, status=400)
        if quantity < 1 or quantity > 99:
            return None, JsonResponse({"error": "Quantity must be between 1 and 99."}, status=400)
        selected_ids = requested.get("addon_ids", requested.get("addons", []))
        if not isinstance(selected_ids, list):
            return None, JsonResponse({"error": "'addon_ids' must be a list."}, status=400)
        allowed_addons = {addon.pk: addon for addon in food_item.addons.filter(available=True)}
        selected = []
        for addon_id in selected_ids:
            if isinstance(addon_id, dict):
                addon_id = addon_id.get("id")
            try:
                addon = allowed_addons[int(addon_id)]
            except (TypeError, ValueError, KeyError):
                return None, JsonResponse({"error": "Invalid add-on for menu item."}, status=400)
            selected.append(addon)
        lines.append((food_item, quantity, selected))
        addons_total = sum((addon.price for addon in selected), Decimal("0.00"))
        total += (food_item.price + addons_total) * quantity
    return (lines, total), None


def _write_order_items(order, lines):
    order.items.all().delete()
    for food_item, quantity, addons in lines:
        order_item = OrderItem.objects.create(
            order=order,
            food_item=food_item,
            quantity=quantity,
            price=food_item.price,
        )
        OrderItemAddon.objects.bulk_create(
            [
                OrderItemAddon(order_item=order_item, name=addon.name, price=addon.price)
                for addon in addons
            ]
        )


@require_http_methods(["GET"])
def customer_orders(request, user_id=None):
    error = _require_customer(request, user_id)
    if error:
        return error
    params, error = _list_params(request)
    if error:
        return error
    page_number, size, direction = params
    queryset, error = _filter_orders_by_status(
        _orders_with_relations(request.user.orders.all()), request.GET.get("filter")
    )
    if error:
        return error
    queryset = queryset.order_by(*_ordering(direction, "created_at", "pk"))
    return JsonResponse(_page_response(queryset, page_number, size, "orders", _serialize_order))


@csrf_protect
@require_http_methods(["POST"])
def customer_create_order(request):
    error = _require_customer(request)
    if error:
        return error
    data, error = _json_body(request)
    if error:
        return error
    order_type, error = _clean_order_type(data.get("order_type"))
    if error:
        return error
    payment_method = data.get(
        "payment_method",
        Order.PaymentMethod.CASH_ON_DELIVERY
        if order_type == Order.OrderType.DELIVERY
        else Order.PaymentMethod.CASH_ON_PICKUP,
    )
    if payment_method not in Order.PaymentMethod.values:
        return JsonResponse({"error": "Select a valid payment method."}, status=400)
    if (
        order_type == Order.OrderType.DELIVERY
        and payment_method == Order.PaymentMethod.CASH_ON_PICKUP
    ) or (
        order_type != Order.OrderType.DELIVERY
        and payment_method == Order.PaymentMethod.CASH_ON_DELIVERY
    ):
        return JsonResponse(
            {"error": "Choose the cash payment option that matches your order type."},
            status=400,
        )
    # Dine-In needs neither a phone number nor an address; Pickup needs a phone
    # number; Delivery needs both.
    phone = address = ""
    if order_type != Order.OrderType.DINE_IN:
        phone, error = _clean_phone(data.get("contact_phone"))
        if error:
            return error
    if order_type == Order.OrderType.DELIVERY:
        address, error = _clean_address(data.get("address", data.get("delivery_address")))
        if error:
            return error
    result, error = _order_lines(data.get("items"))
    if error:
        return error
    lines, total = result
    with transaction.atomic():
        order = Order.objects.create(
            customer=request.user,
            order_type=order_type,
            payment_method=payment_method,
            payment_review_status=(
                Order.PaymentReviewStatus.AWAITING_RECEIPT
                if payment_method == Order.PaymentMethod.GCASH
                else Order.PaymentReviewStatus.NOT_REQUIRED
            ),
            contact_phone=phone,
            delivery_address=address,
            total_amount=total,
            status=Order.Status.PENDING,
            estimated_time=timezone.now() + timedelta(minutes=30),
        )
        _write_order_items(order, lines)
        _record_order_event(
            order,
            "ORDER_PLACED",
            f"Order placed with {order.get_payment_method_display()} payment.",
            request.user,
        )
    order = _orders_with_relations().get(pk=order.pk)
    return JsonResponse(
        {
            "order_number": f"BJFC-{order.pk:06d}",
            "status": order.status,
            "eta": order.estimated_time.isoformat(),
            "order": _serialize_order(order),
        },
        status=201,
    )


@csrf_protect
@require_http_methods(["GET", "POST"])
def customer_upload_gcash_receipt(request, pk):
    if request.method == "GET":
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=401)
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return JsonResponse({"error": "Order not found."}, status=404)
        if not request.user.is_staff and order.customer_id != request.user.pk:
            return JsonResponse({"error": "You can only view your own receipt."}, status=403)
        if not order.gcash_receipt:
            return JsonResponse({"error": "No receipt has been uploaded."}, status=404)
        receipt_file = order.gcash_receipt.open("rb")
        with Image.open(receipt_file) as image:
            content_type = Image.MIME.get(image.format, "application/octet-stream")
        receipt_file.seek(0)
        response = FileResponse(receipt_file, content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    error = _require_customer(request)
    if error:
        return error
    upload = request.FILES.get("receipt")
    if upload is None:
        return JsonResponse({"error": "Choose a receipt image to upload."}, status=400)
    if upload.size > 5 * 1024 * 1024:
        return JsonResponse({"error": "Receipt images must be 5 MB or smaller."}, status=400)
    try:
        receipt = forms.ImageField().clean(upload)
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)

    with transaction.atomic():
        try:
            order = request.user.orders.select_for_update().get(pk=pk)
        except Order.DoesNotExist:
            return JsonResponse({"error": "Order not found."}, status=404)
        if order.payment_method != Order.PaymentMethod.GCASH:
            return JsonResponse({"error": "Receipts are only used for GCash orders."}, status=409)
        if order.status in (Order.Status.CANCELLED, Order.Status.INVALID):
            return JsonResponse(
                {"error": "Receipts can't be submitted for cancelled or invalid orders."},
                status=409,
            )
        if order.is_paid:
            return JsonResponse({"error": "Verified payment receipts cannot be changed."}, status=409)
        if order.gcash_receipt and order.payment_review_status != Order.PaymentReviewStatus.INVALID:
            return JsonResponse(
                {"error": "A submitted receipt can only be replaced after admin rejection."},
                status=409,
            )
        order.gcash_receipt = receipt
        order.payment_review_status = Order.PaymentReviewStatus.PENDING
        order.receipt_invalid_reason = ""
        order.save(
            update_fields=[
                "gcash_receipt",
                "payment_review_status",
                "receipt_invalid_reason",
            ]
        )
        _record_order_event(
            order,
            "RECEIPT_SUBMITTED",
            "Customer submitted a GCash receipt for manual review.",
            request.user,
        )
    return JsonResponse(
        {
            "message": "Receipt uploaded for admin review.",
            "gcash_receipt": f"/api/orders/{order.pk}/gcash-receipt",
            "payment_review_status": order.payment_review_status,
        }
    )


def _locked_customer_order(request, pk):
    """The customer's own order, row-locked. Call inside transaction.atomic()."""
    try:
        return request.user.orders.select_for_update().get(pk=pk), None
    except Order.DoesNotExist:
        return None, JsonResponse({"error": "Order not found."}, status=404)


@csrf_protect
@require_http_methods(["PATCH"])
def customer_order(request, pk):
    """Edit the delivery address of one of the customer's own orders."""
    error = _require_customer(request)
    if error:
        return error
    data, error = _json_body(request)
    if error:
        return error
    if not data or set(data) - {"address", "delivery_address"}:
        return JsonResponse({"error": "Only the delivery address can be changed."}, status=400)
    address, error = _clean_address(data.get("address", data.get("delivery_address")))
    if error:
        return error
    with transaction.atomic():
        order, error = _locked_customer_order(request, pk)
        if error:
            return error
        if order.order_type != Order.OrderType.DELIVERY:
            return JsonResponse({"error": "Only delivery orders have an address."}, status=409)
        if not order.can_customer_edit_address:
            return JsonResponse(
                {
                    "error": "The address can no longer be changed because the order is "
                    f"{order.get_status_display()}."
                },
                status=409,
            )
        if address != order.delivery_address:
            OrderAddressChange.objects.create(
                order=order,
                old_address=order.delivery_address,
                new_address=address,
                changed_by=request.user,
            )
            _record_order_event(
                order,
                "ADDRESS_CHANGED",
                "Customer updated the delivery address.",
                request.user,
            )
            order.delivery_address = address
            order.save(update_fields=["delivery_address"])
    order = _orders_with_relations().get(pk=order.pk)
    return JsonResponse({"message": "Delivery address updated.", "order": _serialize_order(order)})


@csrf_protect
@require_http_methods(["POST"])
def customer_cancel_order(request, pk):
    """Cancel one of the customer's own orders (not once it is Out for Delivery)."""
    error = _require_customer(request)
    if error:
        return error
    with transaction.atomic():
        order, error = _locked_customer_order(request, pk)
        if error:
            return error
        if not order.can_customer_cancel:
            reason = (
                "This order is already cancelled."
                if order.status == Order.Status.CANCELLED
                else "This order can no longer be cancelled because it is "
                f"{order.get_status_display()}."
            )
            return JsonResponse({"error": reason}, status=409)
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])
        _record_order_event(order, "ORDER_CANCELLED", "Customer cancelled the order.", request.user)
    order = _orders_with_relations().get(pk=order.pk)
    return JsonResponse({"message": "Order cancelled.", "order": _serialize_order(order)})


# --------------------------------------------------------------------------- #
# Admin: users
# --------------------------------------------------------------------------- #

def _user_row(user):
    """Safe user fields only. Never include the password."""
    joined = getattr(user, "date_joined", None)
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "first_name": getattr(user, "first_name", ""),
        "last_name": getattr(user, "last_name", ""),
        "phone_number": user.phone_number,
        "is_staff": user.is_staff,
        "date_joined": joined.isoformat() if joined else None,
    }


@_admin_api("GET")
def admin_users(request):
    """GET /api/admin/users?size=10&page=2&sort=asc|desc[&search=...]"""
    # --- read and validate query params ---
    try:
        size = int(request.GET.get("size", 10))
        page_number = int(request.GET.get("page", 1))
    except ValueError:
        return JsonResponse({"error": "size and page must be numbers."}, status=400)

    if size < 1 or page_number < 1:
        return JsonResponse({"error": "size and page must be 1 or greater."}, status=400)
    size = min(size, 100)  # cap so nobody requests 1,000,000 rows

    sort = (request.GET.get("sort") or "asc").lower()
    if sort not in ("asc", "desc"):
        return JsonResponse({"error": "sort must be 'asc' or 'desc'."}, status=400)

    # --- query ---
    queryset = User.objects.all()
    search = (request.GET.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
    queryset = queryset.order_by("-pk" if sort == "desc" else "pk")

    # --- paginate ---
    paginator = Paginator(queryset, size)
    page = paginator.get_page(page_number)

    return JsonResponse({
        "users": [_user_row(u) for u in page.object_list],
        "pagination": {
            "page": page.number,
            "size": size,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        },
        "total": paginator.count,
        "total_pages": paginator.num_pages,
        "page": page.number,
        "size": size,
    })

# --------------------------------------------------------------------------- #
# Profiles and passwords
# --------------------------------------------------------------------------- #

@_admin_api("GET", "PATCH")
def admin_profile(request):
    user = request.user
    if request.method == "GET":
        return JsonResponse(_serialize_user(user))
    data, error = _json_body(request)
    if error:
        return error
    allowed = {"username", "email", "first_name", "last_name", "display_name"}
    unknown = set(data) - allowed
    if unknown:
        return JsonResponse({"error": "Unknown profile fields.", "fields": sorted(unknown)}, status=400)
    if not data:
        return JsonResponse({"error": "Provide at least one profile field."}, status=400)
    if "display_name" in data:
        display_name = data.pop("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            return JsonResponse({"error": "'display_name' must be a non-empty string."}, status=400)
        data["first_name"] = display_name.strip()
        data["last_name"] = ""
    for field, value in data.items():
        if not isinstance(value, str) or (
            field not in ("first_name", "last_name") and not value.strip()
        ):
            return JsonResponse({"error": f"'{field}' must be a non-empty string."}, status=400)
        setattr(user, field, value.strip())
    if "email" in data:
        try:
            validate_email(user.email)
        except ValidationError:
            return JsonResponse({"error": "Invalid email address."}, status=400)
        if User.objects.filter(email__iexact=user.email).exclude(pk=user.pk).exists():
            return JsonResponse({"error": "Email already registered."}, status=409)
    if "username" in data and User.objects.filter(username=user.username).exclude(pk=user.pk).exists():
        return JsonResponse({"error": "Username already taken."}, status=409)
    user.save(update_fields=sorted(data))
    return JsonResponse(_serialize_user(user))


def _change_password(request, admin=False):
    user = request.user
    if admin and (not user.is_authenticated or not user.is_staff):
        return JsonResponse({"error": "Admin access required."}, status=403)
    if not admin and (not user.is_authenticated or user.is_staff):
        return JsonResponse({"error": "Customer access required."}, status=401)
    data, error = _json_body(request)
    if error:
        return error
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    if (
        not isinstance(old_password, str)
        or not isinstance(new_password, str)
        or not old_password
        or not new_password
    ):
        return JsonResponse({"error": "Old and new passwords are required."}, status=400)
    if not user.check_password(old_password):
        return JsonResponse({"error": "Current password is incorrect."}, status=400)
    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    update_session_auth_hash(request, user)
    return JsonResponse({"message": "Password changed successfully."})


@csrf_protect
@require_http_methods(["PATCH"])
def admin_password(request):
    return _change_password(request, admin=True)

@csrf_protect
@require_http_methods(["PATCH"])
def customer_password(request, user_id):
    error = _require_customer(request, user_id)
    if error:
        return error
    return _change_password(request)


@csrf_protect
def customer_profile(request, user_id=None):
    error = _require_customer(request, user_id)
    if error:
        return error
    user = request.user

    if request.method == "GET":
        return JsonResponse(_serialize_user(user))

    if request.method == "PATCH":
        data, error = _json_body(request)
        if error:
            return error
        allowed = {"username", "email", "first_name", "last_name", "phone_number"}
        unknown = set(data) - allowed
        if unknown:
            return JsonResponse({"error": "Unknown profile fields.", "fields": sorted(unknown)}, status=400)
        if not data:
            return JsonResponse({"error": "Provide at least one profile field."}, status=400)
        for field, value in data.items():
            if not isinstance(value, str):
                return JsonResponse({"error": f"'{field}' must be a string."}, status=400)
            setattr(user, field, value.strip())
        if not user.username or not user.email:
            return JsonResponse({"error": "Username and email cannot be empty."}, status=400)
        try:
            validate_email(user.email)
        except ValidationError:
            return JsonResponse({"error": "Invalid email address."}, status=400)
        if User.objects.filter(username=user.username).exclude(pk=user.pk).exists():
            return JsonResponse({"error": "Username already taken."}, status=409)
        if User.objects.filter(email__iexact=user.email).exclude(pk=user.pk).exists():
            return JsonResponse({"error": "Email already registered."}, status=409)
        user.save(update_fields=sorted(data))
        return JsonResponse({"message": "Profile updated.", "user": _serialize_user(user)})

    if request.method == "DELETE":
        data, error = _json_body(request)
        if error:
            return error
        password = data.get("password")
        if not isinstance(password, str) or not password:
            return JsonResponse({"error": "Password is required."}, status=400)
        if data.get("confirm_deletion") != "DELETE_MY_ACCOUNT":
            return JsonResponse({"error": 'Confirmation must be "DELETE_MY_ACCOUNT".'}, status=400)
        if not user.check_password(password):
            return JsonResponse({"error": "Invalid password."}, status=401)
        user.delete()
        logout(request)
        return JsonResponse({"message": "Account deleted successfully."})

    response = JsonResponse({"error": "Method not allowed."}, status=405)
    response["Allow"] = "GET, PATCH, DELETE"
    return response


# --------------------------------------------------------------------------- #
# Admin: editable pages (menu / about / contact via PageInfo, landing via LandingPage)
# --------------------------------------------------------------------------- #

def _get_page(slug):
    defaults = PAGE_DEFAULTS[slug]
    page, _ = PageInfo.objects.get_or_create(
        slug=slug,
        defaults={"title": defaults["title"], "description": defaults["description"]},
    )
    return page


def _page_api(request, slug):
    """Shared GET/PATCH logic for PageInfo-backed pages."""
    if request.method == "GET":
        return JsonResponse(_serialize_page(_get_page(slug)))

    data, error = _json_body(request)
    if error:
        return error
    unknown = set(data) - {"title", "description"}
    if unknown:
        return JsonResponse({"error": "Unknown page fields.", "fields": sorted(unknown)}, status=400)
    if not data:
        return JsonResponse({"error": "Provide a title or description to update."}, status=400)
    for field, value in data.items():
        if not isinstance(value, str) or not value.strip():
            return JsonResponse({"error": f"'{field}' must be a non-empty string."}, status=400)

    page = _get_page(slug)
    for field, value in data.items():
        setattr(page, field, value.strip())
    page.save(update_fields=list(data))
    return JsonResponse(_serialize_page(page))



@_admin_api("GET", "PATCH")
def menu_page(request):
    return _page_api(request, "menu")


@_admin_api("GET", "PATCH")
def about_page(request):
    return _page_api(request, "about")


@_admin_api("GET", "PATCH")
def contact_page(request):
    return _page_api(request, "contact")


@_admin_api("GET", "PATCH")
def page_content(request, slug):
    if slug not in PAGE_DEFAULTS:
        return JsonResponse(
            {"error": "Page not found."},
            status=404,
        )

    return _page_api(request, slug)


@_admin_api("GET", "PATCH")
def admin_landing_page(request):
    if request.method not in ["GET", "PATCH"]:
        return JsonResponse(
            {"error": "Method not allowed."},
            status=405
        )

    page = LandingPage.objects.order_by("pk").first()
    if page is None:
        page = LandingPage.objects.create(**LANDING_DEFAULTS)

    if request.method == "GET":
        return JsonResponse(_serialize_landing_page(page))

    data, error = _json_body(request)
    if error:
        return error
    unknown = set(data) - set(LANDING_FIELDS)
    if unknown:
        return JsonResponse(
            {"error": "Unknown landing-page fields.", "fields": sorted(unknown)}, status=400
        )
    if not data:
        return JsonResponse({"error": "Provide at least one field to update."}, status=400)
    for field, value in data.items():
        if not isinstance(value, str):
            return JsonResponse({"error": f"'{field}' must be a string."}, status=400)
        setattr(page, field, value.strip())
    try:
        page.full_clean()
    except ValidationError as exc:
        return JsonResponse({"errors": exc.message_dict}, status=400)
    page.save(update_fields=[*data, "updated_at"])
    return JsonResponse(_serialize_landing_page(page))


@_admin_api("GET", "PATCH")
def store_information(request):
    store = StoreInformation.objects.order_by("pk").first()
    if request.method == "GET":
        if store is None:
            return JsonResponse({"error": "Store information not found."}, status=404)
        return JsonResponse(_serialize_store(store))

    data, error = _json_body(request)
    if error:
        return error
    if set(data) - {"contact", "address", "email"} or not data:
        return JsonResponse({"error": "Provide one or more valid store fields."}, status=400)
    if store is None:
        store = StoreInformation(storename="BJFC", contact="", address="")
    for field, value in data.items():
        if not isinstance(value, str) or (field != "email" and not value.strip()):
            return JsonResponse({"error": f"'{field}' must be a non-empty string."}, status=400)
        setattr(store, field, value.strip())
    if "email" in data and store.email:
        try:
            validate_email(store.email)
        except ValidationError:
            return JsonResponse({"error": "Invalid store email address."}, status=400)
    if not store.contact or not store.address:
        return JsonResponse({"error": "Store contact and address are required."}, status=400)
    store.save()
    return JsonResponse(_serialize_store(store))


# --------------------------------------------------------------------------- #
# Contact messages
# --------------------------------------------------------------------------- #

@_admin_api("GET")
def admin_contact_messages(request):
    queryset = ContactMessage.objects.select_related("sender")
    status_filter = request.GET.get("status")
    if status_filter:
        valid_statuses = [value for value, _ in ContactMessage.Status.choices]
        if status_filter not in valid_statuses:
            return JsonResponse({"error": "Invalid message status."}, status=400)
        queryset = queryset.filter(status=status_filter)
    params, error = _list_params(request)
    if error:
        return error
    page_number, size, direction = params
    queryset = queryset.order_by(*_ordering(direction, "created_at", "pk"))
    return JsonResponse(_page_response(queryset, page_number, size, "messages", _serialize_contact))


@_admin_api("PATCH")
def admin_contact_message(request, pk):
    data, error = _json_body(request)
    if error:
        return error
    status = data.get("status")
    if status not in (ContactMessage.Status.READ, ContactMessage.Status.RESOLVED):
        return JsonResponse({"error": "Status must be 'read' or 'resolved'."}, status=400)
    try:
        message = ContactMessage.objects.get(pk=pk)
    except ContactMessage.DoesNotExist:
        return JsonResponse({"error": "Contact message not found."}, status=404)
    message.status = status
    message.save(update_fields=["status"])
    return JsonResponse(_serialize_contact(message))


@csrf_exempt
@require_http_methods(["POST"])
def contact_messages(request):
    try:
        data, _ = parse_payload(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    form = ContactMessageForm(data)
    if not form.is_valid():
        return JsonResponse(
            {"error": "Please correct the highlighted fields.", "errors": form_errors(form)},
            status=400,
        )
    message = form.save(commit=False)
    message.sender = request.user if request.user.is_authenticated else None
    message.save()
    return JsonResponse(
        {"message": "Thank you! Your message has been received.", "id": message.pk},
        status=201,
    )


# --------------------------------------------------------------------------- #
# Customer: favorites
# --------------------------------------------------------------------------- #

@require_http_methods(["GET"])
def customer_favorites(request):
    error = _require_customer(request)
    if error:
        return error
    params, error = _list_params(request)
    if error:
        return error
    page_number, size, direction = params
    queryset = (
        Favorite.objects.filter(customer=request.user)
        .select_related("food_item__category")
        .prefetch_related("food_item__addons")
        .order_by("-created_at", "-pk")
    )
    return JsonResponse(
        _page_response(
            queryset,
            page_number,
            size,
            "items",
            lambda favorite: _serialize_food_item(favorite.food_item),
        )
    )


@csrf_protect
@require_http_methods(["PUT", "DELETE"])
def customer_favorite(request, menu_item_id):
    error = _require_customer(request)
    if error:
        return error
    try:
        item = FoodItem.objects.get(pk=menu_item_id, available=True)
    except FoodItem.DoesNotExist:
        return JsonResponse({"error": "Available menu item not found."}, status=404)
    if request.method == "PUT":
        _, created = Favorite.objects.get_or_create(customer=request.user, food_item=item)
        return JsonResponse(
            {"message": "Favorite added.", "item": _serialize_food_item(item)},
            status=201 if created else 200,
        )
    deleted, _ = Favorite.objects.filter(customer=request.user, food_item=item).delete()
    if not deleted:
        return JsonResponse({"error": "Favorite not found."}, status=404)
    return JsonResponse({"message": "Favorite removed."})