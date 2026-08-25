from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/student/', views.student_dashboard, name='student_dashboard'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/admin/users/', views.user_management_list, name='user_management_list'),
    path('dashboard/admin/users/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('dashboard/admin/users/<int:user_id>/toggle-block/', views.toggle_user_block, name='toggle_user_block'),
    path('forbidden/', views.forbidden_view, name='forbidden'),
]
