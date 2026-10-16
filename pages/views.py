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
        {"name": "Fried Chicken", "price": 75, "image": "images/menu/chicken1.png"},
        {"name": "Fruit Soda", "price": 75, "image": "images/menu/chicken2.png"},
        {"name": "Bottled Water", "price": 75, "image": "images/menu/chicken3.png"},
        {"name": "Milk Tea", "price": 75, "image": "images/menu/chicken4.png"},
    ]

    drinks = [
        {"name": "Iced Coffee", "price": 50, "image": "images/menu/ice coffee.png"},
        {"name": "Fruit Soda", "price": 60, "image": "images/menu/fruitsoda.png"},
        {"name": "Milk Tea", "price": 70, "image": "images/menu/milktea.png"},
        {"name": "Matcha Latte", "price": 80, "image": "images/menu/matcha.png"},
        {"name": "Frappe", "price": 90, "image": "images/menu/frappe.png"},
        {"name": "Bottled Water", "price": 20, "image": "images/menu/water.png"},
    ]

    addons = [
        {"name": "Extra Buffalo Sauce", "price": 20, "image": "images/menu/bufalo.png"},
        {"name": "Extra Soy Garlic Sauce", "price": 25, "image": "images/menu/soy garlic.png"},
        {"name": "Extra Sour Cream Sauce", "price": 25, "image": "images/menu/sourcream.png"},
        {"name": "Ketchup", "price": 5, "image": "images/menu/ketchup.png"},
        {"name": "Extra Rice", "price": 20, "image": "images/menu/rice.png"},
        {"name": "Soup", "price": 20, "image": "images/menu/soup.png"},
    ]

    context = {
        "meals": meals,
        "drinks": drinks,
        "addons": addons,
    }

    return render(req, "public/menu.html", context)
  
def about(req):
    return render(req, "public/about.html")

def contact(req):
    return render(req, "public/contact.html")

def login_page(req):
    return render(req, "public/login.html")


def signup_page(req):
    return render(req, "public/signup.html")