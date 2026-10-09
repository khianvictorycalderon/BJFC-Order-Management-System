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


# Menu page
def menu(req):
    meals = [
        {"name": "Fried Chicken", "price": 75, "image": "img\\chicken1.png"},
        {"name": "Fruit Soda", "price": 75, "image": "img\\chicken2.png"},
        {"name": "Bottled Water", "price": 75, "image": "img\\chicken3.png"},
        {"name": "Milk Tea", "price": 75, "image": "img\\chicken4.png "},
    ]

    drinks = [
        {"name": "Iced Coffee", "price": 50, "image": "img\\ice coffee.png"},
        {"name": "Fruit Soda", "price": 60, "image": "img\\fruitsoda.png"},
        {"name": "Milk Tea", "price": 70, "image": "img\\milktea.png"},
        {"name": "Matcha Latte", "price": 80, "image": "img\\matcha.png"},
        {"name": "Frappe", "price": 90, "image": "img\\frappe.png"},
        {"name": "Bottled Water", "price": 20, "image": "img\\water.png"},
    ]

    addons = [
        {"name": "Extra Buffalo Sauce", "price": 20, "image": "img\\bufalo.png"},
        {"name": "Extra Soy Garlic Sauce", "price": 25, "image": "img\\soy garlic.png"},
        {"name": "Extra Sour Cream Sauce", "price": 25, "image": "img\\sourcream.png"},
        {"name": "Ketchup", "price": 5, "image": "img\\ketchup.png"},
        {"name": "Extra Rice", "price": 20, "image": "img\\rice.png"},
        {"name": "Soup", "price": 20, "image": "img\\soup.png"},
    ]

    context = {
        "meals": meals,
        "drinks": drinks,
        "addons": addons,
    }

    return render(req, "public/menu.html", context)