from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

class CustomUserAdmin(UserAdmin):
    model = User
    # Including custom fields in detail views
    fieldsets = UserAdmin.fieldsets + (
        ('Library Roles & Info', {'fields': ('role', 'student_id', 'department')}),
    )
    # Including custom fields in creation views
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Library Roles & Info', {
            'fields': ('role', 'student_id', 'department'),
        }),
    )
    
    list_display = ['username', 'email', 'role', 'student_id', 'department', 'is_staff']
    list_filter = ['role', 'is_staff', 'is_superuser', 'is_active']
    search_fields = ['username', 'email', 'student_id']
    ordering = ['username']

admin.site.register(User, CustomUserAdmin)
