from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q, F
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, JsonResponse
from django.db import transaction as db_transaction
import datetime
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from accounts.decorators import role_required
from google import genai

from .models import (
    Book,
    BorrowRequest,
    IssueTransaction,
    Notification,
    ReturnRequest,
    Fine,
    Reservation,
    ChatMessage,
)
from .forms import BookForm

User = get_user_model()

# ---------------------------------------------------------------------------
# Gemini AI — module-level client (new google-genai SDK, runs once at import)
# ---------------------------------------------------------------------------

gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
GEMINI_MODEL = "gemini-3.6-flash"


# ---------------------------------------------------------------------------
# Librarian Dashboard
# ---------------------------------------------------------------------------


@login_required
@role_required("librarian", "admin")
def librarian_dashboard(request):
    """
    Librarian dashboard view.
    Displays system statistics (total users, available books, borrowed books)
    and a searchable / filterable book management table.
    """
    # --- Search ---
    query = request.GET.get("q", "").strip()
    books = Book.objects.all()
    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(category__icontains=query)
            | Q(isbn__icontains=query)
        )

    # --- Statistics ---
    all_users = User.objects.filter(role="student").order_by("-date_joined")
    total_users = all_users.count()
    total_available_books = (
        Book.objects.aggregate(total=Sum("available_copies"))["total"] or 0
    )
    total_borrowed_books = sum(
        book.total_copies - book.available_copies for book in Book.objects.all()
    )

    context = {
        "books": books,
        "query": query,
        "total_users": total_users,
        "all_users": all_users,
        "total_available_books": total_available_books,
        "total_borrowed_books": total_borrowed_books,
    }
    return render(request, "accounts/dashboard_librarian.html", context)


# ---------------------------------------------------------------------------
# Book CRUD
# ---------------------------------------------------------------------------


@login_required
@role_required("librarian", "admin")
def book_create(request):
    """
    View to add a new book to the catalog.
    Only librarians and admins may access this view.
    """
    if request.method == "POST":
        form = BookForm(request.POST)
        if form.is_valid():
            book = form.save()
            messages.success(request, f'Book "{book.title}" was added successfully.')
            return redirect("librarian_dashboard")
        else:
            messages.error(request, "Please fix the errors below and try again.")
    else:
        form = BookForm()

    return render(
        request,
        "books/book_form.html",
        {
            "form": form,
            "form_title": "Add New Book",
            "submit_label": "Add Book",
        },
    )


@login_required
@role_required("librarian", "admin")
def book_update(request, pk):
    """
    View to edit an existing book entry.
    Only librarians and admins may access this view.
    """
    book = get_object_or_404(Book, pk=pk)

    if request.method == "POST":
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, f'Book "{book.title}" was updated successfully.')
            return redirect("librarian_dashboard")
        else:
            messages.error(request, "Please fix the errors below and try again.")
    else:
        form = BookForm(instance=book)

    return render(
        request,
        "books/book_form.html",
        {
            "form": form,
            "form_title": f"Edit Book: {book.title}",
            "submit_label": "Save Changes",
            "book": book,
        },
    )


@login_required
@role_required("librarian", "admin")
def book_delete(request, pk):
    """
    View to delete a book with a confirmation step.
    Only librarians and admins may access this view.
    """
    book = get_object_or_404(Book, pk=pk)

    if request.method == "POST":
        title = book.title
        book.delete()
        messages.success(request, f'Book "{title}" was deleted successfully.')
        return redirect("librarian_dashboard")

    return render(request, "books/book_confirm_delete.html", {"book": book})


# ---------------------------------------------------------------------------
# Student Book Catalog
# ---------------------------------------------------------------------------


@login_required
def book_list_user(request):
    """
    View for students to view the full list of books entered by librarians.
    Access Control: Only users with role='student' can access this view.
    Librarians and Admins receive a 403 Forbidden response.
    """
    # CRITICAL access check: ensure only students can access this view
    if getattr(request.user, "role", None) != "student":
        return HttpResponseForbidden(
            "Access denied. This view is reserved for students."
        )

    query = request.GET.get("q", "").strip()
    books = Book.objects.all().order_by("book_id")

    # Search filter using Q objects (case-insensitive partial match on title, author, category)
    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(category__icontains=query)
        )

    # Paginate list: 10 books per page
    paginator = Paginator(books, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "books": page_obj.object_list,
        "query": query,
    }
    return render(request, "books/book_list_user.html", context)


