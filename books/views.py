from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q, F
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.db import transaction as db_transaction
import datetime

from accounts.decorators import role_required
from .models import Book, BorrowRequest, IssueTransaction, Notification, ReturnRequest
from .forms import BookForm

User = get_user_model()


# ---------------------------------------------------------------------------
# Librarian Dashboard
# ---------------------------------------------------------------------------

@login_required
@role_required('librarian', 'admin')
def librarian_dashboard(request):
    """
    Librarian dashboard view.
    Displays system statistics (total users, available books, borrowed books)
    and a searchable / filterable book management table.
    """
    # --- Search ---
    query = request.GET.get('q', '').strip()
    books = Book.objects.all()
    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query) |
            Q(category__icontains=query) |
            Q(isbn__icontains=query)
        )

    # --- Statistics ---
    all_users = User.objects.filter(role='student').order_by('-date_joined')
    total_users = all_users.count()
    total_available_books = Book.objects.aggregate(
        total=Sum('available_copies')
    )['total'] or 0
    total_borrowed_books = sum(
        book.total_copies - book.available_copies
        for book in Book.objects.all()
    )

    context = {
        'books': books,
        'query': query,
        'total_users': total_users,
        'all_users': all_users,
        'total_available_books': total_available_books,
        'total_borrowed_books': total_borrowed_books,
    }
    return render(request, 'accounts/dashboard_librarian.html', context)


# ---------------------------------------------------------------------------
# Book CRUD
# ---------------------------------------------------------------------------

@login_required
@role_required('librarian', 'admin')
def book_create(request):
    """
    View to add a new book to the catalog.
    Only librarians and admins may access this view.
    """
    if request.method == 'POST':
        form = BookForm(request.POST)
        if form.is_valid():
            book = form.save()
            messages.success(request, f'Book "{book.title}" was added successfully.')
            return redirect('librarian_dashboard')
        else:
            messages.error(request, 'Please fix the errors below and try again.')
    else:
        form = BookForm()

    return render(request, 'books/book_form.html', {
        'form': form,
        'form_title': 'Add New Book',
        'submit_label': 'Add Book',
    })


@login_required
@role_required('librarian', 'admin')
def book_update(request, pk):
    """
    View to edit an existing book entry.
    Only librarians and admins may access this view.
    """
    book = get_object_or_404(Book, pk=pk)

    if request.method == 'POST':
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, f'Book "{book.title}" was updated successfully.')
            return redirect('librarian_dashboard')
        else:
            messages.error(request, 'Please fix the errors below and try again.')
    else:
        form = BookForm(instance=book)

    return render(request, 'books/book_form.html', {
        'form': form,
        'form_title': f'Edit Book: {book.title}',
        'submit_label': 'Save Changes',
        'book': book,
    })


@login_required
@role_required('librarian', 'admin')
def book_delete(request, pk):
    """
    View to delete a book with a confirmation step.
    Only librarians and admins may access this view.
    """
    book = get_object_or_404(Book, pk=pk)

    if request.method == 'POST':
        title = book.title
        book.delete()
        messages.success(request, f'Book "{title}" was deleted successfully.')
        return redirect('librarian_dashboard')

    return render(request, 'books/book_confirm_delete.html', {'book': book})


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
    if getattr(request.user, 'role', None) != 'student':
        return HttpResponseForbidden("Access denied. This view is reserved for students.")

    query = request.GET.get('q', '').strip()
    books = Book.objects.all().order_by('book_id')

    # Search filter using Q objects (case-insensitive partial match on title, author, category)
    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query) |
            Q(category__icontains=query)
        )

    # Paginate list: 10 books per page
    paginator = Paginator(books, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'books': page_obj.object_list,
        'query': query,
    }
    return render(request, 'books/book_list_user.html', context)


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
    if request.user.role != 'student':
        messages.error(request, "Only students can request to borrow books.")
        return redirect('book_list_user')

    if request.method != 'POST':
        return redirect('book_list_user')

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
            "You already have a book issued. Please return it before requesting another."
        )
        return redirect('book_list_user')

    # Check (b): does the student already have a pending borrow request?
    already_pending = BorrowRequest.objects.filter(
        user=request.user,
        status=BorrowRequest.STATUS_PENDING,
    ).exists()

    if already_pending:
        messages.error(
            request,
            "You already have a pending borrow request. Please wait for it to be reviewed."
        )
        return redirect('book_list_user')

    # All checks passed — create the borrow request
    BorrowRequest.objects.create(
        user=request.user,
        book=book,
        status=BorrowRequest.STATUS_PENDING,
    )

    # Notify ALL admins so they are aware of the new request
    admin_users = User.objects.filter(role='admin')
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
        'Please wait for admin approval.'
    )
    return redirect('book_list_user')


