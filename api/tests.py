import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.models import (
    ContactMessage,
    Favorite,
    FoodAddon,
    FoodCategory,
    FoodItem,
    Order,
    OrderItem,
    Rating,
    User,
)


class BackendApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="api-admin",
            email="admin@example.com",
            password="Test-password-123",
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            username="api-customer",
            email="customer@example.com",
            password="Test-password-123",
            first_name="Jane",
            last_name="Customer",
        )
        category = FoodCategory.objects.create(name="Chicken")
        self.item = FoodItem.objects.create(
            category=category,
            name="Crispy Chicken",
            description="Freshly cooked",
            price=Decimal("10.00"),
        )
        self.addon = FoodAddon.objects.create(name="Extra sauce", price=Decimal("2.50"))
        self.item.addons.add(self.addon)

    def test_admin_menu_crud_and_customer_visibility(self):
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/menu/items/?size=5&page=1&sort=desc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["name"], "Crispy Chicken")
        self.assertEqual(response.json()["items"][0]["addons"][0]["name"], "Extra sauce")

        response = self.client.post(
            "/api/admin/menu/items",
            data=json.dumps(
                {
                    "name": "Spicy Chicken",
                    "description": "A little kick",
                    "category": self.item.category_id,
                    "price": "15.00",
                    "available": True,
                    "addons": [{"name": "Chili dip", "price": "1.25"}],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        created_item_id = response.json()["id"]
        self.assertEqual(response.json()["addons"][0]["name"], "Chili dip")

        response = self.client.patch(
            f"/api/admin/menu/items/{self.item.pk}",
            data=json.dumps({"available": False, "price": "12.00"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertFalse(self.item.available)
        self.assertEqual(self.item.price, Decimal("12.00"))

        response = self.client.delete(f"/api/admin/menu/items/{created_item_id}")
        self.assertEqual(response.status_code, 200)
        self.client.force_login(self.customer)
        response = self.client.get("/api/customer/menu/items")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_order_prices_calculated_from_menu_and_addons(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            "/api/customer/orders",
            data=json.dumps(
                {
                    "items": [
                        {
                            "menu_item_id": self.item.pk,
                            "quantity": 2,
                            "addon_ids": [self.addon.pk],
                        }
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.total_amount, Decimal("25.00"))
        self.assertEqual(OrderItem.objects.get(order=order).quantity, 2)
        self.assertEqual(response.json()["status"], Order.Status.PENDING)

        response = self.client.get("/api/customer/my-orders")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["orders"][0]["total_amount"], "25.00")

    def test_favorites_are_private_and_idempotent(self):
        self.client.force_login(self.customer)
        url = f"/api/customer/favorites/{self.item.pk}"
        self.assertEqual(self.client.put(url).status_code, 201)
        self.assertEqual(self.client.put(url).status_code, 200)
        self.assertEqual(Favorite.objects.count(), 1)
        response = self.client.get("/api/customer/favorites")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], self.item.pk)
        self.assertEqual(self.client.delete(url).status_code, 200)

    def test_contact_submission_and_admin_status(self):
        response = self.client.post(
            "/api/contact/messages",
            data=json.dumps(
                {
                    "name": "Visitor",
                    "email": "visitor@example.com",
                    "phone": "+639123456789",
                    "message": "Please contact me.",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        message = ContactMessage.objects.get()
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/contact/messages?status=unread")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"][0]["email"], "visitor@example.com")
        response = self.client.patch(
            f"/api/admin/contact/messages/{message.pk}",
            data=json.dumps({"status": "resolved"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        message.refresh_from_db()
        self.assertEqual(message.status, ContactMessage.Status.RESOLVED)

    def test_feedback_summary_and_admin_profile(self):
        Rating.objects.create(customer=self.customer, score=5, review="Great!")
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/feedbacks/info")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_feedback"], 1)
        self.assertEqual(response.json()["rating_counts"]["5"], 1)
        response = self.client.get("/api/admin/feedbacks?rating=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedbacks"][0]["review"], "Great!")
        response = self.client.patch(
            "/api/admin/profile",
            data=json.dumps({"display_name": "BJFC Owner"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["display_name"], "BJFC Owner")
