import json
import logging

from django.http import JsonResponse
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth import authenticate, update_session_auth_hash, logout
from core.models import User, Order, PageInfo, StoreInformation
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
logger=logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def login_api(req):
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
@require_http_methods(["POST"])
def register(request):
    #parsing and validation
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Expected a JSON object"},
            status=400,
        )

    fields = ("username", "last_name", "first_name", "email", "password", "confirm_password")
    if any(not isinstance(data.get(field), str) for field in fields):
        return JsonResponse(
            {"error": "All fields are required and must be strings"},
            status=400,
        )
    
    #value extraction
    username = data["username"].strip()
    email = data["email"].strip().lower()
    password = data["password"]
    confirm_password = data["confirm_password"]
    first_name = data["first_name"].strip()
    last_name = data["last_name"].strip()

    if not all((username, last_name, first_name, email, password, confirm_password)):
        return JsonResponse(
            {"error": "All fields are required"},
            status=400,
        )
    #email validation
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"error": "Invalid email"}, status=400)
    user = User(username=username, 
        email=email, 
        first_name=first_name,
        last_name=last_name
    )

    #password handling
    if password !=confirm_password:
        return JsonResponse({
        "error": "Passwords do not match!"
    }, status=400
    )

    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)

    #duplicate checks
    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse(
            {"error": "Email already registered"},
            status=409,
        )
    
    if User.objects.filter(username=username).exists():
        return JsonResponse({
        "error": "Username already taken"
    }, status=409
    )

    #user creation
    try:
        with transaction.atomic():
            user=User.objects.create_user(
                username=username,
                last_name=last_name,
                first_name=first_name,
                email=email,
                password=password,
            )
    except IntegrityError:
        return JsonResponse({
            'error': 'Username or email already registered'
        },status=409)
    except Exception:
        logger.exception('Unexpected error during registration')
        return JsonResponse(
        {"error": "Unable to create account"},
        status=500,
        )
    
    return JsonResponse(
        {"message": "Account created!"},
        status=201,
    )

# ADMIN
@require_http_methods(["GET"])
def admin_orders(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse(
            {"error": "Admin access required."},
            status=403,
        )
    
    status = request.GET.get('filter')
    if status is None:
        result = Order.objects.all()
    elif status in Order.Status.values:
        result = Order.objects.filter(status=status)
    else:
        return JsonResponse(
            {"error": "Invalid status filter"},
            status=400,
        )
    
    size = request.GET.get('size', 10)
    page = request.GET.get('page', 1)
    sort = request.GET.get('sort', 'desc')
    
    try:
        size = int(size)
        page = int(page)
    except (ValueError, TypeError):
        return JsonResponse(
            {"error": "size and page must be integers"},
            status=400,
        )
    if size <= 0 or size > 10:
        return JsonResponse(
            {"error": "size must be between 1 and 10"},
            status=400,
        )
    if page <= 0:
        return JsonResponse(
            {"error": "page must be positive"},
            status=400,
        )
    
    if sort not in ('asc', 'desc'):
        return JsonResponse(
            {"error": "sort must be 'asc' or 'desc'"},
            status=400,
        )
    
    sort_fields = (
        ("-created_at", "-pk")
        if sort == "desc"
        else ("created_at", "pk")
    )

    result = (
        result
        .select_related("customer")
        .prefetch_related("items__food_item")
        .order_by(*sort_fields)
    )

    paginator = Paginator(result, size)
    try:
        page_obj = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        return JsonResponse(
            {"error": "Invalid page"},
            status=400,
        )
    orders = [
        {
            "id": order.id,
            "customer_username": order.customer.username,
            "status": order.status,
            "estimated_time": order.estimated_time,
            "created_at": order.created_at,
            "total_amount": order.total_amount,
            "items": [
                {
                    "food_item_name": item.food_item.name,
                    "quantity": item.quantity,
                    "price": item.price,
                }
                for item in order.items.all()
            ],
        }
        for order in page_obj.object_list
    ]

    return JsonResponse({
        "orders": orders,
        "page": page,
        "size": size,
        "total_pages": paginator.num_pages,
        "total_items": paginator.count,
    }, status=200)

@require_http_methods(["PATCH"])
def admin_order_status(request, pk):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse(
            {"error": "Admin access required."},
            status=403,
        )
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Expected a JSON object"},
            status=400,
        )
    
    status=data.get('status')
    if not isinstance(status, str) or status not in Order.Status.values:
        return JsonResponse(
    {"error": "Invalid order status"},
    status=400,
    )

    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return JsonResponse(
            {"error": "Order not found"},
            status=404,
        )
    order.status = status
    order.save(update_fields=['status'])

    return JsonResponse({
        "message": "Order status updated successfully.",
        "order_id": order.pk,
        "status": order.status,
        "status_display": order.get_status_display(),
    }, status=200
    )

