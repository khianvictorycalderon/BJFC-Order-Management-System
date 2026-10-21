from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.functions import Lower

class User(AbstractUser):
    phone_number = models.CharField(max_length=15,blank=True,null=True)
    
    def __str__(self):
        return self.user.username


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
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders"
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    created_at = models.DateTimeField(auto_now_add=True)
    estimated_time =  models.DateTimeField(blank=True, null=True) 
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    def __str__(self):
        return f"Order #{self.id}"


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