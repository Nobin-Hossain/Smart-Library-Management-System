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

    student_reason = models.CharField(max_length=255, blank=True)

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


# For managing Fines


class Fine(models.Model):

    STATUS_UNPAID = "UNPAID"
    STATUS_PAID = "PAID"

    STATUS_CHOICES = [
        (STATUS_UNPAID, "Unpaid"),
        (STATUS_PAID, "Paid"),
    ]

    transaction = models.ForeignKey(
        IssueTransaction,
        on_delete=models.CASCADE,
        related_name="fines",
    )

    amount = models.DecimalField(max_digits=8, decimal_places=2)
    reason = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UNPAID,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Fine"
        verbose_name_plural = "Fines"

    def __str__(self):
        return (
            f"Fine ৳{self.amount} for {self.transaction.user.username} [{self.status}]"
        )


# Book Reservation


class Reservation(models.Model):
    STATUS_WAITING = "WAITING"
    STATUS_NOTIFIED = "NOTIFIED"
    STATUS_FULFILLED = "FULFILLED"
    STATUS_EXPIRED = "EXPIRED"

    STATUS_CHOICES = [
        (STATUS_WAITING, "Waiting"),
        (STATUS_NOTIFIED, "Notified"),
        (STATUS_FULFILLED, "Fulfilled"),
        (STATUS_EXPIRED, "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservations",
    )

    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="reservations",
    )

    # Sets when Admin notifies the student - starts the 24-hour window
    reservation_date = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_WAITING,
    )

    # Sets when Admin notifies this student - starts the countdown
    notified_at = models.DateTimeField(null=True, blank=True)

    # Admin sets deadline for student to fulfill the reservation
    deadline_hours = models.PositiveIntegerField(default=24)
    deadline_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["reservation_date"]  # queue order = oldest first
        verbose_name = "Reservation"
        verbose_name_plural = "Reservations"

    def __str__(self):
        return f"{self.user.username} - {self.book.title} [{self.status}]"

    def hours_since_notified(self):
        # Returns hours elapsed since notification, None if not notified
        if not self.notified_at:
            return None
        return (timezone.now() - self.notified_at).total_seconds() / 3600

    def is_expired(self):
        # True if notified more than deadline and still not fulfilled
        hours = self.hours_since_notified()
        if hours is None:
            return False
        total_deadline_hours = self.deadline_hours + (self.deadline_minutes / 60.0)
        return hours > total_deadline_hours


# Chatbot


class ChatMessage(models.Model):
    """
    Stores a single chatbot exchange (one user message + one bot response)
    for a given student. Used to populate the floating widget with persistent
    history across page navigations.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    user_message = models.TextField()
    bot_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"

    def __str__(self):
        return (
            f"[{self.created_at:%Y-%m-%d %H:%M}] "
            f"{self.user.username}: {self.user_message[:50]}"
        )
