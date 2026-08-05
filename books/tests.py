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
        from books.models import IssueTransaction
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

    def test_my_borrowed_books_none_when_returned(self):
        self.issue_tx.mark_as_returned()
        self.client.login(username='student1', password='password123')
        url = reverse('my_borrowed_books')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['active_issue'])

    def test_return_book_get_confirmation(self):
        self.client.login(username='student1', password='password123')
        url = reverse('return_book', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/return_confirm.html')

    def test_return_book_other_user_404(self):
        # student2 trying to return student1's book
        self.client.login(username='student2', password='password123')
        url = reverse('return_book', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_return_book_post_success(self):
        initial_available = self.book.available_copies
        self.client.login(username='student1', password='password123')
        url = reverse('return_book', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('my_borrowed_books'))

        self.issue_tx.refresh_from_db()
        self.book.refresh_from_db()
        self.assertEqual(self.issue_tx.status, 'RETURNED')
        self.assertIsNotNone(self.issue_tx.return_date)
        self.assertEqual(self.book.available_copies, initial_available + 1)

    def test_return_book_already_returned_redirects(self):
        self.issue_tx.mark_as_returned()
        self.client.login(username='student1', password='password123')
        url = reverse('return_book', kwargs={'transaction_id': self.issue_tx.transaction_id})
        response = self.client.get(url)
        self.assertRedirects(response, reverse('my_borrowed_books'))

    def test_student_dashboard_metrics_and_display_status(self):
        from django.utils import timezone
        import datetime
        from books.models import IssueTransaction

        today = timezone.now().date()
        # Create an overdue transaction, due today transaction, active transaction, and returned transaction
        tx_returned = IssueTransaction.objects.create(
            book=self.book,
            user=self.student2,
            admin=self.admin,
            due_date=today - datetime.timedelta(days=10)
        )
        tx_returned.mark_as_returned()

        tx_overdue = IssueTransaction.objects.create(
            book=self.book,
            user=self.student2,
            admin=self.admin,
            due_date=today - datetime.timedelta(days=2)
        )

        tx_due_today = IssueTransaction.objects.create(
            book=self.book,
            user=self.student2,
            admin=self.admin,
            due_date=today
        )

        self.client.login(username='student2', password='password123')
        url = reverse('student_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['books_borrowed_count'], 2)

        activity = list(response.context['recent_activity'])
        # Map statuses
        status_map = {tx.transaction_id: tx.display_status for tx in activity}
        self.assertEqual(status_map[tx_returned.transaction_id], 'Returned')
        self.assertEqual(status_map[tx_overdue.transaction_id], 'Overdue')
        self.assertEqual(status_map[tx_due_today.transaction_id], 'Due Today')


