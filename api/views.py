import json
from datetime import timedelta
from functools import wraps
from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods

from core.models import (
    ContactMessage,
    Favorite,
    FoodAddon,
    FoodItem,
    LandingPage,
    Order,
    OrderItem,
    OrderItemAddon,
    PageInfo,
    Rating,
    StoreInformation,
    User,
)
from .forms import ContactMessageForm, FoodItemForm, form_errors, parse_payload

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
PENDING_STATUSES = (
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.PREPARING,
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
MENU_SORT_FIELDS = {
    "id": "id",
    "name": "name",
    "price": "price",
    "category": "category__name",
}


def _json_body(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "Invalid JSON data."}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({"error": "Expected a JSON object."}, status=400)
    return data, None


def _admin_api(*methods):
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
    if user_id is not None and request.user.pk != user_id:
        return JsonResponse({"error": "You can only access your own account."}, status=403)
    if request.user.is_staff:
        return JsonResponse({"error": "Customer access required."}, status=403)
    return None


def _pagination(request):
    try:
        page = int(request.GET.get("page", "1"))
        size = int(request.GET.get("size", str(DEFAULT_PAGE_SIZE)))
    except (TypeError, ValueError):
        return None, JsonResponse(
            {"error": "'page' and 'size' must be positive integers."}, status=400
        )
    if page < 1 or size < 1:
        return None, JsonResponse(
            {"error": "'page' and 'size' must be positive integers."}, status=400
        )
    return (page, min(size, MAX_PAGE_SIZE)), None


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


def _serialize_order(order):
    return {
        "id": order.pk,
        "order_number": f"BJFC-{order.pk:06d}",
        "customer": {
            "id": order.customer_id,
            "name": order.customer.get_full_name() or order.customer.username,
            "username": order.customer.username,
            "email": order.customer.email,
            "phone": order.customer.phone_number,
        },
        "customer_name": order.customer.get_full_name() or order.customer.username,
        "status": order.status,
        "status_display": order.get_status_display(),
        "created_at": order.created_at.isoformat(),
        "estimated_time": (
            order.estimated_time.isoformat() if order.estimated_time else None
        ),
        "eta": order.estimated_time.isoformat() if order.estimated_time else None,
        "total_amount": str(order.total_amount),
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
            for item in order.items.select_related("food_item").prefetch_related(
                "selected_addons"
            )
        ],
    }


