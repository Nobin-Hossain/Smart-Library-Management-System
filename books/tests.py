from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from books.models import Book

User = get_user_model()

class BookListUserViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student_user = User.objects.create_user(
            username='student1',
            email='student@example.com',
            password='password123',
            role='student'
        )
        self.librarian_user = User.objects.create_user(
            username='librarian1',
            email='librarian@example.com',
            password='password123',
            role='librarian'
        )
        self.admin_user = User.objects.create_user(
            username='admin1',
            email='admin@example.com',
            password='password123',
            role='admin'
        )

        # Create sample books
        for i in range(15):
            Book.objects.create(
                title=f'Book {i+1}',
                author=f'Author {i%3}',
                isbn=f'123456789012{i:02d}',
                category='Fiction' if i % 2 == 0 else 'Science',
                publisher='Publisher X',
                price=19.99,
                total_copies=5,
                available_copies=5
            )

        self.url = reverse('book_list_user')

    def test_unauthenticated_user_redirected(self):
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_student_access_allowed(self):
        self.client.login(username='student1', password='password123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/book_list_user.html')
        self.assertEqual(len(response.context['books']), 10)  # Pagination limit 10

    def test_librarian_access_forbidden(self):
        self.client.login(username='librarian1', password='password123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_admin_access_forbidden(self):
        self.client.login(username='admin1', password='password123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_search_functionality(self):
        self.client.login(username='student1', password='password123')
        response = self.client.get(self.url, {'q': 'Book 1'})
        self.assertEqual(response.status_code, 200)
        # Matches 'Book 1', 'Book 10', 'Book 11', 'Book 12', 'Book 13', 'Book 14', 'Book 15'
        self.assertTrue(len(response.context['books']) > 0)
        for book in response.context['books']:
            self.assertIn('1', book.title)


class BookReturnFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.student1 = User.objects.create_user(
            username='student1',
            email='student1@example.com',
            password='password123',
            role='student'
        )
        self.student2 = User.objects.create_user(
            username='student2',
            email='student2@example.com',
            password='password123',
            role='student'
        )
        self.librarian = User.objects.create_user(
            username='librarian1',
            email='librarian1@example.com',
            password='password123',
            role='librarian'
        )
        self.admin = User.objects.create_user(
            username='admin1',
            email='admin@example.com',
            password='password123',
            role='admin'
        )
        self.book = Book.objects.create(
            title='Clean Code',
            author='Robert C. Martin',
            isbn='9780132350884',
            category='Software',
            publisher='Prentice Hall',
            price=45.00,
            total_copies=3,
            available_copies=3
        )
        from django.utils import timezone
        import datetime
        self.today = timezone.now().date()
        from books.models import IssueTransaction, ReturnRequest, Notification
        self.issue_tx = IssueTransaction.objects.create(
            book=self.book,
            user=self.student1,
            admin=self.admin,
            due_date=self.today + datetime.timedelta(days=7)
        )

    def test_my_borrowed_books_view(self):
        self.client.login(username='student1', password='password123')
        url = reverse('my_borrowed_books')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_issue'], self.issue_tx)
        self.assertFalse(response.context['has_pending_return'])

    def test_my_borrowed_books_none_when_returned(self):
        self.issue_tx.mark_as_returned()
        self.client.login(username='student1', password='password123')
        url = reverse('my_borrowed_books')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['active_issue'])

    def test_request_return_get_redirects(self):
        self.client.login(username='student1', password='password123')
        url = reverse('request_return', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.get(url)
        self.assertRedirects(response, reverse('my_borrowed_books'))

    def test_request_return_other_user_404(self):
        # student2 trying to return student1's book
        self.client.login(username='student2', password='password123')
        url = reverse('request_return', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_request_return_post_success(self):
        from books.models import ReturnRequest, Notification
        self.client.login(username='student1', password='password123')
        url = reverse('request_return', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('my_borrowed_books'))

        return_req = ReturnRequest.objects.filter(transaction=self.issue_tx).first()
        self.assertIsNotNone(return_req)
        self.assertEqual(return_req.status, ReturnRequest.STATUS_PENDING)

        # Check notifications sent to admin & librarian
        admin_notif = Notification.objects.filter(user=self.admin).first()
        librarian_notif = Notification.objects.filter(user=self.librarian).first()
        self.assertIsNotNone(admin_notif)
        self.assertIn("wants to return", admin_notif.message)
        self.assertIsNotNone(librarian_notif)
        self.assertIn("has requested to return", librarian_notif.message)

        # Check my_borrowed_books now shows pending return
        my_books_resp = self.client.get(reverse('my_borrowed_books'))
        self.assertTrue(my_books_resp.context['has_pending_return'])

    def test_request_return_duplicate_prevented(self):
        from books.models import ReturnRequest
        ReturnRequest.objects.create(transaction=self.issue_tx, status=ReturnRequest.STATUS_PENDING)

        self.client.login(username='student1', password='password123')
        url = reverse('request_return', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('my_borrowed_books'))
        self.assertEqual(ReturnRequest.objects.filter(transaction=self.issue_tx).count(), 1)

    def test_request_return_already_returned_redirects(self):
        self.issue_tx.mark_as_returned()
        self.client.login(username='student1', password='password123')
        url = reverse('request_return', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('my_borrowed_books'))

    def test_admin_return_request_list_view(self):
        from books.models import ReturnRequest
        ReturnRequest.objects.create(transaction=self.issue_tx, status=ReturnRequest.STATUS_PENDING)

        self.client.login(username='admin1', password='password123')
        url = reverse('admin_return_request_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['pending_returns']), 1)

    def test_approve_return_request(self):
        from books.models import ReturnRequest, Notification
        return_req = ReturnRequest.objects.create(transaction=self.issue_tx, status=ReturnRequest.STATUS_PENDING)
        initial_available = self.book.available_copies

        self.client.login(username='admin1', password='password123')
        url = reverse('approve_return_request', kwargs={'request_id': return_req.pk})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('admin_return_request_list'))

        return_req.refresh_from_db()
        self.issue_tx.refresh_from_db()
        self.book.refresh_from_db()

        self.assertEqual(return_req.status, ReturnRequest.STATUS_APPROVED)
        self.assertEqual(self.issue_tx.status, 'RETURNED')
        self.assertIsNotNone(self.issue_tx.return_date)
        self.assertEqual(self.book.available_copies, initial_available + 1)

        # Check notification sent to student & librarian
        student_notif = Notification.objects.filter(user=self.student1).first()
        self.assertIsNotNone(student_notif)
        self.assertIn("has been confirmed", student_notif.message)

    def test_student_dashboard_metrics_and_display_status(self):
        from django.utils import timezone
        import datetime
        from books.models import IssueTransaction, ReturnRequest

        today = timezone.now().date()

        # Use a separate book with ample copies so available_copies never
        # goes negative regardless of how many transactions this test creates.
        # (self.book only has 3 copies, 1 already consumed by setUp's self.issue_tx)
        dashboard_book = Book.objects.create(
            title='The Pragmatic Programmer',
            author='Andrew Hunt',
            isbn='9780135957059',
            category='Software',
            publisher='Addison-Wesley',
            price=50.00,
            total_copies=10,
            available_copies=10,
        )

        tx_returned = IssueTransaction.objects.create(
            book=dashboard_book,
            user=self.student2,
            admin=self.admin,
            due_date=today - datetime.timedelta(days=10)
        )
        tx_returned.mark_as_returned()

        tx_return_requested = IssueTransaction.objects.create(
            book=dashboard_book,
            user=self.student2,
            admin=self.admin,
            due_date=today + datetime.timedelta(days=5)
        )
        ReturnRequest.objects.create(transaction=tx_return_requested, status=ReturnRequest.STATUS_PENDING)

        tx_overdue = IssueTransaction.objects.create(
            book=dashboard_book,
            user=self.student2,
            admin=self.admin,
            due_date=today - datetime.timedelta(days=2)
        )

        tx_due_today = IssueTransaction.objects.create(
            book=dashboard_book,
            user=self.student2,
            admin=self.admin,
            due_date=today
        )

        self.client.login(username='student2', password='password123')
        url = reverse('student_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        activity = list(response.context['recent_activity'])
        status_map = {tx.transaction_id: tx.display_status for tx in activity}
        self.assertEqual(status_map[tx_returned.transaction_id], 'Returned')
        self.assertEqual(status_map[tx_return_requested.transaction_id], 'Return Requested')
        self.assertEqual(status_map[tx_overdue.transaction_id], 'Overdue')
        self.assertEqual(status_map[tx_due_today.transaction_id], 'Due Today')


class StudentReliabilityAndHistoryTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin1',
            email='admin@example.com',
            password='password123',
            role='admin'
        )
        self.student = User.objects.create_user(
            username='student1',
            email='student1@example.com',
            password='password123',
            role='student'
        )
        self.book = Book.objects.create(
            title='Clean Code',
            author='Robert C. Martin',
            isbn='9780132350884',
            category='Software',
            publisher='Prentice Hall',
            price=45.00,
            total_copies=5,
            available_copies=5
        )

    def test_get_user_borrow_stats_new(self):
        from books.views import get_user_borrow_stats
        stats = get_user_borrow_stats(self.student)
        self.assertEqual(stats['total_borrows'], 0)
        self.assertEqual(stats['status'], 'New')

    def test_get_user_borrow_stats_reliable(self):
        from books.models import IssueTransaction
        from django.utils import timezone
        import datetime
        from books.views import get_user_borrow_stats

        today = timezone.now().date()
        tx = IssueTransaction.objects.create(
            book=self.book,
            user=self.student,
            admin=self.admin,
            due_date=today + datetime.timedelta(days=7)
        )
        tx.mark_as_returned()

        stats = get_user_borrow_stats(self.student)
        self.assertEqual(stats['total_borrows'], 1)
        self.assertEqual(stats['status'], 'Reliable')

    def test_get_user_borrow_stats_caution_and_risky(self):
        from books.models import IssueTransaction
        from django.utils import timezone
        import datetime
        from books.views import get_user_borrow_stats

        today = timezone.now().date()
        # 1 overdue return
        tx1 = IssueTransaction.objects.create(
            book=self.book,
            user=self.student,
            admin=self.admin,
            due_date=today - datetime.timedelta(days=2)
        )
        # Manually mark as returned overdue
        tx1.status = IssueTransaction.STATUS_RETURNED
        tx1.return_date = today
        tx1.save()

        stats = get_user_borrow_stats(self.student)
        self.assertEqual(stats['status'], 'Caution')

        # 2 more overdue returns (making total 3)
        for i in range(2):
            tx = IssueTransaction.objects.create(
                book=self.book,
                user=self.student,
                admin=self.admin,
                due_date=today - datetime.timedelta(days=2)
            )
            tx.status = IssueTransaction.STATUS_RETURNED
            tx.return_date = today
            tx.save()

        stats = get_user_borrow_stats(self.student)
        self.assertEqual(stats['status'], 'Risky')

    def test_student_list_view(self):
        self.client.login(username='admin1', password='password123')
        url = reverse('student_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/student_list.html')
        students = response.context['students']
        self.assertTrue(any(s.username == self.student.username for s in students))

    def test_student_borrow_history_view(self):
        from books.models import IssueTransaction
        from django.utils import timezone
        import datetime
        
        today = timezone.now().date()
        tx = IssueTransaction.objects.create(
            book=self.book,
            user=self.student,
            admin=self.admin,
            due_date=today + datetime.timedelta(days=7)
        )
        tx.mark_as_returned()

        self.client.login(username='admin1', password='password123')
        url = reverse('student_borrow_history', kwargs={'user_id': self.student.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/student_borrow_history.html')
        events = response.context['events']
        self.assertEqual(len(events), 2)  # 1 borrow, 1 return





