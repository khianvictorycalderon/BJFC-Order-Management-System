from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Create your views here.
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
            }, status=400)