from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator

class User(AbstractUser):
    # Defining distinct roles for the university library system
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('librarian', 'Librarian'),
        ('admin', 'Admin'),
    )
    
    DEPARTMENT_CHOICES = (
        ('BCSE', 'BCSE'),
        ('BEEE', 'BEEE'),
        ('BSCE', 'BSCE'),
        ('BSME', 'BSME'),
        ('BsAG', 'BsAG'),
        ('BATHM', 'BATHM'),
        ('BE', 'BE'),
        ('B.Eco', 'B.Eco'),
        ('BBA', 'BBA'),
    )
    
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='student',
        help_text="The role determining user access rights."
    )

    username = models.CharField(
        max_length=150,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z]+$',
                message="Username must contain only letters.",
                code='invalid_username'
            )
        ],
        error_messages={
            'unique': "A user with that username already exists.",
        },
    )

    first_name = models.CharField(
        max_length=150,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z\s]+$',
                message="First name must contain only letters and spaces.",
                code='invalid_first_name'
            )
        ]
    )

    last_name = models.CharField(
        max_length=150,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z\s]+$',
                message="Last name must contain only letters and spaces.",
                code='invalid_last_name'
            )
        ]
    )
    
    # Library system specific optional details
    student_id = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        unique=True,
        help_text="Unique Student ID (only applicable for Students).",
        validators=[
            RegexValidator(
                regex=r'^\d+$',
                message="Student ID must contain only digits (whole numbers).",
                code='invalid_student_id'
            )
        ]
    )
    
    department = models.CharField(
        max_length=100, 
        choices=DEPARTMENT_CHOICES,
        blank=True, 
        null=True,
        help_text="Academic department for the user."
    )

    def is_student(self):
        return self.role == 'student'

    def is_librarian(self):
        return self.role == 'librarian'

    def is_admin(self):
        return self.role == 'admin'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