# ---------------------------------------------------------------------------
# Borrow Request Workflow
# ---------------------------------------------------------------------------


@login_required
def create_borrow_request(request, book_id):
    """
    Allows a student to submit a borrow request for a specific book.
    POST only. Security and business-rule checks are applied before creating
    the request.
    """
    # CRITICAL: Only students may submit borrow requests
    if request.user.role != "student":
        messages.error(request, "Only students can request to borrow books.")
        return redirect("book_list_user")

    if request.method != "POST":
        return redirect("book_list_user")

    book = get_object_or_404(Book, pk=book_id)

    # Business rule: a student can hold AT MOST ONE active book at a time.
    # Check (a): does the student already have an issued (unreturned) book?
    already_issued = IssueTransaction.objects.filter(
        user=request.user,
        status=IssueTransaction.STATUS_ISSUED,
    ).exists()

    if already_issued:
        messages.error(
            request,
            "You already have a book issued. Please return it before requesting another.",
        )
        return redirect("book_list_user")

    # Check (b): does the student already have a pending borrow request?
    already_pending = BorrowRequest.objects.filter(
        user=request.user,
        status=BorrowRequest.STATUS_PENDING,
    ).exists()

    if already_pending:
        messages.error(
            request,
            "You already have a pending borrow request. Please wait for it to be reviewed.",
        )
        return redirect("book_list_user")

    # All checks passed — create the borrow request
    BorrowRequest.objects.create(
        user=request.user,
        book=book,
        status=BorrowRequest.STATUS_PENDING,
    )

    # Notify ALL admins so they are aware of the new request
    admin_users = User.objects.filter(role="admin")
    admin_notifications = [
        Notification(
            user=admin,
            message=f"{request.user.username} requested to borrow '{book.title}'.",
        )
        for admin in admin_users
    ]
    Notification.objects.bulk_create(admin_notifications)

    messages.success(
        request,
        f'Your borrow request for "{book.title}" has been submitted. '
        "Please wait for admin approval.",
    )
    return redirect("book_list_user")


def get_user_borrow_stats(user):
    """
    Calculates borrow statistics for a given user.
    Returns a dictionary containing the total borrow count and a reliability status string.
    """
    total_borrows = IssueTransaction.objects.filter(user=user).count()
    if total_borrows == 0:
        status = "New"
    else:
        overdue_count = IssueTransaction.objects.filter(
            user=user,
            status=IssueTransaction.STATUS_RETURNED,
            return_date__gt=F("due_date"),
        ).count()
        if overdue_count == 0:
            status = "Reliable"
        elif 1 <= overdue_count <= 2:
            status = "Caution"
        else:
            status = "Risky"
    return {"total_borrows": total_borrows, "status": status}


@login_required
@role_required("admin")
def admin_request_list(request):
    """
    Admin view listing all PENDING borrow requests.
    Admins can approve or reject each request from this page.
    """
    # Fetch all pending requests with related user and book data in one query
    pending_requests = (
        BorrowRequest.objects.filter(status=BorrowRequest.STATUS_PENDING)
        .select_related("user", "book")
        .order_by("request_date")
    )

    for req in pending_requests:
        req.student_status = get_user_borrow_stats(req.user)["status"]

    default_due_date = (timezone.now() + datetime.timedelta(days=7)).strftime(
        "%Y-%m-%dT%H:%M"
    )

    return render(
        request,
        "books/admin_request_list.html",
        {
            "pending_requests": pending_requests,
            "default_due_date": default_due_date,
        },
    )


