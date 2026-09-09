"""The daily food menu - manager-side editing and customer-side ordering."""

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

from automation import automation_controller, gTTS, laptop_speaker, pyautogui, pyttsx3
from decorators import (admin_required, admin_required_api,
                        admin_required_api_success, manager_required,
                        super_admin_required)
from extensions import db
from helpers import (SUPER_ADMIN_RECOVERY_EMAIL, safe_print as print,
                     save_uploaded_file, save_uploaded_files, send_email)
from models import (Admin, Customer, DailyMenuItem, DailyMenuOrder,
                    Notification, Order, OrderItem, Product, ProductImage,
                    Room, RoomBooking, RoomImage, create_notification)

bp = Blueprint('menu', __name__)


@bp.route('/order_daily_item/<int:item_id>', methods=['POST'])
def order_daily_item(item_id):
    item = DailyMenuItem.query.get_or_404(item_id)

    if not item.available:
        flash('Món này hiện không còn phục vụ', 'error')
        return redirect(url_for('public.customer_home'))

    customer_name = request.form.get('customer_name', '').strip() or 'Khách'
    customer_phone = request.form.get('customer_phone', '').strip()
    notes = request.form.get('notes', '').strip()

    try:
        quantity = max(1, int(request.form.get('quantity', 1)))
    except ValueError:
        quantity = 1

    if not customer_phone:
        flash('Vui lòng nhập số điện thoại để chúng tôi liên hệ', 'error')
        return redirect(url_for('public.customer_home'))

    order = DailyMenuOrder(
        item_id=item.id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        quantity=quantity,
        notes=notes
    )
    db.session.add(order)
    create_notification('daily_menu_order', f"🍽️ Đặt món: {customer_name} đặt {quantity}x {item.name}")
    db.session.commit()

    flash(f'Đặt món "{item.name}" thành công! Chúng tôi sẽ liên hệ với bạn sớm.', 'success')
    return redirect(url_for('public.customer_home'))

# ---- Manager: daily menu management (logs in via /customer/login) ----

@bp.route('/customer/daily-menu')
@manager_required
def daily_menu_manage():
    items = DailyMenuItem.query.order_by(DailyMenuItem.created_at.desc()).all()
    base_template = 'admin_base.html' if 'admin_logged_in' in session else 'modern_base.html'
    return render_template('daily_menu_manage.html', items=items, base_template=base_template)

@bp.route('/customer/daily-menu/add', methods=['POST'])
@manager_required
def daily_menu_add():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    price_raw = request.form.get('price', '').strip()

    if not name or not price_raw:
        flash('Vui lòng nhập tên món và giá', 'error')
        return redirect(url_for('menu.daily_menu_manage'))

    try:
        price = float(price_raw)
    except ValueError:
        flash('Giá không hợp lệ', 'error')
        return redirect(url_for('menu.daily_menu_manage'))

    image = save_uploaded_file(request.files.get('image')) or 'pngtree.png'

    item = DailyMenuItem(
        name=name,
        description=description,
        price=price,
        image=image,
        created_by_id=session.get('customer_id')
    )
    db.session.add(item)
    db.session.commit()
    flash(f'Đã thêm "{name}" vào thực đơn hôm nay', 'success')
    return redirect(url_for('menu.daily_menu_manage'))

@bp.route('/customer/daily-menu/<int:item_id>/toggle', methods=['POST'])
@manager_required
def daily_menu_toggle(item_id):
    item = DailyMenuItem.query.get_or_404(item_id)
    item.available = not item.available
    db.session.commit()
    return redirect(url_for('menu.daily_menu_manage'))

@bp.route('/customer/daily-menu/<int:item_id>/delete', methods=['POST'])
@manager_required
def daily_menu_delete(item_id):
    item = DailyMenuItem.query.get_or_404(item_id)
    name = item.name
    try:
        db.session.delete(item)
        db.session.commit()
        flash(f'Đã xóa "{name}" khỏi thực đơn', 'success')
    except Exception:
        db.session.rollback()
        flash(f'Không thể xóa "{name}" vì đã có đơn đặt liên quan — hãy tắt hiển thị thay vì xóa', 'error')
    return redirect(url_for('menu.daily_menu_manage'))

# ---- Admin: view daily menu orders ----
