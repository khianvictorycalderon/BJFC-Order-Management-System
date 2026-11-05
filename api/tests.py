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

    def test_admin_only_login_rejects_customers(self):
        self.customer.set_password("customer-test-password")
        self.customer.save(update_fields=["password"])
        response = self.client.post(
            "/api/login",
            data=json.dumps({
                "username": self.customer.username,
                "password": "customer-test-password",
                "admin_only": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_admin_dashboard_uses_database_data(self):
        order = Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("25.00"),
            status=Order.Status.COMPLETED,
        )
        OrderItem.objects.create(
            order=order,
            food_item=self.item,
            quantity=2,
            price=self.item.price,
        )
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_sales"], "25.00")
        self.assertEqual(response.json()["total_orders"], 1)
        self.assertEqual(response.json()["total_customers"], 1)
        self.assertEqual(response.json()["top_items"][0]["food_item__name"], self.item.name)
        self.assertEqual(response.json()["recent_orders"][0]["id"], order.pk)

    def test_admin_orders_status_filter_and_pagination(self):
        for status in (Order.Status.PENDING, Order.Status.PREPARING, Order.Status.COMPLETED):
            Order.objects.create(
                customer=self.customer,
                total_amount=Decimal("10.00"),
                status=status,
            )
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/orders/?filter=pending&size=1&page=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pagination"]["total_items"], 2)
        self.assertTrue(response.json()["pagination"]["has_next"])
        self.assertNotEqual(response.json()["orders"][0]["status"], Order.Status.COMPLETED)

    def test_admin_can_mark_completed_order_pending(self):
        order = Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("10.00"),
            status=Order.Status.COMPLETED,
        )
        self.client.force_login(self.admin)
        response = self.client.patch(
            f"/api/admin/orders/{order.pk}/",
            data=json.dumps({"status": Order.Status.PENDING}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_admin_menu_crud_and_customer_visibility(self):
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/menu/items/?size=5&page=1&sort=desc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["name"], "Crispy Chicken")
        self.assertEqual(response.json()["items"][0]["addons"][0]["name"], "Extra sauce")
        self.assertNotIn("categories", response.json())
        self.assertNotIn("addons", response.json())

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
        hidden_category = FoodCategory.objects.create(name="Legacy category", available=False)
        drink = FoodItem.objects.create(
            category=hidden_category,
            name="Orange drink",
            price=Decimal("3.00"),
        )
        response = self.client.get("/api/customer/menu/items")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["items"]], [drink.pk])

    def test_order_prices_calculated_from_menu_and_addons(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            "/api/customer/orders",
            data=json.dumps(
                {
                    "order_type": "DELIVERY",
                    "contact_phone": "0917 123 4567",
                    "address": "12 Rizal St, Brgy. Ilayang Dupay, Lucena City",
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
        self.assertEqual(order.delivery_address, "12 Rizal St, Brgy. Ilayang Dupay, Lucena City")
        self.assertEqual(order.order_type, Order.OrderType.DELIVERY)
        self.assertEqual(order.contact_phone, "0917 123 4567")
        self.assertFalse(order.is_paid)
        self.assertEqual(response.json()["order"]["address"], order.delivery_address)
        self.assertEqual(order.total_amount, Decimal("25.00"))
        self.assertEqual(OrderItem.objects.get(order=order).quantity, 2)
        self.assertEqual(response.json()["status"], Order.Status.PENDING)

        response = self.client.get("/api/customer/my-orders")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["orders"][0]["total_amount"], "25.00")

    def test_order_requires_valid_address(self):
        self.client.force_login(self.customer)
        items = [{"menu_item_id": self.item.pk, "quantity": 1}]
        for bad in (None, "", "   ", 123, "x" * 256):
            payload = {"items": items, "order_type": "DELIVERY", "contact_phone": "09171234567"}
            if bad is not None:
                payload["address"] = bad
            response = self.client.post(
                "/api/customer/orders",
                data=json.dumps(payload),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400, bad)
        self.assertEqual(Order.objects.count(), 0)

    def test_admin_sees_order_address(self):
        Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("10.00"),
            delivery_address="5 Quezon Ave",
        )
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["orders"][0]["address"], "5 Quezon Ave")

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

    def test_contact_sender_is_customer_or_guest(self):
        guest_response = self.client.post(
            "/api/contact/messages",
            data=json.dumps({
                "name": "Visitor",
                "email": "visitor@example.com",
                "phone": "",
                "message": "Guest message.",
            }),
            content_type="application/json",
        )
        self.assertEqual(guest_response.status_code, 201)
        self.client.force_login(self.customer)
        customer_response = self.client.post(
            "/api/contact/messages",
            data=json.dumps({
                "name": "Jane",
                "email": "customer@example.com",
                "phone": "",
                "message": "Customer message.",
            }),
            content_type="application/json",
        )
        self.assertEqual(customer_response.status_code, 201)
        self.client.force_login(self.admin)
        response = self.client.get("/api/admin/contact/messages?sort=asc")
        self.assertEqual(response.status_code, 200)
        messages = response.json()["messages"]
        self.assertEqual(messages[0]["sender_name"], "Guest")
        self.assertEqual(messages[1]["sender_name"], "Jane Customer")

    def test_customer_cannot_update_an_order(self):
        order = Order.objects.create(
            customer=self.customer,
            total_amount=Decimal("10.00"),
            status=Order.Status.PENDING,
        )
        self.client.force_login(self.customer)
        response = self.client.patch(
            f"/api/customer/{self.customer.pk}/my-orders",
            data=json.dumps({"order_id": order.pk, "items": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

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


class OrderWorkflowTests(TestCase):
    """Order types, bulk ordering, cancel, address edits and payment/status handling."""

    ADDRESS = "12 Rizal St, Lucena City"

    def setUp(self):
        self.admin = User.objects.create_user(
            username="wf-admin", password="Test-password-123", is_staff=True
        )
        self.customer = User.objects.create_user(
            username="wf-customer", password="Test-password-123",
            first_name="Jane", last_name="Customer",
        )
        self.other = User.objects.create_user(username="wf-other", password="Test-password-123")
        category = FoodCategory.objects.create(name="Chicken")
        self.item = FoodItem.objects.create(
            category=category, name="Crispy Chicken", description="x", price=Decimal("10.00")
        )
        self.item2 = FoodItem.objects.create(
            category=category, name="Spicy Wings", description="x", price=Decimal("7.50")
        )

    # ----- helpers -----
    def place(self, **overrides):
        payload = {
            "order_type": "DELIVERY",
            "contact_phone": "09171234567",
            "address": self.ADDRESS,
            "items": [{"menu_item_id": self.item.pk, "quantity": 1}],
        }
        payload.update(overrides)
        return self.client.post(
            "/api/customer/orders", data=json.dumps(payload), content_type="application/json"
        )

    def make_order(self, **fields):
        defaults = dict(
            customer=self.customer,
            total_amount=Decimal("10.00"),
            order_type=Order.OrderType.DELIVERY,
            contact_phone="09171234567",
            delivery_address=self.ADDRESS,
        )
        defaults.update(fields)
        return Order.objects.create(**defaults)

    def send(self, method, url, payload=None):
        return getattr(self.client, method)(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )

    # ----- order types -----
    def test_dine_in_needs_no_phone_or_address(self):
        self.client.force_login(self.customer)
        response = self.place(order_type="DINE_IN", contact_phone="", address="")
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.order_type, Order.OrderType.DINE_IN)
        self.assertEqual((order.contact_phone, order.delivery_address), ("", ""))

    def test_dine_in_ignores_any_phone_or_address_sent(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.place(order_type="dine-in").status_code, 201)
        order = Order.objects.get()
        self.assertEqual((order.contact_phone, order.delivery_address), ("", ""))

    def test_pickup_requires_phone_but_not_address(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.place(order_type="PICKUP", contact_phone="").status_code, 400)
        self.assertEqual(self.place(order_type="PICKUP", contact_phone="abc").status_code, 400)
        response = self.place(order_type="PICKUP", address="")
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.contact_phone, "09171234567")
        self.assertEqual(order.delivery_address, "")

    def test_delivery_requires_phone_and_address(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.place(contact_phone="").status_code, 400)
        self.assertEqual(self.place(address="  ").status_code, 400)
        self.assertEqual(self.place(order_type=None).status_code, 400)
        self.assertEqual(self.place(order_type="TELEPORT").status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_bulk_order_with_many_items(self):
        self.client.force_login(self.customer)
        response = self.place(
            items=[
                {"menu_item_id": self.item.pk, "quantity": 12},
                {"menu_item_id": self.item2.pk, "quantity": 4},
            ]
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.total_amount, Decimal("150.00"))  # 12*10 + 4*7.50
        self.assertEqual(order.items.count(), 2)

    # ----- customer cancel -----
    def test_customer_can_cancel_until_out_for_delivery(self):
        self.client.force_login(self.customer)
        for status in (Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING):
            order = self.make_order(status=status)
            response = self.send("post", f"/api/customer/orders/{order.pk}/cancel")
            self.assertEqual(response.status_code, 200, status)
            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_customer_cannot_cancel_once_locked(self):
        self.client.force_login(self.customer)
        for status in (
            Order.Status.OUT_FOR_DELIVERY,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        ):
            order = self.make_order(status=status)
            response = self.send("post", f"/api/customer/orders/{order.pk}/cancel")
            self.assertEqual(response.status_code, 409, status)
            order.refresh_from_db()
            self.assertEqual(order.status, status)

    def test_customer_cannot_cancel_someone_elses_order_or_when_logged_out(self):
        order = self.make_order()
        self.assertEqual(self.send("post", f"/api/customer/orders/{order.pk}/cancel").status_code, 401)
        self.client.force_login(self.other)
        self.assertEqual(self.send("post", f"/api/customer/orders/{order.pk}/cancel").status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    # ----- address edits + history -----
    def test_address_edit_records_history_visible_to_admin(self):
        order = self.make_order()
        self.client.force_login(self.customer)
        response = self.send(
            "patch", f"/api/customer/orders/{order.pk}", {"address": "99 New Rd,  Tayabas"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order"]["address"], "99 New Rd, Tayabas")
        self.send("patch", f"/api/customer/orders/{order.pk}", {"address": "7 Third St"})

        # Customers do not get the history in their own payload...
        mine = self.client.get("/api/customer/my-orders").json()["orders"][0]
        self.assertNotIn("address_history", mine)

        self.client.force_login(self.admin)
        shown = self.client.get("/api/admin/orders/").json()["orders"][0]
        self.assertEqual(shown["address"], "7 Third St")
        self.assertEqual(
            [(h["old_address"], h["new_address"]) for h in shown["address_history"]],
            [(self.ADDRESS, "99 New Rd, Tayabas"), ("99 New Rd, Tayabas", "7 Third St")],
        )
        self.assertEqual(shown["address_history"][0]["changed_by"], "Jane Customer")

    def test_unchanged_address_adds_no_history(self):
        order = self.make_order()
        self.client.force_login(self.customer)
        response = self.send("patch", f"/api/customer/orders/{order.pk}", {"address": self.ADDRESS})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.address_changes.count(), 0)

    def test_address_locked_once_out_for_delivery_or_finished(self):
        self.client.force_login(self.customer)
        for status in (
            Order.Status.OUT_FOR_DELIVERY,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        ):
            order = self.make_order(status=status)
            response = self.send("patch", f"/api/customer/orders/{order.pk}", {"address": "Elsewhere"})
            self.assertEqual(response.status_code, 409, status)
            order.refresh_from_db()
            self.assertEqual(order.delivery_address, self.ADDRESS)
            self.assertEqual(order.address_changes.count(), 0)

    def test_only_delivery_orders_have_editable_address(self):
        order = self.make_order(order_type=Order.OrderType.PICKUP, delivery_address="")
        self.client.force_login(self.customer)
        response = self.send("patch", f"/api/customer/orders/{order.pk}", {"address": "Somewhere"})
        self.assertEqual(response.status_code, 409)

    def test_address_edit_validation_and_ownership(self):
        order = self.make_order()
        self.client.force_login(self.customer)
        url = f"/api/customer/orders/{order.pk}"
        self.assertEqual(self.send("patch", url, {"address": "  "}).status_code, 400)
        self.assertEqual(self.send("patch", url, {"address": "x" * 256}).status_code, 400)
        self.assertEqual(self.send("patch", url, {"status": "COMPLETED"}).status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.send("patch", url, {"address": "Mine now"}).status_code, 404)

    def test_can_flags_in_order_payload(self):
        self.make_order()
        self.make_order(status=Order.Status.OUT_FOR_DELIVERY)
        self.client.force_login(self.customer)
        orders = {o["status"]: o for o in self.client.get("/api/customer/my-orders").json()["orders"]}
        self.assertTrue(orders["PENDING"]["can_cancel"])
        self.assertTrue(orders["PENDING"]["can_edit_address"])
        self.assertFalse(orders["OUT_FOR_DELIVERY"]["can_cancel"])
        self.assertFalse(orders["OUT_FOR_DELIVERY"]["can_edit_address"])

    # ----- admin status + payment -----
    def test_admin_status_flow_for_delivery(self):
        order = self.make_order()
        self.client.force_login(self.admin)
        url = f"/api/admin/orders/{order.pk}/"
        for status in ("OUT_FOR_DELIVERY", "COMPLETED", "PENDING"):
            response = self.send("patch", url, {"status": status})
            self.assertEqual(response.status_code, 200, status)
            order.refresh_from_db()
            self.assertEqual(order.status, status)

    def test_out_for_delivery_only_for_delivery_orders(self):
        self.client.force_login(self.admin)
        for order_type in (Order.OrderType.DINE_IN, Order.OrderType.PICKUP):
            order = self.make_order(order_type=order_type)
            response = self.send("patch", f"/api/admin/orders/{order.pk}/", {"status": "OUT_FOR_DELIVERY"})
            self.assertEqual(response.status_code, 400, order_type)
            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.PENDING)
            self.assertEqual(
                self.send("patch", f"/api/admin/orders/{order.pk}/", {"status": "COMPLETED"}).status_code, 200
            )

    def test_admin_cannot_set_unlisted_statuses_or_touch_cancelled_orders(self):
        order = self.make_order()
        self.client.force_login(self.admin)
        url = f"/api/admin/orders/{order.pk}/"
        for status in ("CANCELLED", "PREPARING", "NOPE"):
            self.assertEqual(self.send("patch", url, {"status": status}).status_code, 400, status)
        cancelled = self.make_order(status=Order.Status.CANCELLED)
        url = f"/api/admin/orders/{cancelled.pk}/"
        self.assertEqual(self.send("patch", url, {"status": "COMPLETED"}).status_code, 409)
        self.assertEqual(self.send("patch", url, {"is_paid": True}).status_code, 409)

    def test_payment_is_tracked_separately_from_status(self):
        order = self.make_order()
        self.client.force_login(self.admin)
        url = f"/api/admin/orders/{order.pk}/"
        response = self.send("patch", url, {"is_paid": True})
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(order.status, Order.Status.PENDING)  # status untouched
        self.assertEqual(response.json()["order"]["payment_status"], "PAID")

        self.assertEqual(self.send("patch", url, {"status": "COMPLETED"}).status_code, 200)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)  # paying/completing are independent

        self.assertEqual(self.send("patch", url, {"is_paid": False}).status_code, 200)
        order.refresh_from_db()
        self.assertFalse(order.is_paid)
        self.assertIsNone(order.paid_at)
        self.assertEqual(self.send("patch", url, {"is_paid": "yes"}).status_code, 400)
        self.assertEqual(self.send("patch", url, {}).status_code, 400)

    def test_admin_filters_by_payment_type_and_status(self):
        self.make_order(is_paid=True)
        self.make_order(order_type=Order.OrderType.PICKUP)
        self.make_order(status=Order.Status.OUT_FOR_DELIVERY)
        self.make_order(status=Order.Status.CANCELLED)
        self.client.force_login(self.admin)

        def count(query):
            response = self.client.get(f"/api/admin/orders/?{query}")
            self.assertEqual(response.status_code, 200, query)
            return len(response.json()["orders"])

        self.assertEqual(count("payment=paid"), 1)
        self.assertEqual(count("payment=unpaid"), 3)
        self.assertEqual(count("type=pickup"), 1)
        self.assertEqual(count("filter=out_for_delivery"), 1)
        self.assertEqual(count("filter=cancelled"), 1)
        self.assertEqual(self.client.get("/api/admin/orders/?payment=maybe").status_code, 400)
        self.assertEqual(self.client.get("/api/admin/orders/?type=maybe").status_code, 400)