@login_required
@role_required("admin")
def approve_borrow_request(request, request_id):
    """
    Admin approves a pending borrow request.
    POST only. Creates an IssueTransaction (which decrements available_copies
    via the model's overridden save()), marks the BorrowRequest as APPROVED,
    and fans out notifications to the student and every librarian.

    The BorrowRequest status update and IssueTransaction creation are wrapped
    in db_transaction.atomic() so it is all-or-nothing — no partial state
    can be written to the database if an error occurs mid-way.
    """
    if request.method != "POST":
        return redirect("admin_request_list")

    borrow_request = get_object_or_404(BorrowRequest, pk=request_id)
    book = borrow_request.book

    # Safety check: ensure at least one copy is physically available
    if book.available_copies <= 0:
        messages.error(
            request,
            f'Cannot approve: "{book.title}" has no available copies right now.',
        )
        return redirect("admin_request_list")

    # Wrap the state change + transaction creation in a DB atomic block
    with db_transaction.atomic():
        # Mark the borrow request as approved
        borrow_request.status = BorrowRequest.STATUS_APPROVED
        borrow_request.save(update_fields=["status"])

        # Calculate or parse due date
        due_date_str = request.POST.get("due_date")
        if due_date_str:
            naive_dt = datetime.datetime.strptime(due_date_str, "%Y-%m-%dT%H:%M")
            due_date = timezone.make_aware(naive_dt)
        else:
            due_date = timezone.now() + datetime.timedelta(days=7)

        # Create the issue transaction — save() auto-decrements available_copies
        issue = IssueTransaction.objects.create(
            book=book,
            user=borrow_request.user,
            admin=request.user,
            due_date=due_date,
        )

    student = borrow_request.user

    # Notify the student that their request was approved
    Notification.objects.create(
        user=student,
        message=(
            f"Your request for '{book.title}' has been approved. "
            f"Return by {issue.due_date.strftime('%b %d, %Y, %I:%M %p')}."
        ),
    )

    # Sending mail to the user about the approval of the request
    send_mail(
        subject="Your Borrow Request has been Approved",
        message=(
            f"Hi {student.username},\n\n"
            f"Your request for '{book.title}' has been approved.\n"
            f"Please return it by {issue.due_date.strftime('%b %d, %Y, %I:%M %p')}.\n\n"
            f"Thank you,\nSmartLibrary"
        ),
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[student.email],
        fail_silently=True,  # Approve process continues even if email fails
    )

    # Fan-out notification to ALL librarians so they know to physically hand
    # over the book to the student (librarians don't approve but need to
    # be informed to coordinate physical book handover).
    librarian_users = User.objects.filter(role="librarian")
    librarian_notifications = [
        Notification(
            user=librarian,
            message=(
                f"{student.username}'s request for '{book.title}' was approved by admin. "
                f"Due date: {issue.due_date.strftime('%b %d, %Y, %I:%M %p')}."
            ),
        )
        for librarian in librarian_users
    ]
    Notification.objects.bulk_create(librarian_notifications)

    messages.success(
        request,
        f'Request approved. "{book.title}" has been issued to {student.username}.',
    )

    # Fulfill a matching reservation if the student had one NOTIFIED for this book
    matching_reservation = Reservation.objects.filter(
        user=borrow_request.user,
        book=book,
        status=Reservation.STATUS_NOTIFIED,
    ).first()
    if matching_reservation:
        matching_reservation.status = Reservation.STATUS_FULFILLED
        matching_reservation.save(update_fields=["status"])

    return redirect("admin_request_list")


@login_required
@role_required("admin")
def reject_borrow_request(request, request_id):
    """
    Admin rejects a pending borrow request.
    POST only. No IssueTransaction is created and available_copies is unchanged.
    Notifications are sent to the student and all librarians to keep them
    informed of the admin's decision.
    """
    if request.method != "POST":
        return redirect("admin_request_list")

    borrow_request = get_object_or_404(BorrowRequest, pk=request_id)
    book = borrow_request.book
    student = borrow_request.user

    # Mark the request as rejected
    borrow_request.status = BorrowRequest.STATUS_REJECTED
    borrow_request.save(update_fields=["status"])

    # Notify the student of the rejection
    Notification.objects.create(
        user=student,
        message=f"Your request for '{book.title}' has been rejected.",
    )

    # Fan-out notification to ALL librarians to keep them informed of the decision
    librarian_users = User.objects.filter(role="librarian")
    librarian_notifications = [
        Notification(
            user=librarian,
            message=(
                f"{student.username}'s request for '{book.title}' was rejected by admin."
            ),
        )
        for librarian in librarian_users
    ]
    Notification.objects.bulk_create(librarian_notifications)

    messages.info(
        request, f'Request for "{book.title}" by {student.username} has been rejected.'
    )
    return redirect("admin_request_list")


