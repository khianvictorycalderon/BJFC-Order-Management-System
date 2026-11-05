from urllib.parse import parse_qs, urlsplit

from django.test import TestCase

from core.models import User


class PageAccessTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="page-customer",
            password="customer-test-password",
        )
        self.admin = User.objects.create_user(
            username="page-admin",
            password="admin-test-password",
            is_staff=True,
        )

    def test_customer_private_pages_require_customer_login(self):
        private_paths = (
            "/private/",
            "/dashboard",
            "/dashboard/",
            "/my-orders",
            "/my-orders/",
            "/account",
            "/account/",
        )
        for path in private_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                location = urlsplit(response["Location"])
                self.assertEqual(location.path, "/login/")
                self.assertEqual(parse_qs(location.query).get("next"), [path])

    def test_admin_pages_require_staff_login(self):
        admin_paths = (
            "/admin-panel/dashboard/",
            "/admin-panel/menu/",
            "/admin-panel/orders/",
            "/admin-panel/feedback/",
            "/admin-panel/users/",
            "/admin-panel/settings/home/",
            "/admin-panel/settings/about/",
            "/admin-panel/settings/menu/",
            "/admin-panel/settings/contact/",
            "/admin-panel/account/",
        )
        for path in admin_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/admin-login/"))

    def test_signed_in_customer_is_redirected_from_auth_pages(self):
        self.client.force_login(self.customer)
        for path in ("/login/", "/signup/", "/admin-login/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)

    def test_staff_is_redirected_to_admin_from_auth_and_customer_pages(self):
        self.client.force_login(self.admin)
        for path in ("/login/", "/signup/", "/admin-login/", "/dashboard/", "/my-orders/", "/account/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertRedirects(
                    response,
                    "/admin-panel/dashboard/",
                    fetch_redirect_response=False,
                )

    def test_login_rejects_external_next_redirect(self):
        response = self.client.get("/login/?next=https://example.com/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["next_url"], "")


class NavbarAuthButtonTests(TestCase):
    """The navbar's Log in button becomes a role-aware Dashboard link when signed in."""

    PUBLIC_PAGES = ("/", "/menu/", "/about/", "/contact/")

    def setUp(self):
        self.customer = User.objects.create_user(username="nav-customer", password="x-Test-pass-1")
        self.admin = User.objects.create_user(
            username="nav-admin", password="x-Test-pass-1", is_staff=True
        )

    def assert_button(self, path, label, href, absent_label):
        html = self.client.get(path).content.decode()
        self.assertIn(f'href="{href}"', html, path)
        self.assertRegex(html, rf'href="{href}"[^>]*>\s*{label}\s*</a>', path)
        self.assertNotRegex(html, rf'>\s*{absent_label}\s*</a>', path)

    def test_logged_out_visitors_see_log_in(self):
        for path in self.PUBLIC_PAGES:
            self.assert_button(path, "Log in", "/login/", "Dashboard")

    def test_customer_sees_dashboard_linking_to_customer_dashboard(self):
        self.client.force_login(self.customer)
        for path in self.PUBLIC_PAGES:
            self.assert_button(path, "Dashboard", "/dashboard", "Log in")

    def test_admin_sees_dashboard_linking_to_admin_dashboard(self):
        self.client.force_login(self.admin)
        for path in self.PUBLIC_PAGES:
            self.assert_button(path, "Dashboard", "/admin-panel/dashboard/", "Log in")
