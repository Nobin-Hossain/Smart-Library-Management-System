from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from .models import Book

# Validators

# Text-only: letters (any case), spaces, and common punctuation used in titles
# and author names (hyphens, apostrophes, periods, commas, colons, ampersands,
# parentheses, slashes, exclamation/question marks). Digits are NOT allowed.
TEXT_ONLY_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-z\s\-\'\.\,\:\;\!\?\(\)&\/]+$",
    message="This field must contain only letters and punctuation — digits are not allowed.",
    code="text_only",
)

# ISBN: digits and hyphens only (e.g. 978-0-262-03384-8 or 9780262033848).
# Must start and end with a digit, so a lone hyphen or leading/trailing
# hyphen is rejected.
ISBN_VALIDATOR = RegexValidator(
    regex=r"^\d[\d\-]*\d$|^\d$",
    message="ISBN must contain only digits and hyphens, e.g. 978-0-262-03384-8.",
    code="invalid_isbn",
)


# Form


class BookForm(forms.ModelForm):
    """
    ModelForm for creating and editing Book instances.

    Validation rules:
    - Title, Author, Category, Publisher: letters and punctuation only — no digits.
    - ISBN: digits and hyphens only — no letters, no negative sign, no decimals.
    - Price: positive whole number — no decimals, no negative, no text.
    - Available Copies must not exceed Total Copies.
    """

    # Override the model's DecimalField with an IntegerField so that
    # fractional values (e.g. 9.99) and negative values are rejected
    # at the form level.  Django will persist the integer as a Decimal.
    price = forms.IntegerField(
        min_value=1,
        label="Price (৳)",
        widget=forms.NumberInput(
            attrs={
                "placeholder": "e.g. 500",
                "min": "1",
                "step": "1",  # disables decimal entry in the browser
                "class": "form-input",
            }
        ),
        error_messages={
            "required": "Price is required.",
            "invalid": "Price must be a whole number — no decimal points allowed.",
            "min_value": "Price must be at least 1.",
        },
    )

    class Meta:
        model = Book
        fields = [
            "title",
            "author",
            "isbn",
            "category",
            "publisher",
            "price",
            "total_copies",
            "available_copies",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Introduction to Algorithms",
                    "class": "form-input",
                }
            ),
            "author": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Thomas H. Cormen",
                    "class": "form-input",
                }
            ),
            "isbn": forms.TextInput(
                attrs={
                    "placeholder": "e.g. 978-0-262-03384-8",
                    "class": "form-input",
                    "inputmode": "numeric",  # hint mobile keyboards to show digits
                }
            ),
            "category": forms.TextInput(
                attrs={
                    "placeholder": "e.g. Computer Science",
                    "class": "form-input",
                }
            ),
            "publisher": forms.TextInput(
                attrs={
                    "placeholder": "e.g. MIT Press",
                    "class": "form-input",
                }
            ),
            "total_copies": forms.NumberInput(
                attrs={
                    "placeholder": "1",
                    "min": "1",
                    "step": "1",
                    "class": "form-input",
                }
            ),
            "available_copies": forms.NumberInput(
                attrs={
                    "placeholder": "1",
                    "min": "0",
                    "step": "1",
                    "class": "form-input",
                }
            ),
        }
        labels = {
            "isbn": "ISBN",
            "total_copies": "Total Copies",
            "available_copies": "Available Copies",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Attach text-only validator to all prose fields
        for field_name in ("title", "author", "category", "publisher"):
            self.fields[field_name].validators.append(TEXT_ONLY_VALIDATOR)
        # Attach ISBN format validator
        self.fields["isbn"].validators.append(ISBN_VALIDATOR)

    def clean(self):
        cleaned_data = super().clean()
        title = cleaned_data.get("title")
        author = cleaned_data.get("author")
        isbn = cleaned_data.get("isbn")
        total_copies = cleaned_data.get("total_copies")
        available_copies = cleaned_data.get("available_copies")

        # Available copies cannot exceed total copies
        if total_copies is not None and available_copies is not None:
            if available_copies > total_copies:
                self.add_error(
                    "available_copies",
                    ValidationError(
                        "Available copies cannot exceed the total number of copies (%(total)s).",
                        params={"total": total_copies},
                        code="invalid_copies",
                    ),
                )

        # Duplicate ISBN Check
        if isbn:
            isbn_query = Book.objects.filter(isbn__iexact=isbn.strip())
            # During edit, exclude the current instance from the duplicate check (avoids self-conflict when editing)
            if self.instance.pk:
                isbn_query = isbn_query.exclude(pk=self.instance.pk)

            if isbn_query.exists():
                self.add_error("isbn", "A book with this ISBN already exists.")

        # Duplicate Title & Author Check (Case-insensitive)
        if title and author:
            title_query = Book.objects.filter(
                title__iexact=title.strip(), author__iexact=author.strip()
            )
            if self.instance.pk:
                title_query = title_query.exclude(pk=self.instance.pk)

            if title_query.exists():
                self.add_error(
                    "title",
                    f'A book named "{title}" by "{author}" already exists in the catalog.',
                )

        return cleaned_data
