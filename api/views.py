import json
import logging

from django.http import JsonResponse
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.contrib.auth import login
from core.models import User

from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate

from core.models import User, LandingPage


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
logger=logging.getLogger(__name__)
@csrf_exempt
# Create your views here.

def register(request):
    match request.method:
        case "GET":
            return JsonResponse({"message": "register api endpoint"}, status=200)
        case "POST":
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

            fields = ("username", "email", "password", "confirm_password")
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

            if not all((username, email, password, confirm_password)):
                return JsonResponse(
                    {"error": "All fields are required"},
                    status=400,
                )
            #email validation
            try:
                validate_email(email)
            except ValidationError:
                return JsonResponse({"error": "Invalid email"}, status=400)

            #password handling
            if password !=confirm_password:
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

            #duplicate checks
            if User.objects.filter(email__iexact=email).exists():
                return JsonResponse(
                    {"error": "Email already registered"},
                    status=409,
                )
            
            if User.objects.filter(username=username).exists():
                return JsonResponse({
                "error": "Username already taken"
            }, status=409)

            #user creation
            try:
                with transaction.atomic():
                    user=User.objects.create_user(
                        username=username,
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

def admin_landing_page(request):
    # Allow only GET and PATCH requests
    if request.method not in ["GET", "PATCH"]:
        response = JsonResponse(
            {"error": "Method not allowed."},
            status=405,
        )
        response["Allow"] = "GET, PATCH"
        return response

    # Protect this administrative endpoint
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse(
            {"error": "Admin access required."},
            status=403,
        )

    # Find the landing-page record
    landing_page = LandingPage.objects.first()

    if landing_page is None:
        return JsonResponse(
            {"message": "Landing page information has not been configured."},
            status=404,
        )

    # GET: Retrieve landing-page information
    if request.method == "GET":
        image = landing_page.hero_image

        try:
            image = image.url if image else ""
        except ValueError:
            image = ""

        return JsonResponse({
            "id": landing_page.id,
            "main_heading": landing_page.main_heading,
            "subheading_description": landing_page.subheading_description,
            "hero_image": image,
            "button_text": landing_page.button_text,
            "button_link": landing_page.button_link,
        }, status=200)

    # PATCH: Read the incoming JSON
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON data."},
            status=400,
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Expected a JSON object."},
            status=400,
        )

    # Only allow these fields to be updated
    allowed_fields = {
        "main_heading",
        "subheading_description",
        "hero_image",
        "button_text",
        "button_link",
    }

    unknown_fields = set(data.keys()) - allowed_fields

    if unknown_fields:
        return JsonResponse(
            {
                "error": "Invalid fields provided.",
                "fields": sorted(unknown_fields),
            },
            status=400,
        )

    # Validate and update only the fields provided
    for field, value in data.items():
        if not isinstance(value, str):
            return JsonResponse(
                {"error": f"{field} must be a string."},
                status=400,
            )

        setattr(landing_page, field, value)

    landing_page.save()

    return JsonResponse(
        {
            "message": "Landing page updated successfully.",
            "data": {
                "id": landing_page.id,
                "main_heading": landing_page.main_heading,
                "subheading_description": landing_page.subheading_description,
                "button_text": landing_page.button_text,
                "button_link": landing_page.button_link,
            },
        },
        status=200,
    )