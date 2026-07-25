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
