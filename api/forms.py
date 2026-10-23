import json
import re
from django import forms
from core.models import ContactMessage, FoodItem

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")


def parse_payload(request):
    if (request.content_type or "").startswith("application/json"):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Invalid JSON data.")
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data, None
    return request.POST.copy(), request.FILES


def form_errors(form):
    return {field: [str(e) for e in errs] for field, errs in form.errors.items()}


class FoodItemForm(forms.ModelForm):
    class Meta:
        model = FoodItem
        fields = ["name", "description", "category", "price", "available", "image"]

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image
        if image.size > MAX_IMAGE_BYTES:
            raise forms.ValidationError("Image must be 5 MB or smaller.")
        fmt = getattr(getattr(image, "image", None), "format", None)
        if fmt not in ALLOWED_IMAGE_FORMATS:
            raise forms.ValidationError("Image must be a JPEG, PNG, WEBP or GIF file.")
        return image


class ContactMessageForm(forms.ModelForm):
    message = forms.CharField(max_length=2000, widget=forms.Textarea)

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "message"]

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if phone and not PHONE_RE.match(phone):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone