from django.shortcuts import render


def home(req):
    # Hero copy lives here so it can be swapped for real content later.
    context = {
        "hero": {
            "title": "wow and sarap",
            "lines": ["dasdasdasdasfasfas", "fafafasfasfasfasf", "fasfasfasfaf"],
            "cta_label": "Order Now",
            "cta_url": "#menu",
        }
    }
    return render(req, "public/home.html", context)


# For Frontend Designers: Replace with actual .html template file upon developing
def private_test(req):
    return render(req, "private/test.html")
