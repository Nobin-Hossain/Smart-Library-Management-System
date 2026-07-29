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
]

