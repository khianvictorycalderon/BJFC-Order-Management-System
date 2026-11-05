import django.db.models.deletion
import core.models
from django.conf import settings
from django.db import migrations, models


def set_existing_payment_methods(apps, schema_editor):
    Order = apps.get_model("core", "Order")
    Order.objects.filter(order_type="DELIVERY").update(payment_method="CASH_ON_DELIVERY")
    Order.objects.exclude(order_type="DELIVERY").update(payment_method="CASH_ON_PICKUP")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_order_types_payment_address_history"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("CASH_ON_DELIVERY", "Cash on Delivery"),
                    ("CASH_ON_PICKUP", "Cash on Pickup"),
                    ("GCASH", "GCash"),
                ],
                default="CASH_ON_PICKUP",
                max_length=24,
            ),
        ),
        migrations.RunPython(set_existing_payment_methods, migrations.RunPython.noop),
        migrations.AddField(
            model_name="order",
            name="gcash_receipt",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=core.models.PrivateReceiptStorage(),
                upload_to="gcash_receipts/",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_review_status",
            field=models.CharField(
                choices=[
                    ("NOT_REQUIRED", "Not required"),
                    ("AWAITING_RECEIPT", "Receipt required"),
                    ("PENDING", "Receipt pending review"),
                    ("INVALID", "Invalid receipt"),
                    ("VERIFIED", "Verified"),
                ],
                default="NOT_REQUIRED",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="receipt_invalid_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="order",
            name="invalid_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("CONFIRMED", "Confirmed"),
                    ("PREPARING", "Preparing"),
                    ("OUT_FOR_DELIVERY", "Out for Delivery"),
                    ("COMPLETED", "Completed"),
                    ("INVALID", "Invalid"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="OrderAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=40)),
                ("details", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_events",
                        to="core.order",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
    ]
