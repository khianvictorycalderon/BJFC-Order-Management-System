from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.files.storage import FileSystemStorage
from django.db.models.functions import Lower
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateReceiptStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.BASE_DIR / "private_media", base_url=None)


class User(AbstractUser):
    phone_number = models.CharField(max_length=15,blank=True,null=True)
    
    def __str__(self):
        return self.username


class Meta:
    constraints = [
        models.UniqueConstraint(
            Lower("email"),
            name="unique_user_email_case_insensitive",
        ),
    ]

class PageInfo(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    slug = models.SlugField(unique=True)
    def __str__(self):
        return self.title

class StoreInformation(models.Model):
    storename = models.CharField(max_length=255)
    contact = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    def __str__(self):
        return self.storename

class FoodCategory(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    available = models.BooleanField(default=True)
    def __str__(self):
        return self.name

class FoodItem(models.Model):
    category = models.ForeignKey(
        FoodCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="food_items"
    )
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    image = models.ImageField(
        upload_to="food_items/",
        blank=True,
        null=True
    )
    available = models.BooleanField(default=True)
    addons = models.ManyToManyField(
        "FoodAddon",
        blank=True,
        related_name="food_items",
    )

    def __str__(self):
        return self.name


class FoodAddon(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    available = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Cart(models.Model):
    customer = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="cart"
    )
    def __str__(self):
        return f"Cart - {self.customer.username}"

class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items"
    )
    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.CASCADE,
        related_name="cart_items"
    )
    quantity = models.PositiveIntegerField(default=1)
    def __str__(self):
        return f"{self.quantity}x {self.food_item.name}"

class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PREPARING = "PREPARING", "Preparing"
        OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for Delivery"
        COMPLETED = "COMPLETED", "Completed"
        INVALID = "INVALID", "Invalid"
        CANCELLED = "CANCELLED", "Cancelled"

    class OrderType(models.TextChoices):
        DINE_IN = "DINE_IN", "Dine-In"
        PICKUP = "PICKUP", "Pickup"
        DELIVERY = "DELIVERY", "Delivery"

    class PaymentMethod(models.TextChoices):
        CASH_ON_DELIVERY = "CASH_ON_DELIVERY", "Cash on Delivery"
        CASH_ON_PICKUP = "CASH_ON_PICKUP", "Cash on Pickup"
        GCASH = "GCASH", "GCash"

    class PaymentReviewStatus(models.TextChoices):
        NOT_REQUIRED = "NOT_REQUIRED", "Not required"
        AWAITING_RECEIPT = "AWAITING_RECEIPT", "Receipt required"
        PENDING = "PENDING", "Receipt pending review"
        INVALID = "INVALID", "Invalid receipt"
        VERIFIED = "VERIFIED", "Verified"

    # While an order is in one of these statuses the customer may still cancel it
    # or (for deliveries) change its address. Once it is Out for Delivery,
    # Completed, Invalid or Cancelled it is locked.
    CUSTOMER_EDITABLE_STATUSES = (
        Status.PENDING,
        Status.CONFIRMED,
        Status.PREPARING,
    )

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders"
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    order_type = models.CharField(
        max_length=20,
        choices=OrderType.choices,
        default=OrderType.DINE_IN,
    )
    # Required for Pickup and Delivery orders; left blank for Dine-In.
    contact_phone = models.CharField(max_length=20, blank=True, default="")
    # Only used by Delivery orders.
    delivery_address = models.CharField(max_length=255, blank=True, default="")

    payment_method = models.CharField(
        max_length=24,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH_ON_PICKUP,
    )
    gcash_receipt = models.ImageField(
        storage=PrivateReceiptStorage(),
        upload_to="gcash_receipts/",
        blank=True,
        null=True,
    )
    payment_review_status = models.CharField(
        max_length=20,
        choices=PaymentReviewStatus.choices,
        default=PaymentReviewStatus.NOT_REQUIRED,
    )
    receipt_invalid_reason = models.TextField(blank=True, default="")
    invalid_reason = models.TextField(blank=True, default="")

    # Payment is tracked separately from the order status.
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    estimated_time =  models.DateTimeField(blank=True, null=True) 
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    @property
    def can_customer_cancel(self):
        return self.status in self.CUSTOMER_EDITABLE_STATUSES

    @property
    def can_customer_edit_address(self):
        return (
            self.order_type == self.OrderType.DELIVERY
            and self.status in self.CUSTOMER_EDITABLE_STATUSES
        )

    def __str__(self):
        return f"Order #{self.id}"


class OrderAuditEvent(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    event_type = models.CharField(max_length=40)
    details = models.TextField()
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Order #{self.order_id}: {self.event_type}"


class OrderAddressChange(models.Model):
    """One row per time a customer edited a delivery order's address."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="address_changes",
    )
    old_address = models.CharField(max_length=255, blank=True)
    new_address = models.CharField(max_length=255)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at", "pk"]

    def __str__(self):
        return f"Order #{self.order_id} address change"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.PROTECT,
        related_name="order_items"
    )

    quantity = models.PositiveIntegerField(default=1)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        return f"{self.quantity}x {self.food_item.name}"

class OrderItemAddon(models.Model):
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="selected_addons",
    )
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)

class Favorite(models.Model):
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "food_item"],
                name="unique_customer_favorite",
            ),
        ]

class ContactMessage(models.Model):
    class Status(models.TextChoices):
        UNREAD = "unread", "Unread"
        READ = "read", "Read"
        RESOLVED = "resolved", "Resolved"

    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    message = models.TextField()
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_messages",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UNREAD,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Contact message from {self.name}"

class Rating(models.Model):
    SCORE_CHOICES=[
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_ratings"
    )
    score = models.IntegerField(choices=SCORE_CHOICES)
    review = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)

class LoginRecord(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )
    login_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username

class PasswordResetRequest(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username
    
class LandingPage(models.Model):
    main_heading = models.CharField(max_length=255)
    subheading_description = models.TextField()
    hero_image = models.URLField(blank=True, default="")
    button_text = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )
    button_link = models.CharField(
        max_length=255,
        blank=True,
        default=""
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.main_heading