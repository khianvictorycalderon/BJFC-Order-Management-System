from django.contrib import admin
from .models import FoodItem, Rating

admin.site.register(FoodItem)
@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "score", "review", "date")
    list_filter = ("score",)