@login_required
def user_notifications(request):
    """
    Displays all notifications for the currently logged-in user (student,
    librarian, or admin), ordered most-recent-first.
    Marks all unread notifications as read when the page is viewed.
    """
    # Fetch only this user's notifications, freshest first
    notifications = Notification.objects.filter(user=request.user).order_by(
        "-created_at"
    )

    # Mark all currently-unread ones as read now that the user has seen them
    notifications.filter(is_read=False).update(is_read=True)

    return render(
        request,
        "books/notifications.html",
        {
            "notifications": notifications,
        },
    )


# ---------------------------------------------------------------------------
# Student Book Return Flow & Admin Return Request Management
# ---------------------------------------------------------------------------


@login_required
def my_borrowed_books(request):
    """
    Displays the logged-in student's currently active (ISSUED) book transaction, if any.
    Finds the active transaction using .first() since a student can hold at most one.
    Also checks if a pending return request already exists for the active transaction.
    """
    active_issue = IssueTransaction.objects.filter(
        user=request.user, status=IssueTransaction.STATUS_ISSUED
    ).first()

    # Check if the student has already submitted a pending return request for this issue
    has_pending_return = (
        ReturnRequest.objects.filter(
            transaction=active_issue, status=ReturnRequest.STATUS_PENDING
        ).exists()
        if active_issue
        else False
    )

    # Check if the active book is currently overdue
    is_overdue = (
        timezone.now().date() > active_issue.due_date.date() if active_issue else False
    )

    return render(
        request,
        "books/my_borrowed_books.html",
        {
            "active_issue": active_issue,
            "has_pending_return": has_pending_return,
            "is_overdue": is_overdue,
        },
    )


@login_required
def request_return(request, transaction_id):
    """
    Allows a student to submit a return request for an active book loan.
    POST only. Replaces direct single-step return with a request-based flow.
    - Filters by transaction_id and user=request.user so students cannot request returns for others.
    - Prevents submission if the book is already returned or if a pending return request exists.
    - Fans out notifications to all Admins (to action the request) and Librarians (for awareness).
    """
    if request.method != "POST":
        return redirect("my_borrowed_books")

    transaction = get_object_or_404(
        IssueTransaction, pk=transaction_id, user=request.user
    )

    if transaction.status == IssueTransaction.STATUS_RETURNED:
        messages.error(
            request, f'"{transaction.book.title}" has already been returned.'
        )
        return redirect("my_borrowed_books")

    # Prevent duplicate pending return requests
    if ReturnRequest.objects.filter(
        transaction=transaction, status=ReturnRequest.STATUS_PENDING
    ).exists():
        messages.error(
            request, "You already have a pending return request for this book."
        )
        return redirect("my_borrowed_books")

    student_reason = request.POST.get("student_reason", "").strip()

    # Create the return request
    ReturnRequest.objects.create(
        transaction=transaction,
        status=ReturnRequest.STATUS_PENDING,
        student_reason=student_reason,
    )

    # Notify all admins so they can review and approve the return
    admin_users = User.objects.filter(role="admin")
    admin_notifications = [
        Notification(
            user=admin,
            message=f"{request.user.username} wants to return '{transaction.book.title}'.",
        )
        for admin in admin_users
    ]
    Notification.objects.bulk_create(admin_notifications)

    # Fan-out notification to ALL librarians so they are informed of the return request
    librarian_users = User.objects.filter(role="librarian")
    librarian_notifications = [
        Notification(
            user=librarian,
            message=f"{request.user.username} has requested to return '{transaction.book.title}'.",
        )
        for librarian in librarian_users
    ]
    Notification.objects.bulk_create(librarian_notifications)

    messages.success(
        request,
        f'Your return request for "{transaction.book.title}" has been submitted. '
        "Please wait for admin approval.",
    )
    return redirect("my_borrowed_books")


