import logging
import os

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        post_migrate.connect(
            create_default_admin,
            sender=self,
            dispatch_uid="core.create_default_admin",
        )


def create_default_admin(**kwargs):
    username = os.environ.get("ADMIN_DEFAULT_USERNAME", "").strip()
    password = os.environ.get("ADMIN_DEFAULT_PASSWORD", "")
    if not username or not password:
        logging.getLogger(__name__).warning(
            "Default admin was not created: ADMIN_DEFAULT_USERNAME and "
            "ADMIN_DEFAULT_PASSWORD must both be set."
        )
        return
    if len(username) > 150:
        raise ImproperlyConfigured("ADMIN_DEFAULT_USERNAME must be 150 characters or fewer.")

    from core.models import User

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        user = User(username=username, is_active=True, is_staff=True)
        if "@" in username:
            user.email = username
        user.set_password(password)
        user.save()
        logging.getLogger(__name__).info("Created the environment-configured default admin.")
        return

    if not user.is_staff:
        raise ImproperlyConfigured(
            "ADMIN_DEFAULT_USERNAME is already assigned to a non-staff account."
        )