def get_user_borrow_stats(user):
    """
    Calculates borrow statistics for a given user.
    Returns a dictionary containing the total borrow count and a reliability status string.
    """
    total_borrows = IssueTransaction.objects.filter(user=user).count()
    if total_borrows == 0:
        status = 'New'
    else:
        overdue_count = IssueTransaction.objects.filter(
            user=user,
            status=IssueTransaction.STATUS_RETURNED,
            return_date__gt=F('due_date')
        ).count()
        if overdue_count == 0:
            status = 'Reliable'
        elif 1 <= overdue_count <= 2:
            status = 'Caution'
        else:
            status = 'Risky'
    return {'total_borrows': total_borrows, 'status': status}


@login_required
@role_required('admin')
def admin_request_list(request):
    """
    Admin view listing all PENDING borrow requests.
    Admins can approve or reject each request from this page.
    """
    # Fetch all pending requests with related user and book data in one query
    pending_requests = BorrowRequest.objects.filter(
        status=BorrowRequest.STATUS_PENDING
    ).select_related('user', 'book').order_by('request_date')

    for req in pending_requests:
        req.student_status = get_user_borrow_stats(req.user)['status']

    return render(request, 'books/admin_request_list.html', {
        'pending_requests': pending_requests,
    })


@login_required
@role_required('admin')
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
    if request.method != 'POST':
        return redirect('admin_request_list')

    borrow_request = get_object_or_404(BorrowRequest, pk=request_id)
    book = borrow_request.book

    # Safety check: ensure at least one copy is physically available
    if book.available_copies <= 0:
        messages.error(
            request,
            f'Cannot approve: "{book.title}" has no available copies right now.'
        )
        return redirect('admin_request_list')

    # Wrap the state change + transaction creation in a DB atomic block
    with db_transaction.atomic():
        # Mark the borrow request as approved
        borrow_request.status = BorrowRequest.STATUS_APPROVED
        borrow_request.save(update_fields=['status'])

        # Calculate due date: issue_date (today) + 7 days
        today = datetime.date.today()
        due_date = today + datetime.timedelta(days=7)

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
            f"Return by {issue.due_date.strftime('%b %d, %Y')}."
        ),
    )

    # Fan-out notification to ALL librarians so they know to physically hand
    # over the book to the student (librarians don't approve but need to
    # be informed to coordinate physical book handover).
    librarian_users = User.objects.filter(role='librarian')
    librarian_notifications = [
        Notification(
            user=librarian,
            message=(
                f"{student.username}'s request for '{book.title}' was approved by admin. "
                f"Due date: {issue.due_date.strftime('%b %d, %Y')}."
            ),
        )
        for librarian in librarian_users
    ]
    Notification.objects.bulk_create(librarian_notifications)

    messages.success(
        request,
        f'Request approved. "{book.title}" has been issued to {student.username}.'
    )
    return redirect('admin_request_list')


@login_required
@role_required('admin')
def reject_borrow_request(request, request_id):
    """
    Admin rejects a pending borrow request.
    POST only. No IssueTransaction is created and available_copies is unchanged.
    Notifications are sent to the student and all librarians to keep them
    informed of the admin's decision.
    """
    if request.method != 'POST':
        return redirect('admin_request_list')

    borrow_request = get_object_or_404(BorrowRequest, pk=request_id)
    book = borrow_request.book
    student = borrow_request.user

    # Mark the request as rejected
    borrow_request.status = BorrowRequest.STATUS_REJECTED
    borrow_request.save(update_fields=['status'])

    # Notify the student of the rejection
    Notification.objects.create(
        user=student,
        message=f"Your request for '{book.title}' has been rejected.",
    )

    # Fan-out notification to ALL librarians to keep them informed of the decision
    librarian_users = User.objects.filter(role='librarian')
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
        request,
        f'Request for "{book.title}" by {student.username} has been rejected.'
    )
    return redirect('admin_request_list')


@login_required
def user_notifications(request):
    """
    Displays all notifications for the currently logged-in user (student,
    librarian, or admin), ordered most-recent-first.
    Marks all unread notifications as read when the page is viewed.
    """
    # Fetch only this user's notifications, freshest first
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')

    # Mark all currently-unread ones as read now that the user has seen them
    notifications.filter(is_read=False).update(is_read=True)

    return render(request, 'books/notifications.html', {
        'notifications': notifications,
    })


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
        user=request.user,
        status=IssueTransaction.STATUS_ISSUED
    ).first()

    # Check if the student has already submitted a pending return request for this issue
    has_pending_return = ReturnRequest.objects.filter(
        transaction=active_issue,
        status=ReturnRequest.STATUS_PENDING
    ).exists() if active_issue else False

    return render(request, 'books/my_borrowed_books.html', {
        'active_issue': active_issue,
        'has_pending_return': has_pending_return,
    })


