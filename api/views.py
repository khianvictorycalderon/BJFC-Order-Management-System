import json

from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import LoginRecord

User = get_user_model()


@csrf_exempt
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
            }, status=405)


@csrf_exempt
@require_POST
def register_api(req):
    try:
        data = json.loads(req.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({
            "error": "Invalid JSON."
        }, status=400)

    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    phone_number = data.get("phone_number")

    if not username or not email or not password:
        return JsonResponse({
            "error": "Username, email, and password are required."
        }, status=400)

    if password != confirm_password:
        return JsonResponse({
            "error": "Passwords do not match."
        }, status=400)

    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse({
            "error": "Username is already taken."
        }, status=409)

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({
            "error": "Email is already registered."
        }, status=409)

    user = User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number or None,
    )

    try:
        user.set_password(password)
        user.full_clean()
        user.save()
    except Exception as error:
        # Log the actual error server-side in a production application.
        return JsonResponse({
            "error": "Unable to register user. Check the submitted information."
        }, status=400)

    return JsonResponse({
        "message": "Registration successful.",
        "user": {
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }
    }, status=201)


@csrf_exempt
@require_POST
def login_api(req):
    try:
        data = json.loads(req.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({
            "error": "Invalid JSON."
        }, status=400)

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return JsonResponse({
            "error": "Username and password are required."
        }, status=400)

    user = authenticate(
        request=req,
        username=username,
        password=password
    )

    if user is None:
        return JsonResponse({
            "error": "Invalid username or password."
        }, status=401)

    if not user.is_active:
        return JsonResponse({
            "error": "This account is inactive."
        }, status=403)

    LoginRecord.objects.create(user=user)

    return JsonResponse({
        "message": "Login successful.",
        "user": {
            "id": user.pk,
            "username": user.username,
            "email": user.email,
        }
    }, status=200)
