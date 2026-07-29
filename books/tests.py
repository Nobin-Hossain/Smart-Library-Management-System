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

