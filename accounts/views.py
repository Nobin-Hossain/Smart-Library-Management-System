from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from .forms import UserRegistrationForm, UserLoginForm
from .decorators import role_required
from django.utils import timezone
from books.models import (
    IssueTransaction,
    ReturnRequest,
    Fine,
    Reservation,
    Notification,
)
from books.views import get_user_borrow_stats
from django.shortcuts import get_object_or_404
from .forms import UserEditForm
from django.views.decorators.http import require_POST
from django.http import HttpResponseNotAllowed

User = get_user_model()


def get_dashboard_redirect(user):
    """
    Helper function to determine the correct dashboard URL based on User role.
    """
    if user.role == "student":
        return "student_dashboard"
    elif user.role == "librarian":
        return "librarian_dashboard"
    elif user.role == "admin":
        return "admin_dashboard"
    return "student_dashboard"


def register_view(request):
    """
    Handles user registration.
    If the user is already logged in, redirect them directly to their dashboard.
    Validates form data and hashes passwords securely via Django's User model save().
    """
    if request.user.is_authenticated:
        return redirect(get_dashboard_redirect(request.user))

    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            # Save the new user. The form's save method splits the full name
            # and uses user.set_password() to securely hash the password.
            user = form.save()
            messages.success(
                request,
                f"Registration successful for {user.username}! You can now log in.",
            )
            return redirect("login")
        else:
            messages.error(request, "Please correct the registration errors below.")
    else:
        form = UserRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    """
    Handles user login, supporting either Username or Email as input.
    Validates password, signs the user into a session, and redirects by role.
    Implements a 'Remember Me' checkbox that extends session lifespan.
    """
    if request.user.is_authenticated:
        return redirect(get_dashboard_redirect(request.user))

    if request.method == "POST":
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username_or_email = form.cleaned_data.get("username_or_email")
            password = form.cleaned_data.get("password")
            remember_me = form.cleaned_data.get("remember_me")

            # Supporting username or email login:
            # Check if input is email format, and lookup the matching username if exists
            username = username_or_email
            if "@" in username_or_email:
                try:
                    user_record = User.objects.get(email__iexact=username_or_email)
                    username = user_record.username
                except User.DoesNotExist:
                    # Fallback if no user is found with that email
                    pass

            # Before authenticate(), user is searched by username using is_active
            try:
                target_user = User.objects.get(username=username)
                if not target_user.is_active and target_user.check_password(password):
                    messages.error(
                        request, "You have been blocked. Please, contact the Admin."
                    )
                    return render(request, "accounts/login.html", {"form": form})
            except User.DoesNotExist:
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

                    messages.success(
                        request, f"Welcome back, {user.first_name or user.username}!"
                    )
                    return redirect(get_dashboard_redirect(user))
                else:
                    messages.error(
                        request, "You have been blocked. Please, contact the Admin."
                    )
            else:
                messages.error(request, "Invalid username/email or password.")
        else:
            messages.error(request, "Please fix the login form errors.")
    else:
        form = UserLoginForm()

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    """
    Logs out the user, flushes the session data, and redirects to the login screen.
    """
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect("login")


# DASHBOARDS
# Protect with both @login_required and custom @role_required decorators