@login_required
def request_return(request, transaction_id):
    """
    Allows a student to submit a return request for an active book loan.
    POST only. Replaces direct single-step return with a request-based flow.
    - Filters by transaction_id and user=request.user so students cannot request returns for others.
    - Prevents submission if the book is already returned or if a pending return request exists.
    - Fans out notifications to all Admins (to action the request) and Librarians (for awareness).
    """
    if request.method != 'POST':
        return redirect('my_borrowed_books')

    transaction = get_object_or_404(
        IssueTransaction,
        pk=transaction_id,
        user=request.user
    )

    if transaction.status == IssueTransaction.STATUS_RETURNED:
        messages.error(request, f'"{transaction.book.title}" has already been returned.')
        return redirect('my_borrowed_books')

    # Prevent duplicate pending return requests
    if ReturnRequest.objects.filter(transaction=transaction, status=ReturnRequest.STATUS_PENDING).exists():
        messages.error(request, "You already have a pending return request for this book.")
        return redirect('my_borrowed_books')

    # Create the return request
    ReturnRequest.objects.create(
        transaction=transaction,
        status=ReturnRequest.STATUS_PENDING
    )

    # Notify all admins so they can review and approve the return
    admin_users = User.objects.filter(role='admin')
    admin_notifications = [
        Notification(
            user=admin,
            message=f"{request.user.username} wants to return '{transaction.book.title}'.",
        )
        for admin in admin_users
    ]
    Notification.objects.bulk_create(admin_notifications)

    # Fan-out notification to ALL librarians so they are informed of the return request
    librarian_users = User.objects.filter(role='librarian')
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
        'Please wait for admin approval.'
    )
    return redirect('my_borrowed_books')


@login_required
@role_required('admin')
def admin_return_request_list(request):
    """
    Admin view listing all PENDING return requests.
    Admins review student return requests and approve them to complete the book return process.
    """
    pending_returns = ReturnRequest.objects.filter(
        status=ReturnRequest.STATUS_PENDING
    ).select_related('transaction__user', 'transaction__book').order_by('request_date')

    return render(request, 'books/admin_return_request_list.html', {
        'pending_returns': pending_returns,
    })


@login_required
@role_required('admin')
def approve_return_request(request, request_id):
    """
    Admin approves a pending return request.
    POST only.
    - Inside db_transaction.atomic(): marks transaction as RETURNED (which increments available_copies
      and sets return_date) and updates return_request.status to APPROVED.
    - Sends notifications to the student and fans out notifications to all librarians.
    """
    if request.method != 'POST':
        return redirect('admin_return_request_list')

    return_request = get_object_or_404(ReturnRequest, pk=request_id)
    transaction = return_request.transaction
    book = transaction.book
    student = transaction.user

    # Execute transaction mark_as_returned and request approval atomically
    with db_transaction.atomic():
        transaction.mark_as_returned()
        return_request.status = ReturnRequest.STATUS_APPROVED
        return_request.save(update_fields=['status'])

    # Notify student that their return has been confirmed
    Notification.objects.create(
        user=student,
        message=f"Your return for '{book.title}' has been confirmed.",
    )

    # Fan-out notification to ALL librarians so they know the book return is confirmed
    librarian_users = User.objects.filter(role='librarian')
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
        f'Return request for "{book.title}" by {student.username} approved successfully.'
    )
    return redirect('admin_return_request_list')


@login_required
@role_required('admin')
def student_list(request):
    """
    Admin view listing all students with their reliability status.
    """
    students = User.objects.filter(role='student').order_by('username')
    for student in students:
        student.student_status = get_user_borrow_stats(student)['status']
    
    return render(request, 'books/student_list.html', {
        'students': students,
    })


@login_required
@role_required('admin')
def student_borrow_history(request, user_id):
    """
    Admin view displaying borrowing history for a specific student.
    """
    student = get_object_or_404(User, pk=user_id, role='student')
    transactions = IssueTransaction.objects.filter(user=student).select_related('book')
    
    events = []
    for tx in transactions:
        events.append({
            'date': tx.issue_date,
            'type': 'Borrowed',
            'status': 'borrowed',
            'book_title': tx.book.title,
            'due_date': tx.due_date,
        })
        if tx.status == IssueTransaction.STATUS_RETURNED and tx.return_date:
            is_overdue = tx.return_date > tx.due_date
            events.append({
                'date': tx.return_date,
                'type': 'Returned',
                'status': 'returned_overdue' if is_overdue else 'returned_on_time',
                'book_title': tx.book.title,
                'due_date': tx.due_date,
            })
            
    events.sort(key=lambda x: x['date'])
    
    return render(request, 'books/student_borrow_history.html', {
        'student': student,
        'events': events,
    })


