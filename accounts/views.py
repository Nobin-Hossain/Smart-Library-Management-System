from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import UserRegistrationForm, UserLoginForm
from .decorators import role_required
from django.utils import timezone
from books.models import IssueTransaction, ReturnRequest

User = get_user_model()

def get_dashboard_redirect(user):
    """
    Helper function to determine the correct dashboard URL based on User role.
    """
    if user.role == 'student':
        return 'student_dashboard'
    elif user.role == 'librarian':
        return 'librarian_dashboard'
    elif user.role == 'admin':
        return 'admin_dashboard'
    return 'student_dashboard'

def register_view(request):
    """
    Handles user registration.
    If the user is already logged in, redirect them directly to their dashboard.
    Validates form data and hashes passwords securely via Django's User model save().
    """
    if request.user.is_authenticated:
        return redirect(get_dashboard_redirect(request.user))

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            # Save the new user. The form's save method splits the full name
            # and uses user.set_password() to securely hash the password.
            user = form.save()
            messages.success(request, f"Registration successful for {user.username}! You can now log in.")
            return redirect('login')
        else:
            messages.error(request, "Please correct the registration errors below.")
    else:
        form = UserRegistrationForm()
        
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    """
    Handles user login, supporting either Username or Email as input.
    Validates password, signs the user into a session, and redirects by role.
    Implements a 'Remember Me' checkbox that extends session lifespan.
    """
    if request.user.is_authenticated:
        return redirect(get_dashboard_redirect(request.user))

    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username_or_email = form.cleaned_data.get('username_or_email')
            password = form.cleaned_data.get('password')
            remember_me = form.cleaned_data.get('remember_me')

            # Supporting username or email login:
            # Check if input is email format, and lookup the matching username if exists
            username = username_or_email
            if '@' in username_or_email:
                try:
                    user_record = User.objects.get(email__iexact=username_or_email)
                    username = user_record.username
                except User.DoesNotExist:
                    # Fallback if no user is found with that email
                    pass

            # Authenticate user credentials
            user = authenticate(request, username=username, password=password)

            if user is not None:
                if user.is_active:
                    login(request, user)
                    
                    # Manage Session Expiry based on "Remember Me" choice
                    if remember_me:
                        # Keep session active for 2 weeks
                        request.session.set_expiry(1209600)
                    else:
                        # Expire session when browser closes
                        request.session.set_expiry(0)
                        
                    messages.success(request, f"Welcome back, {user.first_name or user.username}!")
                    return redirect(get_dashboard_redirect(user))
                else:
                    messages.error(request, "This account has been deactivated.")
            else:
                messages.error(request, "Invalid username/email or password.")
        else:
            messages.error(request, "Please fix the login form errors.")
    else:
        form = UserLoginForm()

    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    """
    Logs out the user, flushes the session data, and redirects to the login screen.
    """
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')


# DASHBOARDS
# Protect with both @login_required and custom @role_required decorators

@login_required
@role_required('student')
def student_dashboard(request):
    """
    Student dashboard view displaying real borrowing statistics and recent activity.
    """
    today = timezone.now().date()

    # Calculate count of active (ISSUED) transactions for the student (0 or 1)
    books_borrowed_count = IssueTransaction.objects.filter(
        user=request.user,
        status=IssueTransaction.STATUS_ISSUED
    ).count()

    # Fetch student's last 5 transactions, ordered by issue_date descending
    recent_activity = IssueTransaction.objects.filter(
        user=request.user
    ).order_by('-issue_date')[:5]

    # Fetch pending return request transaction IDs in one query to avoid N+1 queries
    pending_return_txn_ids = set(
        ReturnRequest.objects.filter(
            transaction__in=recent_activity, status=ReturnRequest.STATUS_PENDING
        ).values_list('transaction_id', flat=True)
    )

    # Compute display_status on Python objects for template rendering:
    # Checked strictly in this order:
    # a) if transaction.status == IssueTransaction.STATUS_RETURNED -> 'Returned'
    # b) elif transaction.transaction_id in pending_return_txn_ids -> 'Return Requested' [NEW]
    # c) elif transaction.due_date == today -> 'Due Today'
    # d) elif transaction.due_date < today -> 'Overdue'
    # e) else -> 'Active'
    for transaction in recent_activity:
        if transaction.status == IssueTransaction.STATUS_RETURNED:
            transaction.display_status = 'Returned'
        elif transaction.transaction_id in pending_return_txn_ids:
            transaction.display_status = 'Return Requested'
        elif transaction.due_date == today:
            transaction.display_status = 'Due Today'
        elif transaction.due_date < today:
            transaction.display_status = 'Overdue'
        else:
            transaction.display_status = 'Active'

    context = {
        'books_borrowed_count': books_borrowed_count,
        'recent_activity': recent_activity,
    }
    return render(request, 'accounts/dashboard_student.html', context)


@login_required
@role_required('admin')
def admin_dashboard(request):
    """
    System administrator dashboard view containing admin actions.
    """
    return render(request, 'accounts/dashboard_admin.html')

def forbidden_view(request):
    """
    Renders custom 403 forbidden page.
    """
    return render(request, 'accounts/forbidden.html', status=403)
