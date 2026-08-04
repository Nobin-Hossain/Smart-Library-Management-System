from django.urls import path
from . import views

urlpatterns = [
    # Librarian dashboard (book management hub)
    path('dashboard/librarian/', views.librarian_dashboard, name='librarian_dashboard'),

    # Book CRUD
    path('books/add/', views.book_create, name='book_create'),
    path('books/<int:pk>/edit/', views.book_update, name='book_update'),
    path('books/<int:pk>/delete/', views.book_delete, name='book_delete'),

    # Student catalog view
    path('books/catalog/', views.book_list_user, name='book_list_user'),

    # Borrow Request Workflow
    path('books/<int:book_id>/borrow/', views.create_borrow_request, name='create_borrow_request'),
    # Borrow Request Workflow (prefix must NOT start with 'admin/' — that is
    # reserved for Django's built-in admin site and would be swallowed by its
    # catch-all URL pattern before our routes ever matched).
    path('borrow-requests/', views.admin_request_list, name='admin_request_list'),
    path('borrow-requests/<int:request_id>/approve/', views.approve_borrow_request, name='approve_borrow_request'),
    path('borrow-requests/<int:request_id>/reject/', views.reject_borrow_request, name='reject_borrow_request'),

    # Notifications (works for student, librarian, and admin)
    path('notifications/', views.user_notifications, name='user_notifications'),
]