def _serialize_contact(message):
    return {
        "id": message.pk,
        "name": message.name,
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


def _item_sort(request):
    direction = request.GET.get("sort", "asc").lower()
    if direction not in ("asc", "desc"):
        return None, JsonResponse(
            {"error": "'sort' must be 'asc' or 'desc'."}, status=400
        )
    return direction, None


@require_http_methods(["GET"])
def test_api_response(request):
    return JsonResponse({"message": "API is running."})


@csrf_protect
@require_http_methods(["POST"])
def login_api(request):
    data, error = _json_body(request)
    if error:
        return error
    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return JsonResponse(
            {"error": "Username and password are required."}, status=400
        )
    user = authenticate(request=request, username=username, password=password)
    if user is None:
        return JsonResponse({"error": "Invalid username or password."}, status=401)
    if not user.is_active:
        return JsonResponse({"error": "Account is inactive."}, status=403)
    login(request, user)
    return JsonResponse(
        {"message": "Login successful.", "user": _serialize_user(user)}, status=200
    )


@csrf_protect
@require_http_methods(["POST"])
def register(request):
    data, error = _json_body(request)
    if error:
        return error
    required = ("username", "last_name", "first_name", "email", "password", "confirm_password")
    if any(not isinstance(data.get(field), str) for field in required):
        return JsonResponse(
            {"error": "All fields are required and must be strings."}, status=400
        )
    values = {field: data[field].strip() for field in required if field not in ("password", "confirm_password")}
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
    user = User(
        username=values["username"],
        email=values["email"].lower(),
        first_name=values["first_name"],
        last_name=values["last_name"],
    )
    try:
        validate_password(password, user=user)
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


@_admin_api("GET")
def admin_orders(request):
    queryset = Order.objects.select_related("customer").prefetch_related(
        "items__food_item", "items__selected_addons"
    )
    status_filter = request.GET.get("filter", "").lower()
    if status_filter:
        if status_filter == "pending":
            queryset = queryset.filter(status__in=PENDING_STATUSES)
        elif status_filter == "completed":
            queryset = queryset.filter(status=Order.Status.COMPLETED)
        elif status_filter.upper() in Order.Status.values:
            queryset = queryset.filter(status=status_filter.upper())
        else:
            return JsonResponse({"error": "Invalid status filter."}, status=400)
    pagination, error = _pagination(request)
    if error:
        return error
    direction, error = _item_sort(request)
    if error:
        return error
    page_number, size = pagination
    prefix = "-" if direction == "desc" else ""
    queryset = queryset.order_by(f"{prefix}created_at", f"{prefix}pk")
    result = _page_response(queryset, page_number, size, "orders", _serialize_order)
    result.update(result["pagination"])
    return JsonResponse(result)


def _set_order_status(request, order_id):
    data, error = _json_body(request)
    if error:
        return error
    status = data.get("status")
    if status is None and isinstance(data.get("is_complete"), bool):
        status = Order.Status.COMPLETED if data["is_complete"] else Order.Status.PENDING
    if not isinstance(status, str):
        return JsonResponse({"error": "A valid order status is required."}, status=400)
    status = status.upper()
    if status not in Order.Status.values:
        return JsonResponse({"error": "Invalid order status."}, status=400)
    try:
        order = Order.objects.select_related("customer").get(pk=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found."}, status=404)
    order.status = status
    order.save(update_fields=["status"])
    return JsonResponse({"message": "Order status updated.", "order": _serialize_order(order)})


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
    pagination, error = _pagination(request)
    if error:
        return error
    direction, error = _item_sort(request)
    if error:
        return error
    page_number, size = pagination
    queryset = queryset.order_by(
        f"{'-' if direction == 'desc' else ''}date",
        f"{'-' if direction == 'desc' else ''}pk",
    )

    def serialize(rating):
        return {
            "id": rating.pk,
            "customer": {
                "id": rating.customer_id,
                "name": rating.customer.get_full_name() or rating.customer.username,
                "email": rating.customer.email,
                "phone": rating.customer.phone_number,
            },
            "customer_name": rating.customer.get_full_name() or rating.customer.username,
            "email": rating.customer.email,
            "phone": rating.customer.phone_number,
            "rating": rating.score,
            "score": rating.score,
            "review": rating.review,
            "message": rating.review,
            "date": rating.date.isoformat(),
            "created_at": rating.date.isoformat(),
        }

    result = _page_response(queryset, page_number, size, "feedbacks", serialize)
    return JsonResponse(result)


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


def _menu_queryset(request, customer=False):
    queryset = FoodItem.objects.select_related("category").prefetch_related("addons")
    if customer:
        queryset = queryset.filter(available=True).filter(
            Q(category__isnull=True) | Q(category__available=True)
        )
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
    pagination, error = _pagination(request)
    if error:
        return error
    direction, error = _item_sort(request)
    if error:
        return error
    sort_by = request.GET.get("sort_by", "id").lower()
    if sort_by not in MENU_SORT_FIELDS:
        return JsonResponse(
            {"error": f"'sort_by' must be one of: {', '.join(MENU_SORT_FIELDS)}."},
            status=400,
        )
    if not customer and request.GET.get("available") is not None:
        raw = request.GET["available"].lower()
        if raw not in ("true", "false"):
            return JsonResponse({"error": "'available' must be 'true' or 'false'."}, status=400)
        queryset = _menu_queryset(request).filter(available=raw == "true")
    else:
        queryset = _menu_queryset(request, customer=customer)
    prefix = "-" if direction == "desc" else ""
    queryset = queryset.order_by(
        f"{prefix}{MENU_SORT_FIELDS[sort_by]}",
        f"{prefix}pk",
    )
    page_number, size = pagination
    result = _page_response(queryset, page_number, size, "items", _serialize_food_item)
    result["sort"] = direction
    result["sort_by"] = sort_by
    return JsonResponse(result)


def _save_menu_item(request, item=None):
    try:
        data, files = parse_payload(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    addon_input = data.get("addons", data.get("addon_ids", []))
    if isinstance(addon_input, str):
        try:
            addon_input = json.loads(addon_input)
        except json.JSONDecodeError:
            addon_input = [part.strip() for part in addon_input.split(",") if part.strip()]
    if not isinstance(addon_input, list):
        return JsonResponse({"error": "'addons' must be a list."}, status=400)

    form_data = data.copy()
    if item is not None:
        for field in ("name", "description", "category", "price", "available"):
            if field not in form_data:
                value = getattr(item, f"{field}_id") if field == "category" else getattr(item, field)
                form_data[field] = value
    elif "available" not in form_data:
        form_data["available"] = True
    form = FoodItemForm(form_data, files, instance=item)
    if not form.is_valid():
        return JsonResponse(
            {"error": "Validation failed.", "errors": form_errors(form)}, status=400
        )
    prepared_addons = []
    for value in addon_input:
        if isinstance(value, dict):
            name = value.get("name")
            raw_price = value.get("price", "0")
            if not isinstance(name, str) or not name.strip():
                return JsonResponse({"error": "Each add-on needs a name."}, status=400)
            try:
                price = Decimal(str(raw_price))
            except (InvalidOperation, TypeError, ValueError):
                return JsonResponse({"error": "Add-on prices must be valid numbers."}, status=400)
            if not price.is_finite() or price < 0:
                return JsonResponse({"error": "Add-on prices must be finite and non-negative."}, status=400)
            addon = FoodAddon(name=name.strip(), price=price)
            try:
                addon.full_clean()
            except ValidationError as exc:
                return JsonResponse({"errors": exc.message_dict}, status=400)
            prepared_addons.append(("new", addon))
        else:
            try:
                addon = FoodAddon.objects.get(pk=int(value), available=True)
            except (TypeError, ValueError, FoodAddon.DoesNotExist):
                return JsonResponse({"error": "Invalid add-on ID."}, status=400)
            prepared_addons.append(("existing", addon))
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
            food_item = FoodItem.objects.prefetch_related("addons").get(pk=int(item_id), available=True)
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
        total += (food_item.price + sum((addon.price for addon in selected), Decimal("0.00"))) * quantity
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
    pagination, error = _pagination(request)
    if error:
        return error
    direction, error = _item_sort(request)
    if error:
        return error
    queryset = request.user.orders.select_related("customer").prefetch_related(
        "items__food_item", "items__selected_addons"
    )
    status_filter = request.GET.get("filter", "").lower()
    if status_filter:
        if status_filter == "pending":
            queryset = queryset.filter(status__in=PENDING_STATUSES)
        elif status_filter == "completed":
            queryset = queryset.filter(status=Order.Status.COMPLETED)
        elif status_filter.upper() in Order.Status.values:
            queryset = queryset.filter(status=status_filter.upper())
        else:
            return JsonResponse({"error": "Invalid status filter."}, status=400)
    page_number, size = pagination
    prefix = "-" if direction == "desc" else ""
    queryset = queryset.order_by(f"{prefix}created_at", f"{prefix}pk")
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
    result, error = _order_lines(data.get("items"))
    if error:
        return error
    lines, total = result
    with transaction.atomic():
        order = Order.objects.create(
            customer=request.user,
            total_amount=total,
            status=Order.Status.PENDING,
            estimated_time=timezone.now() + timedelta(minutes=30),
        )
        _write_order_items(order, lines)
    order = Order.objects.select_related("customer").prefetch_related(
        "items__food_item", "items__selected_addons"
    ).get(pk=order.pk)
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
@require_http_methods(["PATCH"])
def customer_update_order(request, user_id):
    error = _require_customer(request, user_id)
    if error:
        return error
    data, error = _json_body(request)
    if error:
        return error
    order_id = data.get("order_id")
    try:
        order = Order.objects.get(pk=int(order_id), customer=request.user)
    except (TypeError, ValueError, Order.DoesNotExist):
        return JsonResponse({"error": "Order not found."}, status=404)
    if order.status != Order.Status.PENDING:
        return JsonResponse({"error": "Only pending orders can be changed."}, status=409)
    result, error = _order_lines(data.get("items"))
    if error:
        return error
    lines, total = result
    with transaction.atomic():
        order.total_amount = total
        order.save(update_fields=["total_amount"])
        _write_order_items(order, lines)
    order = Order.objects.select_related("customer").prefetch_related(
        "items__food_item", "items__selected_addons"
    ).get(pk=order.pk)
    return JsonResponse({"order": _serialize_order(order)})


@_admin_api("GET")
def admin_users(request):
    pagination, error = _pagination(request)
    if error:
        return error
    direction, error = _item_sort(request)
    if error:
        return error
    queryset = User.objects.all()
    search = (request.GET.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
    page_number, size = pagination
    prefix = "-" if direction == "desc" else ""
    queryset = queryset.order_by(f"{prefix}pk")
    result = _page_response(queryset, page_number, size, "users", _serialize_user)
    result["total"] = result["pagination"]["total_items"]
    result["total_pages"] = result["pagination"]["total_pages"]
    result["page"] = page_number
    result["size"] = size
    return JsonResponse(result)


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
    fields = sorted(set(data) - {"display_name"})
    user.save(update_fields=fields)
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
    if not isinstance(old_password, str) or not isinstance(new_password, str) or not old_password or not new_password:
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


def _get_page(slug):
    defaults = PAGE_DEFAULTS[slug]
    page, _ = PageInfo.objects.get_or_create(
        slug=slug,
        defaults={"title": defaults["title"], "description": defaults["description"]},
    )
    return page


def _page_api(request, slug):
    if request.method == "GET":
        page = _get_page(slug)
        return JsonResponse({"title": page.title, "description": page.description})
    data, error = _json_body(request)
    if error:
        return error
    allowed = {"title", "description"}
    unknown = set(data) - allowed
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
    return JsonResponse({"title": page.title, "description": page.description})


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
        return JsonResponse({"error": "Page not found."}, status=404)
    if request.method not in ("GET", "PATCH"):
        response = JsonResponse({"error": "Method not allowed."}, status=405)
        response["Allow"] = "GET, PATCH"
        return response
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"error": "Admin access required."}, status=403)
    return _page_api(request, slug)


@_admin_api("GET", "PATCH")
def admin_landing_page(request):
    page = LandingPage.objects.order_by("pk").first()
    if page is None:
        page = LandingPage.objects.create(
            main_heading="Welcome to BJFC",
            subheading_description="Fresh, crispy favorites made for you.",
        )
    if request.method == "GET":
        return JsonResponse(
            {
                "id": page.pk,
                "main_heading": page.main_heading,
                "subheading_description": page.subheading_description,
                "hero_image": page.hero_image,
                "button_text": page.button_text,
                "button_link": page.button_link,
            }
        )
    data, error = _json_body(request)
    if error:
        return error
    allowed = {"main_heading", "subheading_description", "hero_image", "button_text", "button_link"}
    unknown = set(data) - allowed
    if unknown:
        return JsonResponse({"error": "Unknown landing-page fields.", "fields": sorted(unknown)}, status=400)
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
    return JsonResponse(
        {
            "id": page.pk,
            "main_heading": page.main_heading,
            "subheading_description": page.subheading_description,
            "hero_image": page.hero_image,
            "button_text": page.button_text,
            "button_link": page.button_link,
        }
    )


@_admin_api("GET", "PATCH")
def store_information(request):
    store = StoreInformation.objects.order_by("pk").first()
    if request.method == "GET":
        if store is None:
            return JsonResponse({"error": "Store information not found."}, status=404)
        return JsonResponse({"storename": store.storename, "contact": store.contact, "address": store.address})
    data, error = _json_body(request)
    if error:
        return error
    allowed = {"storename", "contact", "address"}
    if set(data) - allowed or not data:
        return JsonResponse({"error": "Provide one or more valid store fields."}, status=400)
    if store is None:
        store = StoreInformation(storename="", contact="", address="")
    for field, value in data.items():
        if not isinstance(value, str) or not value.strip():
            return JsonResponse({"error": f"'{field}' must be a non-empty string."}, status=400)
        setattr(store, field, value.strip())
    if not store.storename or not store.contact or not store.address:
        return JsonResponse({"error": "Store name, contact and address are required."}, status=400)
    store.save()
    return JsonResponse({"storename": store.storename, "contact": store.contact, "address": store.address})


@_admin_api("GET")
def admin_contact_messages(request):
    queryset = ContactMessage.objects.all()
    status_filter = request.GET.get("status")
    valid_statuses = [status for status, _ in ContactMessage.Status.choices]
    if status_filter:
        if status_filter not in valid_statuses:
            return JsonResponse({"error": "Invalid message status."}, status=400)
        queryset = queryset.filter(status=status_filter)
    pagination, error = _pagination(request)
    if error:
        return error
    direction, error = _item_sort(request)
    if error:
        return error
    page_number, size = pagination
    prefix = "-" if direction == "desc" else ""
    queryset = queryset.order_by(f"{prefix}created_at", f"{prefix}pk")
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
    message = form.save()
    return JsonResponse(
        {"message": "Thank you! Your message has been received.", "id": message.pk},
        status=201,
    )


@require_http_methods(["GET"])
def customer_favorites(request):
    error = _require_customer(request)
    if error:
        return error
    queryset = Favorite.objects.filter(customer=request.user).select_related(
        "food_item__category"
    ).prefetch_related("food_item__addons")
    pagination, error = _pagination(request)
    if error:
        return error
    direction, error = _item_sort(request)
    if error:
        return error
    page_number, size = pagination
    prefix = "-" if direction == "desc" else ""
    queryset = queryset.order_by(f"{prefix}created_at", f"{prefix}pk")
    return JsonResponse(
        _page_response(queryset, page_number, size, "items", lambda favorite: _serialize_food_item(favorite.food_item))
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
