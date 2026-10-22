import json
import logging
from datetime import datetime, time, timedelta
from functools import wraps

from django.contrib.auth import authenticate, login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from core.models import FoodItem, Order, PageInfo, Rating, User

from .forms import ContactMessageForm, FoodItemForm, form_errors, parse_payload

logger = logging.getLogger(__name__)



# Constants

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100

# ?sort_by=<key> -> database field
MENU_SORT_FIELDS = {
    "id": "id",
    "name": "name",
    "price": "price",
    "category": "category__name",
}

# Used when no PageInfo row exists yet (matches the admin settings form).
MENU_PAGE_DEFAULTS = {
    "title": "SIGNATURE FRIED CHICKEN",
    "description": "Golden, crunchy, and juicy chicken with our signature crispy coating.",
}



# Helpers

def admin_api(*methods):
    """Restrict a view to the given HTTP methods and to staff users, with JSON errors."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                response = JsonResponse({"error": "Method not allowed!"}, status=405)
                response["Allow"] = ", ".join(methods)
                return response
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Authentication required."}, status=401)
            if not request.user.is_staff:
                return JsonResponse({"error": "Admin access required."}, status=403)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def _positive_int(raw, default, name):
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a positive integer.")
    if value < 1:
        raise ValueError(f"'{name}' must be a positive integer.")
    return value


def _serialize_food_item(item):
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "price": float(item.price),
        "available": item.available,
        "image": item.image.url if item.image else None,
        "category": (
            {"id": item.category_id, "name": item.category.name}
            if item.category_id
            else None
        ),
    }


def _get_menu_page():
    """The menu page uses the first PageInfo row (None if it doesn't exist yet)."""
    return PageInfo.objects.order_by("id").first()


def _serialize_menu_page(page):
    if page is None:
        return dict(MENU_PAGE_DEFAULTS)
    return {"title": page.title, "description": page.description}



@csrf_exempt
def login_api(req):
    if req.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed!"},
            status=405
        )

    try:
        data = json.loads(req.body)

        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required."},
                status=400
            )

        user = authenticate(
            request=req,
            username=username,
            password=password
        )

        if user is None:
            return JsonResponse(
                {"error": "Invalid username or password."},
                status=401
            )

        if not user.is_active:
            return JsonResponse(
                {"error": "Account is inactive."},
                status=403
            )

       
        login(req, user)

        return JsonResponse({
            "message": "Login successful!",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON data."},
            status=400
        )


@csrf_exempt
def register(request):
    match request.method:
        case "GET":
            return JsonResponse({"message": "register api endpoint"}, status=200)
        case "POST":
            
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            if not isinstance(data, dict):
                return JsonResponse(
                    {"error": "Expected a JSON object"},
                    status=400,
                )

            fields = ("username", "email", "password", "confirm_password")
            if any(not isinstance(data.get(field), str) for field in fields):
                return JsonResponse(
                    {"error": "All fields are required and must be strings"},
                    status=400,
                )

            # value extraction
            username = data["username"].strip()
            email = data["email"].strip().lower()
            password = data["password"]
            confirm_password = data["confirm_password"]

            if not all((username, email, password, confirm_password)):
                return JsonResponse(
                    {"error": "All fields are required"},
                    status=400,
                )
         
            try:
                validate_email(email)
            except ValidationError:
                return JsonResponse({"error": "Invalid email"}, status=400)

           
            if password != confirm_password:
                return JsonResponse({
                    "error": "Passwords do not match!"
                }, status=400)

            if len(password) < 8:
                return JsonResponse({"error": "Password must be at least 8 characters"}, status=400)

            user = User(username=username, email=email)

            try:
                validate_password(password, user=user)
            except ValidationError as exc:
                return JsonResponse({"errors": exc.messages}, status=400)

           
            if User.objects.filter(email__iexact=email).exists():
                return JsonResponse(
                    {"error": "Email already registered"},
                    status=409,
                )

            if User.objects.filter(username=username).exists():
                return JsonResponse({
                    "error": "Username already taken"
                }, status=409)

          
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                    )
            except IntegrityError:
                return JsonResponse({
                    'error': 'Username or email already registered'
                }, status=409)
            except Exception:
                logger.exception('Unexpected error during registration')
                return JsonResponse(
                    {"error": "Unable to create account"},
                    status=500,
                )

            login(request, user)
            return JsonResponse(
                {"success": "Account created!"},
                status=201,
            )
        case _:
            return JsonResponse({
                "error": "Method not allowed!"
            }, status=405)


def test_api_response(req):
    match req.method:
        case "GET":
            return JsonResponse({
                "message": "Hello API World!",
                "method": "GET"
            }, status=200)
        case "POST":
            return JsonResponse({
                "message": "Hello API World!",
                "method": "POST"
            }, status=201)
        case _:
            return JsonResponse({
                "error": "Method not allowed!"
            }, status=400)

# /api/admin/menu/items 

@admin_api("GET", "POST")
def menu_items(request):
    if request.method == "POST":
        return _create_menu_item(request)
    return _list_menu_items(request)