@login_required
@role_required("student")
def student_dashboard(request):
    """
    Student dashboard view displaying real borrowing statistics and recent activity.
    """
    today = timezone.now()

    # Calculate count of active (ISSUED) transactions for the student (0 or 1)
    books_borrowed_count = IssueTransaction.objects.filter(
        user=request.user, status=IssueTransaction.STATUS_ISSUED
    ).count()

    # Fetch student's last 5 transactions, ordered by issue_date descending
    recent_activity = IssueTransaction.objects.filter(user=request.user).order_by(
        "-issue_date"
    )[:5]

    # Fetch pending return request transaction IDs in one query to avoid N+1 queries
    pending_return_txn_ids = set(
        ReturnRequest.objects.filter(
            transaction__in=recent_activity, status=ReturnRequest.STATUS_PENDING
        ).values_list("transaction_id", flat=True)
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
            transaction.display_status = "Returned"
        elif transaction.transaction_id in pending_return_txn_ids:
            transaction.display_status = "Return Requested"
        elif transaction.due_date < today:
            transaction.display_status = "Overdue"
        elif transaction.due_date.date() == today.date():
            transaction.display_status = "Due Today"
        else:
            transaction.display_status = "Active"

    unpaid_fines = Fine.objects.filter(
        transaction__user=request.user, status=Fine.STATUS_UNPAID
    )
    total_fine_amount = unpaid_fines.aggregate(total=Sum("amount"))["total"] or 0

    # Active reservation (WAITING or NOTIFIED) — at most one per student
    active_reservation = Reservation.objects.filter(
        user=request.user,
        status__in=[Reservation.STATUS_WAITING, Reservation.STATUS_NOTIFIED],
    ).first()

    context = {
        "books_borrowed_count": books_borrowed_count,
        "recent_activity": recent_activity,
        "total_fine_amount": total_fine_amount,
        "active_reservation": active_reservation,
    }
    return render(request, "accounts/dashboard_student.html", context)


@login_required
@role_required("admin")
def admin_dashboard(request):
    """
    System administrator dashboard view containing admin actions.
    """
    unpaid_fines = Fine.objects.filter(status=Fine.STATUS_UNPAID)
    total_unpaid_amount = unpaid_fines.aggregate(total=Sum("amount"))["total"] or 0
    unpaid_fines_count = unpaid_fines.count()

    # Active reservation queue count (WAITING + NOTIFIED)
    reservation_queue_count = Reservation.objects.filter(
        status__in=[Reservation.STATUS_WAITING, Reservation.STATUS_NOTIFIED]
    ).count()

    # Real user stats
    total_students = User.objects.filter(role="student").count()
    total_librarians = User.objects.filter(role="librarian").count()
    total_users = total_students + total_librarians

    # Recent Activity Feed
    recent_activity = Notification.objects.filter(user__role="admin").order_by(
        "-created_at"
    )[:10]

    return render(
        request,
        "accounts/dashboard_admin.html",
        {
            "total_unpaid_amount": total_unpaid_amount,
            "unpaid_fines_count": unpaid_fines_count,
            "reservation_queue_count": reservation_queue_count,
            "total_users": total_users,
            "recent_activity": recent_activity,
        },
    )


@login_required
@role_required("admin")
def user_management_list(request):
    """
    Lists students and librarians for the administrator.
    """

    students = User.objects.filter(role="student").order_by("username")
    for student in students:
        student.borrow_stats = get_user_borrow_stats(student)

    librarians = User.objects.filter(role="librarian").order_by("username")

    context = {
        "students": students,
        "librarians": librarians,
        "total_students": students.count(),
        "total_librarians": librarians.count(),
    }
    return render(request, "accounts/user_management_list.html", context)


@login_required
@role_required("admin")
def edit_user(request, user_id):
    """
    Allows admin to edit user details (excluding password).
    """

    user = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"User details for {user.username} updated successfully."
            )
            return redirect("user_management_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserEditForm(instance=user)

    return render(
        request, "accounts/edit_user.html", {"form": form, "user_to_edit": user}
    )


@login_required
@role_required("admin")
def toggle_user_block(request, user_id):
    """
    Toggles is_active status of a student user. Librarians and admins cannot be blocked here.
    Only allows POST requests.
    """

    if request.method != "POST":
        # Standard approach is HTTP 405 Method Not Allowed or similar, but the user specifies POST only.
        # We can use Django's HttpResponseNotAllowed or return custom forbidden/error, let's return a 405.
        return HttpResponseNotAllowed(["POST"])

    student = get_object_or_404(User, pk=user_id, role="student")
    student.is_active = not student.is_active
    student.save()

    if student.is_active:
        messages.success(
            request, f"Student {student.username} has been unblocked successfully."
        )
    else:
        messages.success(
            request, f"Student {student.username} has been blocked successfully."
        )
    return redirect("user_management_list")


def forbidden_view(request):
    """
    Renders custom 403 forbidden page.
    """
    return render(request, "accounts/forbidden.html", status=403)
