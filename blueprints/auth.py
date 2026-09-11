"""Sign-in, sign-out and password recovery for both admins and customers."""

import logging

import base64
import io
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta

import openpyxl
import qrcode
from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, send_file, session, url_for)
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import func, text
from werkzeug.security import check_password_hash, generate_password_hash

from decorators import (admin_required, admin_required_api,
                        admin_required_api_success, manager_required,
                        super_admin_required)
from extensions import db
from helpers import (SUPER_ADMIN_RECOVERY_EMAIL, safe_print as print,
                     save_uploaded_file, save_uploaded_files, send_email)
from models import (Admin, Customer, Notification, Order, OrderItem,
                    Product, ProductImage,
                    Room, RoomBooking, RoomImage, create_notification)

logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)


@bp.route('/admin')
@bp.route('/admin/login', methods=['GET'])
def admin_login():
    if 'admin_logged_in' in session:
        return redirect(url_for('admin.admin_dashboard'))
    return render_template('admin_login.html')

@bp.route('/admin/login', methods=['POST'])
def admin_authenticate():
    username = request.form.get('username')
    password = request.form.get('password')
    
    admin = Admin.query.filter_by(username=username).first()
    if admin and check_password_hash(admin.password, password):
        session['admin_logged_in'] = True
        session['admin_username'] = username
        session['admin_role'] = admin.role
        # Deliberately NOT permanent: admins must log in again every time
        # they open a new browser session (unlike customers).
        session.permanent = False
        return redirect(url_for('admin.admin_dashboard'))
    else:
        flash('Thông tin đăng nhập không hợp lệ', 'error')
        return redirect(url_for('auth.admin_login'))

@bp.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    session.pop('admin_role', None)
    return redirect(url_for('auth.admin_login'))

@bp.route('/admin/change_password', methods=['GET'])
@admin_required
def admin_change_password():
    return render_template('admin_change_password.html')

@bp.route('/admin/change_password', methods=['POST'])
@admin_required
def admin_change_password_submit():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    admin = Admin.query.filter_by(username=session.get('admin_username')).first_or_404()

    if not check_password_hash(admin.password, current_password):
        flash('Mật khẩu hiện tại không đúng', 'error')
        return redirect(url_for('auth.admin_change_password'))

    if len(new_password) < 6:
        flash('Mật khẩu mới phải có ít nhất 6 ký tự', 'error')
        return redirect(url_for('auth.admin_change_password'))

    if new_password != confirm_password:
        flash('Xác nhận mật khẩu không khớp', 'error')
        return redirect(url_for('auth.admin_change_password'))

    admin.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Đã đổi mật khẩu thành công', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@bp.route('/admin/forgot_password', methods=['GET'])
def admin_forgot_password():
    return render_template('admin_forgot_password.html')

@bp.route('/admin/forgot_password', methods=['POST'])
def admin_forgot_password_submit():
    username = request.form.get('username', '').strip()
    admin = Admin.query.filter_by(username=username, role='super_admin').first()

    # Always show the same message regardless of whether the account exists,
    # so this form can't be used to discover valid super_admin usernames.
    generic_message = 'Nếu tài khoản Super Admin tồn tại, mã xác nhận đã được gửi qua email khôi phục.'

    if admin:
        code = f"{secrets.randbelow(1000000):06d}"
        admin.reset_code_hash = generate_password_hash(code)
        admin.reset_code_expiry = datetime.utcnow() + timedelta(minutes=15)
        admin.reset_code_attempts = 0
        db.session.commit()
        send_email(
            SUPER_ADMIN_RECOVERY_EMAIL,
            'Mã khôi phục mật khẩu Super Admin - Cô Bông Cát Lái',
            f'Mã xác nhận khôi phục mật khẩu cho tài khoản "{username}" là: {code}\n\n'
            f'Mã có hiệu lực trong 15 phút. Nếu bạn không yêu cầu, hãy bỏ qua email này.'
        )

    flash(generic_message, 'success')
    return redirect(url_for('auth.admin_reset_password', username=username))