@login_required
@role_required("admin")
def admin_return_request_list(request):
    """
    Admin view listing all PENDING return requests.
    Admins review student return requests and approve them to complete the book return process.
    """
    pending_returns = (
        ReturnRequest.objects.filter(status=ReturnRequest.STATUS_PENDING)
        .select_related("transaction__user", "transaction__book")
        .order_by("request_date")
    )

    # Check each pending return for overdue status. If overdue, flag the page
    # (has_any_overdue) so the template shows the column, and set a display
    # reason — the student's own text if given, otherwise an estimated fallback.
    today = timezone.now().date()
    has_any_overdue = False

    for rr in pending_returns:
        due = rr.transaction.due_date.date()
        rr.is_overdue = today > due

        if rr.is_overdue:
            has_any_overdue = True
            estimated_days_late = (today - due).days
            rr.display_reason = (
                rr.student_reason
                if rr.student_reason
                else f"{estimated_days_late} day(s) overdue (estimated)"
            )
        else:
            rr.display_reason = ""
    # for rr in pending_returns:
    #     estimated_days_late = (
    #         timezone.now().date() - rr.transaction.due_date.date()
    #     ).days
    #     rr.is_overdue = estimated_days_late > 0

    return render(
        request,
        "books/admin_return_request_list.html",
        {
            "pending_returns": pending_returns,
            "has_any_overdue": has_any_overdue,
        },
    )


@login_required
@role_required("admin")
def approve_return_request(request, request_id):
    """
    Admin approves a pending return request.
    POST only.
    - Inside db_transaction.atomic(): marks transaction as RETURNED (which increments available_copies
      and sets return_date) and updates return_request.status to APPROVED.
    - Sends notifications to the student and fans out notifications to all librarians.
    """
    if request.method != "POST":
        return redirect("admin_return_request_list")

    return_request = get_object_or_404(ReturnRequest, pk=request_id)
    transaction = return_request.transaction
    book = transaction.book
    student = transaction.user

    FINE_PER_DAY = 25
    FULL_PRICE_THRESHOLD_DAYS = 5

    # Execute transaction mark_as_returned and request approval atomically
    with db_transaction.atomic():
        transaction.mark_as_returned()
        return_request.status = ReturnRequest.STATUS_APPROVED
        return_request.save(update_fields=["status"])

        days_late = (transaction.return_date.date() - transaction.due_date.date()).days

        fine_created = False  # For sending mail

        if days_late > 0:
            if days_late >= FULL_PRICE_THRESHOLD_DAYS:
                fine_amount = book.price
                default_reason = f"{days_late} day(s) overdue - full book price charged"

            else:
                fine_amount = days_late * FINE_PER_DAY
                default_reason = f"{days_late} day(s) overdue"

            final_reason = (
                return_request.student_reason
                if return_request.student_reason
                else default_reason
            )

            fine = Fine.objects.create(
                transaction=transaction,
                amount=fine_amount,
                reason=final_reason,
            )
            fine_created = True

    # Sending Fine Email to students
    if fine_created:
        send_mail(
            subject="Library Fine Notice",
            message=(
                f"Hi {student.username},\n\n"
                f"A fine of ৳{fine.amount} has been charged for '{book.title}'.\n"
                f"Reason: {fine.reason}\n\n"
                f"Please contact the library to settle this fine.\n\n"
                f"Thank you,\nSmartLibrary"
            ),
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[student.email],
            fail_silently=True,
        )

    # Notify student that their return has been confirmed
    Notification.objects.create(
        user=student,
        message=f"Your return for '{book.title}' has been confirmed.",
    )

    # Fan-out notification to ALL librarians so they know the book return is confirmed
    librarian_users = User.objects.filter(role="librarian")
    librarian_notifications = [
        Notification(
            user=librarian,
            message=f"{student.username}'s return of '{book.title}' has been confirmed by admin.",
        )
        for librarian in librarian_users
    ]
    Notification.objects.bulk_create(librarian_notifications)

    messages.success(
        request,
        f'Return request for "{book.title}" by {student.username} approved successfully.',
    )
    return redirect("admin_return_request_list")


@login_required
@role_required("admin")
def student_list(request):
    """
    Admin view listing all students with their reliability status.
    """
    students = User.objects.filter(role="student").order_by("username")
    for student in students:
        student.student_status = get_user_borrow_stats(student)["status"]

    return render(
        request,
        "books/student_list.html",
        {
            "students": students,
        },
    )


