from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class RepeatedCharacterPasswordValidator:
    def validate(self, password, user=None):
        if password and len(set(password.casefold())) == 1:
            raise ValidationError(
                _("The password cannot consist of a single repeated character."),
                code="repeated_character",
            )

    def get_help_text(self):
        return _("Your password cannot consist of a single repeated character.")
