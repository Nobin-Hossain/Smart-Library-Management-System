from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.contrib.auth import get_user_model

from accounts.decorators import role_required
from .models import Book
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

from django.core.paginator import Paginator
from django.http import HttpResponseForbidden

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

