from django.contrib import admin
from .models import (
    Book,
    BorrowRequest,
    IssueTransaction,
    Notification,
    Fine,
    Reservation,
)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = (
        "book_id",
        "title",
        "author",
        "isbn",
        "category",
        "available_copies",
        "total_copies",
    )
    search_fields = ("title", "author", "isbn", "category")
    list_filter = ("category",)


@admin.register(BorrowRequest)
class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ("pk", "user", "book", "status", "request_date")
    list_filter = ("status",)
    search_fields = ("user__username", "book__title")
    readonly_fields = ("request_date",)


@admin.register(IssueTransaction)
class IssueTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_id",
        "user",
        "book",
        "admin",
        "status",
        "issue_date",
        "due_date",
        "return_date",
    )
    list_filter = ("status",)
    search_fields = ("user__username", "book__title")
    readonly_fields = ("issue_date",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("pk", "user", "message", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("user__username", "message")
    readonly_fields = ("created_at",)


@admin.register(Fine)
class FineAdmin(admin.ModelAdmin):
    list_display = ("pk", "get_user", "transaction", "amount", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = (
        "transaction__user__username",
        "transaction__book__title",
        "amount",
    )
    readonly_fields = ("created_at",)

    @admin.display(description="User", ordering="transaction__user")
    def get_user(self, obj):
        return obj.transaction.user


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "user",
        "book",
        "status",
        "reservation_date",
        "notified_at",
        "is_expired_status",
    )
    list_filter = ("user", "book", "status", "reservation_date")
    search_fields = ("user__username", "book__title")
    readonly_fields = ("reservation_date",)

    @admin.display(description="Expired?", boolean=True)
    def is_expired_status(self, obj):
        return obj.is_expired()
