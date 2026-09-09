"""Session-based access control for the admin and manager areas."""

from functools import wraps

from flask import flash, jsonify, redirect, session, url_for


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('auth.admin_login'))
        return view(*args, **kwargs)
    return wrapped

def admin_required_api(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return view(*args, **kwargs)
    return wrapped

def admin_required_api_success(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return view(*args, **kwargs)
    return wrapped

def super_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('auth.admin_login'))
        if session.get('admin_role') != 'super_admin':
            flash('Chỉ Super Admin mới có quyền truy cập chức năng này', 'error')
            return redirect(url_for('admin.admin_dashboard'))
        return view(*args, **kwargs)
    return wrapped

def manager_required(view):
    """Allows Manager customer accounts, and also Admin/Super Admin (admins
    have full access by design - Manager is just a helper role for daily
    menu updates, not the only account that can do it)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'admin_logged_in' in session:
            return view(*args, **kwargs)
        if 'customer_logged_in' not in session:
            return redirect(url_for('auth.customer_login'))
        if session.get('customer_role') != 'manager':
            flash('Bạn không có quyền truy cập chức năng này', 'error')
            return redirect(url_for('public.customer_home'))
        return view(*args, **kwargs)
    return wrapped
