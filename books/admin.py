from django.contrib import admin
from .models import Book, BorrowRequest, IssueTransaction, Notification


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('book_id', 'title', 'author', 'isbn', 'category', 'available_copies', 'total_copies')
    search_fields = ('title', 'author', 'isbn', 'category')
    list_filter = ('category',)


@admin.register(BorrowRequest)
class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'book', 'status', 'request_date')
    list_filter = ('status',)
    search_fields = ('user__username', 'book__title')
    readonly_fields = ('request_date',)


@admin.register(IssueTransaction)
class IssueTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'user', 'book', 'admin', 'status', 'issue_date', 'due_date', 'return_date')
    list_filter = ('status',)
    search_fields = ('user__username', 'book__title')
    readonly_fields = ('issue_date',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('user__username', 'message')
    readonly_fields = ('created_at',)
