from django.shortcuts import render, redirect
from functools import wraps

def role_required(*allowed_roles):
    """
    Decorator to restrict access to specific views based on User role.
    If the user's role is not in allowed_roles, they are shown a custom 403 page.
    If the user is not authenticated, they are redirected to the login page.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                # Redirect to login page if user is not authenticated
                return redirect('login')
            
            # Check user role
            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            else:
                # Render 403 Forbidden template
                return render(request, 'accounts/forbidden.html', status=403)
        return _wrapped_view
    return decorator
