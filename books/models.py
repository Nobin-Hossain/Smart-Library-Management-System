from django.db import models
from django.conf import settings
from django.utils import timezone
import datetime


class Book(models.Model):
    book_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    isbn = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=100)
    publisher = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["title"]
        verbose_name = "Book"
        verbose_name_plural = "Books"

    def __str__(self):
        return f"{self.title} by {self.author}"

    def borrowed_copies(self):
        """Returns the number of copies currently borrowed."""
        return self.total_copies - self.available_copies


class BorrowRequest(models.Model):
    """
    Represents a student's request to borrow a specific book.
    Admins review PENDING requests and either approve or reject them.
    """

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="borrow_requests",
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="borrow_requests",
    )
    request_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    class Meta:
        ordering = ["-request_date"]
        verbose_name = "Borrow Request"
        verbose_name_plural = "Borrow Requests"

    def __str__(self):
        return f"{self.user.username} → {self.book.title} [{self.status}]"


class IssueTransaction(models.Model):
    """
    Created when an admin approves a BorrowRequest.
    On first save(), decrements book.available_copies by 1.
    mark_as_returned() sets status=RETURNED and increments available_copies.
    """

    STATUS_ISSUED = "ISSUED"
    STATUS_RETURNED = "RETURNED"

    STATUS_CHOICES = [
        (STATUS_ISSUED, "Issued"),
        (STATUS_RETURNED, "Returned"),
    ]

    transaction_id = models.AutoField(primary_key=True)
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="issue_transactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="issue_transactions",
    )
    # The admin who approved the borrow request
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="approved_issues",
    )
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateTimeField()
    return_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ISSUED,
    )

    class Meta:
        ordering = ["-issue_date"]
        verbose_name = "Issue Transaction"
        verbose_name_plural = "Issue Transactions"

    def save(self, *args, **kwargs):
        """
        On first creation only (no pk yet), decrement book.available_copies
        by 1 to reflect the copy being physically taken from the shelf.
        """
        is_new = self._state.adding  # True when the object has no pk yet
        super().save(*args, **kwargs)
        if is_new:
            # Decrement available copies atomically to avoid race conditions
            Book.objects.filter(pk=self.book_id).update(
                available_copies=models.F("available_copies") - 1
            )
            # Refresh the in-memory book instance so callers see updated value
            self.book.refresh_from_db()

    def mark_as_returned(self):
        """
        Marks this transaction as RETURNED, records today's return date,
        and increments book.available_copies by 1.
        """
        self.status = self.STATUS_RETURNED
        self.return_date = timezone.now()
        self.save(update_fields=["status", "return_date"])
        # Increment available copies back
        Book.objects.filter(pk=self.book_id).update(
            available_copies=models.F("available_copies") + 1
        )
        self.book.refresh_from_db()

    def __str__(self):
        return f"Transaction #{self.transaction_id} — {self.user.username} / {self.book.title}"


class ReturnRequest(models.Model):
    """
    Represents a student's request to return a currently borrowed book.
    Admins review PENDING return requests and approve them, which triggers mark_as_returned().
    """

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
    ]

    transaction = models.ForeignKey(
        IssueTransaction,
        on_delete=models.CASCADE,
        related_name="return_requests",
    )
    request_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    class Meta:
        ordering = ["-request_date"]
        verbose_name = "Return Request"
        verbose_name_plural = "Return Requests"

    def __str__(self):
        return f"Return Request for Transaction #{self.transaction.transaction_id} — {self.transaction.user.username} / {self.transaction.book.title} [{self.status}]"


class Notification(models.Model):
    """
    In-app notification for a specific user.
    Used to inform students of approval/rejection and librarians of
    any admin decision (so they know which books to physically handle).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        read_status = "read" if self.is_read else "unread"
        return f"Notification for {self.user.username} [{read_status}]: {self.message[:50]}"