@login_required
@role_required("admin")
def student_borrow_history(request, user_id):
    """
    Admin view displaying borrowing history for a specific student.
    """
    student = get_object_or_404(User, pk=user_id, role="student")
    transactions = IssueTransaction.objects.filter(user=student).select_related("book")

    events = []
    for tx in transactions:
        issue_datetime = timezone.make_aware(
            datetime.datetime.combine(tx.issue_date, datetime.time.min)
        )
        events.append(
            {
                "date": issue_datetime,
                "type": "Borrowed",
                "status": "borrowed",
                "book_title": tx.book.title,
                "due_date": tx.due_date,
            }
        )
        if tx.status == IssueTransaction.STATUS_RETURNED and tx.return_date:
            is_overdue = tx.return_date > tx.due_date
            events.append(
                {
                    "date": tx.return_date,
                    "type": "Returned",
                    "status": "returned_overdue" if is_overdue else "returned_on_time",
                    "book_title": tx.book.title,
                    "due_date": tx.due_date,
                }
            )

    events.sort(key=lambda x: x["date"])

    return render(
        request,
        "books/student_borrow_history.html",
        {
            "student": student,
            "events": events,
        },
    )


@login_required
@role_required("admin")
def admin_fine_list(request):
    """
    Admin view listing all library fines.
    Admins can mark unpaid fines as paid from this page.
    """
    fines = (
        Fine.objects.select_related("transaction__user", "transaction__book")
        .all()
        .order_by("-created_at")
    )

    return render(
        request,
        "books/admin_fine_list.html",
        {
            "fines": fines,
        },
    )


@login_required
@role_required("admin")
def mark_fine_paid(request, fine_id):
    """
    Admin marks an unpaid fine as paid.
    POST only. Updates fine status to PAID and redirects back to the fine list.
    """
    if request.method != "POST":
        return redirect("admin_fine_list")

    fine = get_object_or_404(Fine, pk=fine_id)
    fine.status = Fine.STATUS_PAID
    fine.save(update_fields=["status"])

    messages.success(
        request,
        f"Fine of ৳{fine.amount} for {fine.transaction.user.username} marked as paid.",
    )
    return redirect("admin_fine_list")


@login_required
@role_required("student")
def create_reservation(request, book_id):
    # Allows a student to reserve a book if no copies are currently available.
    # POST only. Notifies all admins that a new reservation was made.
    if request.method != "POST":
        return redirect("book_list_user")

    book = get_object_or_404(Book, pk=book_id)

    has_active_book = IssueTransaction.objects.filter(
        user=request.user,
        status=IssueTransaction.STATUS_ISSUED,
    ).exists()

    if has_active_book:
        messages.error(
            request,
            "You currently have a book issued. Please return it before making a reservation.",
        )
        return redirect("book_list_user")

    # Reserving Unavailable Books Only
    if book.available_copies > 0:
        messages.error(
            request, "This book is currently available. Please borrow it instead."
        )
        return redirect("book_list_user")

    # One student = One reserve (rule)
    already_reserved = Reservation.objects.filter(
        user=request.user,
        status__in=[Reservation.STATUS_WAITING, Reservation.STATUS_NOTIFIED],
    ).exists()

    if already_reserved:
        messages.error(request, "You already have an active reservation.")
        return redirect("book_list_user")

    Reservation.objects.create(user=request.user, book=book)

    # Notifying the Admin about Reservation
    admin_users = User.objects.filter(role="admin")
    admin_notifications = [
        Notification(
            user=admin,
            message=f"{request.user.username} has joined the reservation queue for '{book.title}'.",
        )
        for admin in admin_users
    ]
    Notification.objects.bulk_create(admin_notifications)

    messages.success(
        request, f'You have been added to the waiting list for "{book.title}".'
    )
    return redirect("book_list_user")


# ---------------------------------------------------------------------------
# Student: My Reservations
# ---------------------------------------------------------------------------


@login_required
@role_required("student")
def my_reservations(request):
    """
    Displays the student's active reservation (WAITING or NOTIFIED), if any.
    A student can hold at most one active reservation at a time.
    """
    active_reservation = (
        Reservation.objects.filter(
            user=request.user,
            status__in=[Reservation.STATUS_WAITING, Reservation.STATUS_NOTIFIED],
        )
        .select_related("book")
        .first()
    )

    # Compute queue position for WAITING reservations
    queue_position = None
    if active_reservation and active_reservation.status == Reservation.STATUS_WAITING:
        queue_position = (
            Reservation.objects.filter(
                book=active_reservation.book,
                status=Reservation.STATUS_WAITING,
                reservation_date__lt=active_reservation.reservation_date,
            ).count()
            + 1
        )

    return render(
        request,
        "books/my_reservations.html",
        {
            "reservation": active_reservation,
            "queue_position": queue_position,
        },
    )