@require_http_methods(["PATCH"])
def admin_password(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse(
            {"error": "Admin access required."},
            status=403,
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Expected a JSON object"},
            status=400,
        )

    user = request.user

    old_password = data.get("old_password")
    new_password = data.get("new_password")

    if not isinstance(old_password, str) or not isinstance(new_password, str):
        return JsonResponse(
            {"error": "Old and new passwords are required."},
            status=400,
        )

    if not old_password or not new_password:
        return JsonResponse(
            {"error": "Passwords cannot be empty."},
            status=400,
        )

    if not user.check_password(old_password):
        return JsonResponse(
            {"error": "Current password is incorrect."},
            status=400,
        )

    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        return JsonResponse(
            {"errors": exc.messages},
            status=400,
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    update_session_auth_hash(request, user)

    return JsonResponse({
        "success": True,
        "message": "Password changed successfully.",
    }, status=200)

def page_content(request, slug):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse(
            {"error": "Admin access required."},
            status=403,
        )

    match request.method:
        case 'GET':
            try:
                page = PageInfo.objects.get(slug=slug)
            except PageInfo.DoesNotExist:
                return JsonResponse(
                    {"error": "Page not found"},
                    status=404,
                )

            return JsonResponse({
                "title": page.title,
                "description": page.description,
            }, status=200)
        case 'PATCH':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({"error": "Invalid JSON"}, status=400)
            
            if not isinstance(data, dict):
                return JsonResponse(
                    {"error": "Expected a JSON object"},
                    status=400,
                )
            title=data.get("title")
            desc=data.get("description")
            try:
                page = PageInfo.objects.get(slug=slug)
            except PageInfo.DoesNotExist:
                return JsonResponse(
                    {"error": "Page not found"},
                    status=404,
                )
            page.title=title
            page.description=desc
            page.save(update_fields=['title','description'])
            
            return JsonResponse({"message": "Page updated successfully."}, status=200)
        case _:
            return JsonResponse({
                "error": "Method not allowed!"
            }, status=405)

def store_information(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse(
            {"error": "Admin access required."},
            status=403,
        )

    match request.method:
        case 'GET':
            try:
                storeinfo = StoreInformation.objects.get()
            except StoreInformation.DoesNotExist:
                return JsonResponse(
                    {"error": "Store not found"},
                    status=404,
                )

            return JsonResponse({
                "storename": storeinfo.storename,
                "contact": storeinfo.contact,
                "address": storeinfo.address
            }, status=200)
        
        case 'PATCH':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            if not isinstance(data, dict):
                return JsonResponse(
                    {"error": "Expected a JSON object"},
                    status=400,
                )
            storename=data.get("storename")
            contact=data.get("contact")
            address=data.get("address")
            try:
                storeinfo = StoreInformation.objects.get()
            except StoreInformation.DoesNotExist:
                return JsonResponse(
                    {"error": "Store not found"},
                    status=404,
                )
            storeinfo.storename=storename
            storeinfo.contact=contact
            storeinfo.address=address
            storeinfo.save(update_fields=['storename','contact','address'])

            return JsonResponse({"message": "Store information updated successfully."}, status=200)
        case _:
            return JsonResponse({
                "error": "Method not allowed!"
            }, status=405)

# CUSTOMER
def customer_profile(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "You must log in first"},
            status=401,
        )

    match request.method:
        case "GET":
            user=request.user
            return JsonResponse({
                'id': user.id,
                'username': user.username,
                "last_name": user.last_name,
                "first_name": user.first_name,
                'email': user.email,
                "message": "User successfully retrieved.",
            }, status=200)
        case "PATCH":
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({"error": "Invalid JSON"}, status=400)
            
            if not isinstance(data, dict):
                return JsonResponse(
                    {"error": "Expected a JSON object"},
                    status=400,
                )
            fields = ("username", "email", "first_name", "last_name")
            if any(not isinstance(data.get(field), str) for field in fields):
                return JsonResponse(
                    {"error": "All fields are required and must be strings"},
                    status=400,
                )

            username = data["username"].strip()
            email = data["email"].strip().lower()
            first_name = data["first_name"].strip()
            last_name = data["last_name"].strip()

            if not all((username, email, first_name, last_name)):
                return JsonResponse(
                    {"error": "All fields are required and cannot be empty"},
                    status=400,
                )
            
            user=request.user
            user.email=email
            user.first_name=first_name
            user.last_name=last_name
            user.username=username

            if User.objects.filter(
                username=username
            ).exclude(pk=user.pk).exists():
                return JsonResponse(
                    {"error": "Username already taken"},
                    status=409,
                )
            if User.objects.filter(
                email__iexact=email
            ).exclude(pk=user.pk).exists():
                return JsonResponse(
                    {"error": "Email already registered"},
                    status=409,
                )
            
            try:
                user.full_clean()
            except ValidationError as e:
                return JsonResponse({"error": e.messages}, status=400)
            
            user.save(update_fields=[
                "username",
                "email",
                "first_name",
                "last_name",
            ])
            return JsonResponse({"message": "User updated"}, status=200)

        case "DELETE":
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({"error": "Invalid JSON"}, status=400)
            
            if not isinstance(data, dict):
                return JsonResponse(
                    {"error": "Expected a JSON object"},
                    status=400,
                )
            
            password = data.get('password')
            confirm = data.get('confirm_deletion')
            
            if not password or not isinstance(password, str):
                return JsonResponse({'error': 'password required'}, status=400)
            
            if confirm != 'DELETE_MY_ACCOUNT':
                return JsonResponse(
                    {'error': 'Confirmation must be "DELETE_MY_ACCOUNT"'},
                    status=400
                )
            
            if not request.user.check_password(password):
                return JsonResponse({'error': 'Invalid password'}, status=401)
            
            user_id = request.user.id
            username = request.user.username
            logger.warning(f'User {username} (ID: {user_id}) deleted their own account')
            
            request.user.delete()
            
            logout(request)
            
            return JsonResponse({'success': 'Account deleted successfully'}, status=200)
        case _:
            return JsonResponse({
                "error": "Method not allowed!"
            }, status=405
            )