def _list_menu_items(request):
    params = request.GET

    try:
        page_number = _positive_int(params.get("page"), 1, "page")
        size = _positive_int(params.get("size"), DEFAULT_PAGE_SIZE, "size")
        category_id = _positive_int(params.get("category"), None, "category")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    size = min(size, MAX_PAGE_SIZE)

    direction = params.get("sort", "asc").lower()
    if direction not in ("asc", "desc"):
        return JsonResponse({"error": "'sort' must be 'asc' or 'desc'."}, status=400)

    sort_by = params.get("sort_by", "id").lower()
    if sort_by not in MENU_SORT_FIELDS:
        return JsonResponse(
            {"error": f"'sort_by' must be one of: {', '.join(MENU_SORT_FIELDS)}."},
            status=400,
        )

    available = params.get("available")
    if available is not None and available.lower() not in ("true", "false"):
        return JsonResponse({"error": "'available' must be 'true' or 'false'."}, status=400)

    queryset = FoodItem.objects.select_related("category")

    search = (params.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    if category_id is not None:
        queryset = queryset.filter(category_id=category_id)
    if available is not None:
        queryset = queryset.filter(available=available.lower() == "true")

    prefix = "-" if direction == "desc" else ""
   
    queryset = queryset.order_by(f"{prefix}{MENU_SORT_FIELDS[sort_by]}", f"{prefix}id")

    paginator = Paginator(queryset, size)
    try:
        page = paginator.page(page_number)
        items = [_serialize_food_item(item) for item in page.object_list]
        has_next, has_previous = page.has_next(), page.has_previous()
    except EmptyPage:  # page past the end -> empty list, not an error
        items, has_next, has_previous = [], False, paginator.num_pages > 0

    return JsonResponse(
        {
            "items": items,
            "pagination": {
                "page": page_number,
                "size": size,
                "total_items": paginator.count,
                "total_pages": paginator.num_pages,
                "has_next": has_next,
                "has_previous": has_previous,
            },
            "sort": direction,
            "sort_by": sort_by,
        },
        status=200,
    )


def _create_menu_item(request):
    try:
        data, files = parse_payload(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    # An unchecked/missing checkbox means False in a ModelForm; our API default is True.
    if "available" not in data:
        data["available"] = True

    form = FoodItemForm(data, files)
    if not form.is_valid():
        return JsonResponse(
            {"error": "Validation failed.", "errors": form_errors(form)}, status=400
        )

    item = form.save()
    return JsonResponse(_serialize_food_item(item), status=201)


# GET /api/admin/orders/info

@admin_api("GET")
def orders_info(request):
    start_of_today = timezone.make_aware(
        datetime.combine(timezone.localdate(), time.min)
    )
    start_of_tomorrow = start_of_today + timedelta(days=1)

    pending = Order.objects.filter(status=Order.Status.PENDING).count()

    completed_today = Order.objects.filter(
        status=Order.Status.COMPLETED,
        created_at__gte=start_of_today,
        created_at__lt=start_of_tomorrow,
    ).count()

    return JsonResponse(
        {"pending_orders": pending, "completed_today": completed_today}, status=200
    )


# GET /api/admin/feedbacks/info

@admin_api("GET")
def feedbacks_info(request):
    summary = Rating.objects.aggregate(total=Count("id"), average=Avg("score"))
    per_score = dict(
        Rating.objects.values_list("score").annotate(n=Count("id")).order_by("score")
    )

    return JsonResponse(
        {
            "total_feedback": summary["total"],
            "average_rating": round(summary["average"], 2) if summary["average"] else 0,
            "rating_counts": {str(star): per_score.get(star, 0) for star in range(1, 6)},
        },
        status=200,
    )


# GET / PATCH /api/admin/menu-page

@admin_api("GET", "PATCH")
def menu_page(request):
    if request.method == "GET":
        return JsonResponse(_serialize_menu_page(_get_menu_page()), status=200)

    # PATCH
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"error": "Expected a JSON object."}, status=400)

    editable = set(MENU_PAGE_DEFAULTS)
    unknown = set(data) - editable
    if unknown:
        return JsonResponse(
            {"error": f"Unknown field(s): {', '.join(sorted(unknown))}."}, status=400
        )
    if not data:
        return JsonResponse(
            {"error": f"Provide at least one of: {', '.join(sorted(editable))}."},
            status=400,
        )

    cleaned = {}
    for field, value in data.items():
        if not isinstance(value, str) or not value.strip():
            return JsonResponse(
                {"error": f"'{field}' must be a non-empty string."}, status=400
            )
        cleaned[field] = value.strip()

    page = _get_menu_page()
    if page is None:
        page = PageInfo(**MENU_PAGE_DEFAULTS)
    for field, value in cleaned.items():
        setattr(page, field, value)
    page.save()

    return JsonResponse(_serialize_menu_page(page), status=200)



# POST /api/contact/messages

@csrf_exempt
def contact_messages(request):
    if request.method != "POST":
        response = JsonResponse({"error": "Method not allowed!"}, status=405)
        response["Allow"] = "POST"
        return response

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

    form.save()
    return JsonResponse({"message": "Thank you! Your message has been received."}, status=201)