# ---------------------------------------------------------------------------
# Admin: Reservation Queue Management
# ---------------------------------------------------------------------------


@login_required
@role_required("admin")
def admin_reservation_list(request):
    """
    Admin view listing all WAITING reservations grouped by book,
    and all NOTIFIED reservations with their countdown status.
    For each reservation, attaches the student's reliability badge.
    """
    waiting = (
        Reservation.objects.filter(status=Reservation.STATUS_WAITING)
        .select_related("user", "book")
        .order_by("book", "reservation_date")
    )

    for res in waiting:
        res.student_status = get_user_borrow_stats(res.user)["status"]

    notified = (
        Reservation.objects.filter(status=Reservation.STATUS_NOTIFIED)
        .select_related("user", "book")
        .order_by("reservation_date")
    )

    for res in notified:
        res.student_status = get_user_borrow_stats(res.user)["status"]
        res.hours_elapsed = round(res.hours_since_notified() or 0, 1)
        total_deadline = res.deadline_hours + (res.deadline_minutes / 60.0)
        res.hours_remaining = round(
            max(total_deadline - (res.hours_since_notified() or 0), 0), 1
        )
        res.expired = res.is_expired()

    return render(
        request,
        "books/admin_reservation_list.html",
        {
            "waiting": waiting,
            "notified": notified,
        },
    )


@login_required
@role_required("admin")
def notify_reservation(request, reservation_id):
    """
    Admin notifies a student that their reserved book is available.
    POST only. Sets status=NOTIFIED, records notified_at timestamp,
    applies the custom deadline_hours, and fans out notifications to
    the student and all librarians.
    """
    if request.method != "POST":
        return redirect("admin_reservation_list")

    reservation = get_object_or_404(Reservation, pk=reservation_id)

    # Read admin-specified deadline (hours and minutes)
    try:
        deadline_hours = int(request.POST.get("deadline_hours", 24))
    except (ValueError, TypeError):
        deadline_hours = 24

    try:
        deadline_minutes = int(request.POST.get("deadline_minutes", 0))
    except (ValueError, TypeError):
        deadline_minutes = 0

    if deadline_hours == 0 and deadline_minutes == 0:
        messages.error(request, "Please set a deadline greater than 0")
        return redirect("admin_reservation_list")

    reservation.status = Reservation.STATUS_NOTIFIED
    reservation.notified_at = timezone.now()
    reservation.deadline_hours = deadline_hours
    reservation.deadline_minutes = deadline_minutes
    reservation.save(
        update_fields=["status", "notified_at", "deadline_hours", "deadline_minutes"]
    )

    student = reservation.user
    book = reservation.book

    # Build deadline string for messages
    deadline_parts = []
    if deadline_hours > 0:
        deadline_parts.append(
            f"{deadline_hours} hour{'s' if deadline_hours != 1 else ''}"
        )
    if deadline_minutes > 0:
        deadline_parts.append(
            f"{deadline_minutes} minute{'s' if deadline_minutes != 1 else ''}"
        )
    deadline_str = " and ".join(deadline_parts)

    # Notify the student
    Notification.objects.create(
        user=student,
        message=(
            f"'{book.title}' is available! "
            f"You have {deadline_str} to submit a borrow request."
        ),
    )

    # Notify the student via email as well
    send_mail(
        subject=f"'{book.title}' is now available!",
        message=(
            f"Hi {student.username},\n\n"
            f"The book '{book.title}' you reserved is now available.\n"
            f"You have {deadline_str} to submit a borrow request.\n\n"
            f"Thank you,\nSmartLibrary"
        ),
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[student.email],
        fail_silently=True,
    )

    # Fan-out notification to ALL librarians
    librarian_users = User.objects.filter(role="librarian")
    librarian_notifications = [
        Notification(
            user=librarian,
            message=(
                f"{student.username} has been notified for '{book.title}', "
                f"prepare to issue it."
            ),
        )
        for librarian in librarian_users
    ]
    Notification.objects.bulk_create(librarian_notifications)

    messages.success(
        request,
        f'{student.username} has been notified for "{book.title}" '
        f"with a {deadline_str} deadline.",
    )
    return redirect("admin_reservation_list")


