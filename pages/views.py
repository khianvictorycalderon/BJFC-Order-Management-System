from django.shortcuts import render

# For Frontend Designers: Replace with actual .html template file upon developing

def public_test(req):
    return render(req, "public/test.html")

def private_test(req):
    return render(req, "private/test.html")