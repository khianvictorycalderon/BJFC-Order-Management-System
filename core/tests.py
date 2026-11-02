from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from core.apps import create_default_admin
from core.models import User


class DefaultAdminProvisioningTests(TestCase):
    def test_creates_staff_account_from_environment_credentials(self):
        credentials = {
            "ADMIN_DEFAULT_USERNAME": "configured-admin@example.test",
            "ADMIN_DEFAULT_PASSWORD": "A-strong-test-password-2026!",
        }
        with patch.dict("os.environ", credentials):
            create_default_admin()

        admin = User.objects.get(username=credentials["ADMIN_DEFAULT_USERNAME"])
        self.assertTrue(admin.is_staff)
        self.assertFalse(admin.is_superuser)
        self.assertTrue(admin.check_password(credentials["ADMIN_DEFAULT_PASSWORD"]))

    def test_existing_default_admin_password_is_not_reset(self):
        admin = User.objects.create_user(
            username="existing-default-admin",
            password="existing-password",
            is_staff=True,
        )
        credentials = {
            "ADMIN_DEFAULT_USERNAME": admin.username,
            "ADMIN_DEFAULT_PASSWORD": "new-default-password",
        }
        with patch.dict("os.environ", credentials):
            create_default_admin()

        admin.refresh_from_db()
        self.assertTrue(admin.check_password("existing-password"))
        self.assertFalse(admin.check_password(credentials["ADMIN_DEFAULT_PASSWORD"]))

    def test_does_not_promote_existing_customer(self):
        customer = User.objects.create_user(username="customer-account", password="password")
        credentials = {
            "ADMIN_DEFAULT_USERNAME": customer.username,
            "ADMIN_DEFAULT_PASSWORD": "default-password",
        }
        with patch.dict("os.environ", credentials):
            with self.assertRaises(ImproperlyConfigured):
                create_default_admin()

        customer.refresh_from_db()
        self.assertFalse(customer.is_staff)
