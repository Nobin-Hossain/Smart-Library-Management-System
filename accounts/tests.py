from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from accounts.forms import UserRegistrationForm

User = get_user_model()

class StudentRegistrationValidationTest(TestCase):
    def test_valid_student_registration_model(self):
        user = User(
            username='JohnSmith',
            email='student1@example.com',
            role='student',
            student_id='123456',
            department='BCSE',
            first_name='John',
            last_name='Smith',
            password='hashed_password_placeholder'
        )
        # Should not raise any validation error
        user.full_clean()
        user.save()
        self.assertEqual(User.objects.count(), 1)

    # --- Student ID Tests ---

    def test_negative_student_id_model(self):
        user = User(
            username='AliceWong',
            email='student2@example.com',
            role='student',
            student_id='-12345',
            department='BCSE',
            first_name='Alice',
            last_name='Wong',
            password='hashed_password_placeholder'
        )
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()
        self.assertIn('student_id', ctx.exception.error_dict)

    def test_fractional_student_id_model(self):
        user = User(
            username='BobMiller',
            email='student3@example.com',
            role='student',
            student_id='123.45',
            department='BCSE',
            first_name='Bob',
            last_name='Miller',
            password='hashed_password_placeholder'
        )
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()
        self.assertIn('student_id', ctx.exception.error_dict)

    def test_alpha_student_id_model(self):
        user = User(
            username='CarlaJones',
            email='student4@example.com',
            role='student',
            student_id='123a45',
            department='BCSE',
            first_name='Carla',
            last_name='Jones',
            password='hashed_password_placeholder'
        )
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()
        self.assertIn('student_id', ctx.exception.error_dict)

    # --- Department Tests ---

    def test_invalid_department_model(self):
        user = User(
            username='DavidLee',
            email='student5@example.com',
            role='student',
            student_id='123456',
            department='Computer Science',  # Invalid choice
            first_name='David',
            last_name='Lee',
            password='hashed_password_placeholder'
        )
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()
        self.assertIn('department', ctx.exception.error_dict)

    def test_numeric_department_model(self):
        user = User(
            username='EmmaClark',
            email='student6@example.com',
            role='student',
            student_id='123456',
            department='-123.45',  # Invalid choice
            first_name='Emma',
            last_name='Clark',
            password='hashed_password_placeholder'
        )
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()
        self.assertIn('department', ctx.exception.error_dict)

    # --- Username Tests ---

    def test_numeric_username_model(self):
        user = User(
            username='user123',  # Contains digits — invalid
            email='student7@example.com',
            role='student',
            student_id='111111',
            department='BEEE',
            first_name='Frank',
            last_name='Hall',
            password='hashed_password_placeholder'
        )
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()
        self.assertIn('username', ctx.exception.error_dict)

    def test_negative_username_model(self):
        user = User(
            username='-FrankHall',  # Contains dash — invalid
            email='student8@example.com',
            role='student',
            student_id='222222',
            department='BSME',
            first_name='Frank',
            last_name='Hall',
            password='hashed_password_placeholder'
        )
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()
        self.assertIn('username', ctx.exception.error_dict)

    # --- Full Name Tests (form-level) ---

    def test_form_validation_valid(self):
        data = {
            'username': 'JaneDoe',
            'email': 'jane@example.com',
            'role': 'student',
            'student_id': '7890',
            'department': 'BCSE',
            'full_name': 'Jane Doe',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_form_fullname_with_numbers(self):
        data = {
            'username': 'MarcusBrown',
            'email': 'marcus@example.com',
            'role': 'student',
            'student_id': '7890',
            'department': 'BCSE',
            'full_name': 'Marcus123',  # Numbers — invalid
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('full_name', form.errors)

    def test_form_fullname_negative(self):
        data = {
            'username': 'NancyGreen',
            'email': 'nancy@example.com',
            'role': 'student',
            'student_id': '7890',
            'department': 'BCSE',
            'full_name': '-Nancy',  # Starts with dash — invalid
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('full_name', form.errors)

    def test_form_username_with_numbers(self):
        data = {
            'username': 'Oscar99',  # Contains digits — invalid
            'email': 'oscar@example.com',
            'role': 'student',
            'student_id': '7890',
            'department': 'BCSE',
            'full_name': 'Oscar White',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_form_username_letters_only(self):
        data = {
            'username': 'OscarWhite',  # Letters only — valid
            'email': 'oscar2@example.com',
            'role': 'student',
            'student_id': '7890',
            'department': 'BCSE',
            'full_name': 'Oscar White',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())

    # --- Student ID form-level tests ---

    def test_form_validation_invalid_negative_student_id(self):
        data = {
            'username': 'PetraKim',
            'email': 'petra@example.com',
            'role': 'student',
            'student_id': '-7890',
            'department': 'BEEE',
            'full_name': 'Petra Kim',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('student_id', form.errors)

    def test_form_validation_invalid_fractional_student_id(self):
        data = {
            'username': 'QuinnPark',
            'email': 'quinn@example.com',
            'role': 'student',
            'student_id': '78.90',
            'department': 'BSCE',
            'full_name': 'Quinn Park',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('student_id', form.errors)

    # --- Department form-level tests ---

    def test_form_validation_invalid_department(self):
        data = {
            'username': 'RachelBond',
            'email': 'rachel@example.com',
            'role': 'student',
            'student_id': '7890',
            'department': 'InvalidDepartment',
            'full_name': 'Rachel Bond',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('department', form.errors)

    def test_form_validation_numeric_department(self):
        data = {
            'username': 'SamFord',
            'email': 'sam@example.com',
            'role': 'student',
            'student_id': '7890',
            'department': '-12.3',
            'full_name': 'Sam Ford',
            'password': 'StrongPassword123!',
            'confirm_password': 'StrongPassword123!'
        }
        form = UserRegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('department', form.errors)


class UserManagementAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='AdminUser',
            email='admin@example.com',
            password='password123',
            role='admin'
        )
        self.student_user = User.objects.create_user(
            username='StudentUser',
            email='student@example.com',
            password='password123',
            role='student',
            student_id='9999',
            department='BCSE'
        )
        self.librarian_user = User.objects.create_user(
            username='LibrarianUser',
            email='librarian@example.com',
            password='password123',
            role='librarian'
        )

    def test_admin_dashboard_user_counts(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/dashboard/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_users'], 2)

    def test_user_management_list_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/dashboard/admin/users/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.student_user, response.context['students'])
        self.assertIn(self.librarian_user, response.context['librarians'])

    def test_edit_user_get(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(f'/dashboard/admin/users/{self.student_user.id}/edit/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'StudentUser')

    def test_edit_user_post(self):
        self.client.force_login(self.admin_user)
        data = {
            'username': 'UpdatedStudent',
            'email': 'updated@example.com',
            'first_name': 'NewFirst',
            'last_name': 'NewLast',
            'student_id': '8888',
            'department': 'BEEE'
        }
        response = self.client.post(f'/dashboard/admin/users/{self.student_user.id}/edit/', data)
        self.assertRedirects(response, '/dashboard/admin/users/')
        self.student_user.refresh_from_db()
        self.assertEqual(self.student_user.username, 'UpdatedStudent')
        self.assertEqual(self.student_user.email, 'updated@example.com')
        self.assertEqual(self.student_user.student_id, '8888')

    def test_toggle_user_block_post(self):
        self.client.force_login(self.admin_user)
        self.assertTrue(self.student_user.is_active)
        response = self.client.post(f'/dashboard/admin/users/{self.student_user.id}/toggle-block/')
        self.assertRedirects(response, '/dashboard/admin/users/')
        self.student_user.refresh_from_db()
        self.assertFalse(self.student_user.is_active)

        # Toggle back
        response = self.client.post(f'/dashboard/admin/users/{self.student_user.id}/toggle-block/')
        self.student_user.refresh_from_db()
        self.assertTrue(self.student_user.is_active)

    def test_toggle_user_block_get_not_allowed(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(f'/dashboard/admin/users/{self.student_user.id}/toggle-block/')
        self.assertEqual(response.status_code, 405)

    def test_toggle_user_block_librarian_not_found(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(f'/dashboard/admin/users/{self.librarian_user.id}/toggle-block/')
        self.assertEqual(response.status_code, 404)
