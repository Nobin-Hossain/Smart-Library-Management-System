from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

User = get_user_model()

class UserRegistrationForm(forms.ModelForm):
    # Custom form fields for registration
    full_name = forms.CharField(
        max_length=150, 
        required=True,
        label="Full Name",
        widget=forms.TextInput(attrs={'placeholder': 'Enter your full name'}),
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z\s]+$',
                message="Full name must contain only letters and spaces.",
                code='invalid_full_name'
            )
        ]
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Create a password'}),
        required=True,
        help_text="Must be at least 8 characters, and not too common."
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm your password'}),
        required=True
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'role', 'student_id', 'department']
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Choose a username'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Enter university email'}),
            'role': forms.Select(attrs={'id': 'role_select'}),
            'student_id': forms.TextInput(attrs={'placeholder': 'Enter Student ID (required for students)'}),
            'department': forms.Select(attrs={'id': 'department_select'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        role = cleaned_data.get("role")
        student_id = cleaned_data.get("student_id")
        department = cleaned_data.get("department")

        # 1. Validate that passwords match
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")

        # 2. Apply Django's built-in password validators
        if password:
            try:
                # We validate password using Django's validators (minimum length, common passwords, etc.)
                validate_password(password)
            except ValidationError as e:
                self.add_error('password', e)

        # 3. Conditional validation for role
        if role == 'student':
            if not student_id:
                self.add_error('student_id', "Student ID is required for student accounts.")
            if not department:
                self.add_error('department', "Department is required for student accounts.")
        else:
            # If the user is librarian or admin, clear these out
            cleaned_data['student_id'] = None
            cleaned_data['department'] = None

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        # Split full name into first and last name
        full_name = self.cleaned_data.get('full_name', '')
        name_parts = full_name.strip().split(' ', 1)
        if len(name_parts) > 1:
            user.first_name = name_parts[0]
            user.last_name = name_parts[1]
        else:
            user.first_name = name_parts[0]
            user.last_name = ''

        # Set hashed password correctly
        user.set_password(self.cleaned_data["password"])
        
        if commit:
            user.save()
        return user


class UserLoginForm(forms.Form):
    username_or_email = forms.CharField(
        max_length=150,
        label="Username or Email",
        widget=forms.TextInput(attrs={'placeholder': 'Enter username or email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter your password'}),
        label="Password"
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Remember Me",
        widget=forms.CheckboxInput(attrs={'class': 'remember-me-checkbox'})
    )


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'student_id', 'department']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'student_id': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Ensure email uniqueness, ignoring current instance
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = self.instance.role
        student_id = cleaned_data.get("student_id")
        department = cleaned_data.get("department")

        if role == 'student':
            if not student_id:
                self.add_error('student_id', "Student ID is required for student accounts.")
            if not department:
                self.add_error('department', "Department is required for student accounts.")
        else:
            # Clear student_id and department if not a student
            cleaned_data['student_id'] = None
            cleaned_data['department'] = None

        return cleaned_data