@login_required
@role_required("admin")
def expire_reservation(request, reservation_id):
    """
    Admin manually expires a reservation whose deadline has passed.
    POST only. Sets status=EXPIRED and redirects back to the reservation list.
    Does NOT auto-notify the next student — admin picks manually per the
    existing admin-discretion design.
    """
    if request.method != "POST":
        return redirect("admin_reservation_list")

    reservation = get_object_or_404(Reservation, pk=reservation_id)
    reservation.status = Reservation.STATUS_EXPIRED
    reservation.save(update_fields=["status"])

    messages.info(
        request,
        f'Reservation for "{reservation.book.title}" by '
        f"{reservation.user.username} has been expired.",
    )
    return redirect("admin_reservation_list")


# ---------------------------------------------------------------------------
# Chatbot
# ---------------------------------------------------------------------------


def get_bot_response(message, user):
    """
    Database-first chatbot response helper.

    Checks the message against known keywords and queries the database to
    build a personalised answer. Falls back to Gemini for all other queries.

    Args:
        message (str): The raw message text from the student.
        user: The authenticated Django user instance.

    Returns:
        str: A plain-text response to display in the chatbot widget.
    """
    msg = message.lower()

    # --- Fines ---
    if "fine" in msg:
        total = (
            Fine.objects.filter(
                transaction__user=user, status=Fine.STATUS_UNPAID
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        if total:
            return f"You have ৳{total:.2f} in unpaid fines. Please clear them at the library counter."
        return "You have no outstanding fines. "

    # --- Borrowed books ---
    if "borrowed" in msg or "my book" in msg:
        transaction = IssueTransaction.objects.filter(
            user=user, status=IssueTransaction.STATUS_ISSUED
        ).first()
        if transaction:
            due = transaction.due_date.strftime("%d %b %Y, %I:%M %p")
            return (
                f'You currently have "{transaction.book.title}" borrowed. '
                f"It is due on {due}."
            )
        return "You have no books currently borrowed."

    # --- Reservations ---
    if "reservation" in msg:
        reservation = Reservation.objects.filter(
            user=user,
            status__in=[Reservation.STATUS_WAITING, Reservation.STATUS_NOTIFIED],
        ).first()
        if reservation:
            status_label = (
                "Waiting" if reservation.status == Reservation.STATUS_WAITING else "Notified"
            )
            return (
                f'Your reservation for "{reservation.book.title}" is currently '
                f"{status_label}."
            )
        return "You have no active reservations."

    # --- Available books ---
    if "available" in msg:
        available_books = Book.objects.filter(available_copies__gt=0)[:5]
        if available_books:
            titles = ", ".join(f'"{b.title}"' for b in available_books)
            return f"Here are some available books: {titles}."
        return "Sorry, no books are currently available."

    # --- Library hours ---
    if any(kw in msg for kw in ("hours", "open", "timing")):
        return (
            "Library hours: Mon\u2013Fri 8:00\u202fAM\u2013 10:00\u202fPM, "
            "Sat\u2013Sun 10:00\u202fAM\u2013 6:00\u202fPM."
        )

    # --- Gemini fallback ---
    try:
        prompt = (
            "You are a helpful university library assistant. "
            "Answer the student's question concisely and politely.\n\n"
            f"Student: {message}"
        )
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Gemini API error: %s", exc, exc_info=True)
        return (
            "I'm sorry, I couldn't process your request right now. "
            "Please try again or visit the library desk for assistance."
        )


@login_required
def chatbot_view(request):
    """
    Serves the floating chatbot widget's API endpoint.

    GET  — Returns the authenticated student's full chat history as JSON so
           the widget can render previous messages on first open.
    POST — Accepts a 'message' field, generates a bot response via
           get_bot_response(), persists the exchange in ChatMessage, and
           returns the response as JSON.

    Does not render an HTML page; all output is JSON for fetch() consumption.
    """
    if request.method == "GET":
        history = ChatMessage.objects.filter(user=request.user).values(
            "user_message", "bot_response"
        )
        return JsonResponse({"history": list(history)})

    # POST
    user_message = request.POST.get("message", "").strip()
    if not user_message:
        return JsonResponse({"error": "Empty message."}, status=400)

    bot_response = get_bot_response(user_message, request.user)
    ChatMessage.objects.create(
        user=request.user,
        user_message=user_message,
        bot_response=bot_response,
    )
    return JsonResponse({"response": bot_response})
