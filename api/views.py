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