@bp.route('/admin/reset_password', methods=['GET'])
def admin_reset_password():
    return render_template('admin_reset_password.html', username=request.args.get('username', ''))

@bp.route('/admin/reset_password', methods=['POST'])
def admin_reset_password_submit():
    username = request.form.get('username', '').strip()
    code = request.form.get('code', '').strip()
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    admin = Admin.query.filter_by(username=username, role='super_admin').first()

    # The code is six digits, so all million of them can be tried inside the
    # 15-minute window if wrong guesses are free. Burn the code after a few.
    MAX_RESET_ATTEMPTS = 5

    expired = (not admin or not admin.reset_code_hash or not admin.reset_code_expiry
               or datetime.utcnow() > admin.reset_code_expiry)

    if not expired and not check_password_hash(admin.reset_code_hash, code):
        admin.reset_code_attempts = (admin.reset_code_attempts or 0) + 1
        if admin.reset_code_attempts >= MAX_RESET_ATTEMPTS:
            admin.reset_code_hash = None
            admin.reset_code_expiry = None
            logger.warning('Reset code for %r invalidated after %d wrong attempts',
                           username, admin.reset_code_attempts)
        db.session.commit()
        expired = True

    if expired:
        flash('Mã xác nhận không đúng hoặc đã hết hạn', 'error')
        return redirect(url_for('auth.admin_reset_password', username=username))

    if len(new_password) < 6:
        flash('Mật khẩu mới phải có ít nhất 6 ký tự', 'error')
        return redirect(url_for('auth.admin_reset_password', username=username))

    if new_password != confirm_password:
        flash('Xác nhận mật khẩu không khớp', 'error')
        return redirect(url_for('auth.admin_reset_password', username=username))

    admin.password = generate_password_hash(new_password)
    admin.reset_code_hash = None
    admin.reset_code_expiry = None
    admin.reset_code_attempts = 0
    db.session.commit()
    flash('Đã đặt lại mật khẩu thành công, hãy đăng nhập lại', 'success')
    return redirect(url_for('auth.admin_login'))

@bp.route('/customer/login')
def customer_login():
    if 'customer_logged_in' in session:
        return redirect(url_for('public.customer_home'))
    return render_template('customer_login.html')

@bp.route('/customer/authenticate', methods=['POST'])
def customer_authenticate():
    username = request.form.get('username')
    password = request.form.get('password')
    
    customer = Customer.query.filter_by(username=username).first()
    if customer and check_password_hash(customer.password, password):
        session['customer_logged_in'] = True
        session['customer_id'] = customer.id
        session['customer_name'] = customer.full_name
        session['customer_role'] = customer.role
        # Customers stay logged in across visits (permanent session).
        session.permanent = True
        flash('Đăng nhập thành công!', 'success')
        return redirect(url_for('public.customer_home'))
    else:
        flash('Thông tin đăng nhập không hợp lệ', 'error')
        return redirect(url_for('auth.customer_login'))

@bp.route('/customer/logout')
def customer_logout():
    session.pop('customer_logged_in', None)
    session.pop('customer_id', None)
    session.pop('customer_name', None)
    session.pop('customer_role', None)
    flash('Đăng xuất thành công!', 'success')
    return redirect(url_for('public.customer_home'))

@bp.route('/customer/register')
def customer_register():
    return render_template('customer_register.html')

@bp.route('/customer/create', methods=['POST'])
def customer_create():
    username = request.form.get('username')
    password = request.form.get('password')
    full_name = request.form.get('full_name') or username
    phone = request.form.get('phone') or ""
    
    # Check if username already exists
    if Customer.query.filter_by(username=username).first():
        flash('Tên đăng nhập đã tồn tại', 'error')
        return redirect(url_for('auth.customer_register'))
    
    # Create new customer
    customer = Customer(
        username=username,
        password=generate_password_hash(password),
        full_name=full_name,
        phone=phone
    )
    db.session.add(customer)
    db.session.commit()
    
    flash('Đăng ký thành công!', 'success')
    return redirect(url_for('public.customer_home'))

# Excel Export Routes
